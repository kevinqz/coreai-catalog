// CoreAIBenchRunner — record types, statistics, and environment capture.
//
// Every value written here is measured or echoed from the orchestrator's
// run context. Nothing is fabricated: unknown stays nil/"unknown".

import Foundation

// MARK: - Runner identity

/// Bump on any change that could affect measured numbers.
let benchRunnerVersion = "0.1.0"

/// Protocol implemented (benchmarks/protocol-config.json "protocol_version").
let benchProtocolVersion = "1.0"

// MARK: - Orchestrator-supplied run context
//
// Produced by coreai_catalog/bench.py (build_run_context). The runner never
// invents provenance — it only echoes what the orchestrator resolved from
// artifacts.yaml and the installer manifest.

struct RunContext: Codable {
    var modelId: String?
    /// 40-hex Hugging Face commit the installed artifact was pinned to.
    var artifactRevision: String?
    /// sha256 over the artifact's sorted per-file digest list
    /// (see docs/benchmark-protocol.md, "Artifact digest root").
    var artifactSha256Root: String?
    var artifactFilesTotal: Int?
    /// Freshness nonce (catalog repo HEAD commit at invocation time).
    var freshnessNonce: String?
}

// MARK: - Protocol config subset (benchmarks/protocol-config.json)

struct ProtocolConfig: Codable {
    struct StandardPrompt: Codable {
        var text: String
        var repeatUntilTokens: Int
    }
    struct CoarseningEntry: Codable {
        // protocol-config.json B5 fix: exact-identifier LIST (raw_models),
        // not a single raw_prefix — a prefix binned whole hardware generations
        // onto one chip (e.g. Mac16,1 base-M4 into mac-m4-max).
        var rawModels: [String]
        var deviceClass: String
        var chipFamily: String
    }
    struct DeviceCoarsening: Codable {
        var mapping: [CoarseningEntry]
    }
    var protocolVersion: String
    var standardPrompt: StandardPrompt
    var deviceCoarsening: DeviceCoarsening?
}

// MARK: - Output records

struct TrialRecord: Codable {
    var trial: Int
    var promptTokens: Int
    var generatedTokens: Int
    var timeToFirstTokenMs: Double
    var decodeTokens: Int
    var decodeSeconds: Double
    var decodeTokensPerSecond: Double
    var totalSeconds: Double
    var peakMemoryMb: Double?
    var thermalStateBefore: String
    var thermalStateAfter: String
}

struct MetricSummary: Codable {
    var metric: String
    var unit: String
    var median: Double
    var stddev: Double
    var p50: Double
    var p95: Double
    var higherIsBetter: Bool
}

struct EnvironmentCapture: Codable {
    var osVersion: String
    var osMajor: String
    var lowPowerMode: Bool
    var thermalStateStart: String
    var thermalStateEnd: String
    var engineType: String
    /// Derived from the engine type per the upstream engine-selection doc
    /// (apple/coreai-models CoreAILanguageModel.swift:18-22 @ e203a0da:
    /// pipelined = GPU, sequential = CPU, static-shape = Neural Engine).
    var computeUnitInferred: String
}

struct SelfCheck: Codable {
    /// True when the standard prompt tokenized to exactly the requested count.
    var promptTokenCountExact: Bool
    /// Greedy sampling (temperature 0) — deterministic where the engine allows.
    var greedySampling: Bool
    /// The public SamplingConfiguration API has no seed parameter
    /// (apple/coreai-models Samplers/SamplingConfiguration.swift:113 @ e203a0da),
    /// so the seed is recorded but not applied; determinism comes from greedy.
    var samplingSeedApplied: Bool
    /// True if any trial started or ended at thermal state serious/critical.
    var thermalPressureDetected: Bool
    /// True when every measured trial produced the requested token count.
    var allTrialsCompletedRequestedTokens: Bool
    /// True when the raw device model was coarsened via the protocol mapping.
    var deviceClassCoarsened: Bool
}

struct RunManifest: Codable {
    var runnerVersion: String
    var protocolVersion: String
    var runId: String
    var startedAt: String
    var finishedAt: String
    var modelId: String
    var modelBundleName: String
    var artifactRevision: String?
    var artifactSha256Root: String?
    var artifactFilesTotal: Int?
    var freshnessNonce: String?
    var seed: UInt64
    var sampling: String
    /// Coarsened device class (e.g. "mac-m4-max"); "unknown" when the raw
    /// model has no mapping. The raw device identifier is never written to
    /// disk (privacy rules, docs/benchmark-protocol.md).
    var deviceClass: String
    var chipFamily: String?
    var promptTokens: Int
    var generationTokens: Int
    var warmupRuns: Int
    var measuredRuns: Int
    var metrics: [MetricSummary]
    var environment: EnvironmentCapture
    var selfCheck: SelfCheck
    var rawTrialsFile: String
}

// MARK: - Statistics

enum Stats {
    static func median(_ values: [Double]) -> Double {
        percentile(values, 50)
    }

    /// Sample standard deviation; 0 for n < 2.
    static func stddev(_ values: [Double]) -> Double {
        guard values.count > 1 else { return 0 }
        let n = Double(values.count)
        let mean = values.reduce(0, +) / n
        let sumSq = values.reduce(0) { $0 + ($1 - mean) * ($1 - mean) }
        return (sumSq / (n - 1)).squareRoot()
    }

    /// Linear-interpolated percentile (p in 0...100).
    static func percentile(_ values: [Double], _ p: Double) -> Double {
        guard !values.isEmpty else { return 0 }
        let sorted = values.sorted()
        if sorted.count == 1 { return sorted[0] }
        let rank = p / 100 * Double(sorted.count - 1)
        let lower = Int(rank.rounded(.down))
        let upper = Int(rank.rounded(.up))
        if lower == upper { return sorted[lower] }
        let fraction = rank - Double(lower)
        return sorted[lower] + (sorted[upper] - sorted[lower]) * fraction
    }
}

// MARK: - Environment capture helpers

func thermalStateName(_ state: ProcessInfo.ThermalState) -> String {
    switch state {
    case .nominal: return "nominal"
    case .fair: return "fair"
    case .serious: return "serious"
    case .critical: return "critical"
    @unknown default: return "unknown"
    }
}

func currentThermalStateName() -> String {
    thermalStateName(ProcessInfo.processInfo.thermalState)
}

func sysctlString(_ name: String) -> String? {
    var size = 0
    guard sysctlbyname(name, nil, &size, nil, 0) == 0, size > 0 else { return nil }
    var buffer = [CChar](repeating: 0, count: size)
    guard sysctlbyname(name, &buffer, &size, nil, 0) == 0 else { return nil }
    return buffer.withUnsafeBufferPointer { pointer in
        guard let base = pointer.baseAddress else { return nil }
        return String(validatingCString: base)
    }
}

/// Peak resident memory in bytes via mach_task_basic_info, as specified by
/// docs/benchmark-protocol.md ("Record peak memory via mach_task_basic_info").
func peakResidentBytes() -> UInt64? {
    var info = mach_task_basic_info()
    var count = mach_msg_type_number_t(
        MemoryLayout<mach_task_basic_info>.size / MemoryLayout<natural_t>.size
    )
    let result = withUnsafeMutablePointer(to: &info) { infoPointer in
        infoPointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
            task_info(
                mach_task_self_,
                task_flavor_t(MACH_TASK_BASIC_INFO),
                $0,
                &count
            )
        }
    }
    guard result == KERN_SUCCESS else { return nil }
    return info.resident_size_max
}

/// Maps an engine type name to a compute unit, grounded in the upstream
/// engine-selection documentation (apple/coreai-models
/// CoreAILanguageModel.swift:18-22 @ e203a0da): "Pipelined: GPU-accelerated",
/// "Sequential: CPU-based", "Static-shape: Neural Engine optimized".
func inferComputeUnit(engineTypeName: String) -> String {
    let lowered = engineTypeName.lowercased()
    if lowered.contains("pipelined") { return "GPU" }
    if lowered.contains("staticshape") || lowered.contains("static-shape") { return "ANE" }
    if lowered.contains("sequential") { return "CPU" }
    return "unknown"
}

/// Coarsens a raw device model (e.g. "Mac16,6") using the protocol-config
/// mapping via EXACT identifier match (protocol-config.json B5 fix: exact
/// identifiers, not prefixes — a prefix bins whole hardware generations onto
/// one chip). Returns nil when no row lists the identifier — callers record
/// "unknown" rather than guessing.
func coarsenDevice(
    rawModel: String,
    mapping: [ProtocolConfig.CoarseningEntry]
) -> ProtocolConfig.CoarseningEntry? {
    mapping.first { $0.rawModels.contains(rawModel) }
}

func iso8601Now() -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    return formatter.string(from: Date())
}
