// coreai-bench-runner — reference benchmark runner for coreai-catalog
// (redteam findings B1/B8; spec §3.2 step 1).
//
// Implements benchmarks/protocol-config.json v1.0 for LLM-type models:
// decode_throughput (128-token standard prompt, 256-token generation,
// 3 warmup + 10 measured runs, median) and time_to_first_token.
//
// Every apple/coreai-models API call below is grounded in the upstream
// source at commit e203a0da1f847041d7d28036fcc9b484495359bb (tag 0.1.0 has
// the same public surface). Citations use repo-relative paths:
//   - LanguageBundle(from:)              swift/Sources/CoreAILanguageModels/Bundle/LanguageBundle.swift:26
//   - bundle.loadTokenizer()             swift/Sources/CoreAILanguageModels/Bundle/LanguageBundle.swift:93
//   - tokenizer.encode(text:)            usage: swift/Sources/CoreAILanguageModels/LanguageModel/CoreAILanguageModel.swift:668
//   - ModelConfig(...)                   usage: swift/Sources/Tools/benchmark/BenchmarkMain.swift:60-67
//   - EngineFactory.createEngine(...)    swift/Sources/CoreAILanguageModels/InferenceEngines/EngineFactory.swift:33-37
//   - engine.reset()                     swift/Sources/CoreAILanguageModels/InferenceEngines/InferenceEngine.swift:216
//   - engine.generate(with:samplingConfiguration:inferenceOptions:)
//                                        swift/Sources/CoreAILanguageModels/InferenceEngines/InferenceEngine.swift:101-105
//   - InferenceOptions(maxTokens:includeLogits:)
//                                        swift/Sources/CoreAILanguageModels/InferenceEngines/InferenceEngine.swift:45-49
//   - SamplingConfiguration(temperature: 0) == .greedy (deterministic)
//                                        swift/Sources/CoreAILanguageModels/Samplers/SamplingConfiguration.swift:113,133
//   - InferenceOutput.tokenId            swift/Sources/CoreAILanguageModels/InferenceEngines/InferenceEngine.swift:20-21
// The trial timing scheme (SuspendingClock, first-token split, decode count
// = tokens - 1) mirrors Apple's own llm-benchmark tool:
// swift/Sources/Tools/benchmark/BenchmarkMain.swift:120-154.

import ArgumentParser
import CoreAILanguageModels
import Foundation

@main
struct Main {
    static func main() async throws {
        await BenchRunner.main()
    }
}

struct BenchRunner: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "coreai-bench-runner",
        abstract: "coreai-catalog protocol v1.0 benchmark runner (LLM metrics)"
    )

    @Option(name: .customLong("model-path"), help: "Path to the installed model bundle directory")
    var modelPath: String

    @Option(name: .customLong("model-id"), help: "Catalog model id (overrides run-context)")
    var modelId: String?

    @Option(
        name: .customLong("run-context"),
        help: "JSON file from the orchestrator with artifact provenance (revision, sha256 root, nonce)")
    var runContextPath: String?

    @Option(
        name: .customLong("protocol-config"),
        help: "Path to benchmarks/protocol-config.json (prompt text + device coarsening)")
    var protocolConfigPath: String?

    @Option(name: .customLong("prompt-tokens"), help: "Standard prompt length in tokens")
    var promptTokens: Int = 128

    @Option(name: .customLong("generation-tokens"), help: "Tokens generated per measured trial")
    var generationTokens: Int = 256

    @Option(name: .customLong("warmup-runs"), help: "Warmup iterations (timings discarded)")
    var warmupRuns: Int = 3

    @Option(name: .customLong("measured-runs"), help: "Measured timing trials")
    var measuredRuns: Int = 10

    @Option(
        name: .customLong("warmup-generation-tokens"),
        help: "Tokens generated per warmup iteration (protocol: 128)")
    var warmupGenerationTokens: Int = 128

    @Option(
        name: .long,
        help: "Recorded seed. The engine API exposes no sampling seed; determinism comes from greedy sampling.")
    var seed: UInt64 = 0

    @Option(name: .customLong("variant"), help: "Engine variant override (nil = auto-detect)")
    var variant: String?

    @Option(name: .customLong("out-dir"), help: "Output directory for trials JSONL + run manifest")
    var outDir: String = "bench-out"

    func validate() throws {
        if promptTokens < 1 { throw ValidationError("--prompt-tokens must be >= 1") }
        if generationTokens < 1 { throw ValidationError("--generation-tokens must be >= 1") }
        if warmupRuns < 0 { throw ValidationError("--warmup-runs must be >= 0") }
        if measuredRuns < 1 { throw ValidationError("--measured-runs must be >= 1") }
        if !FileManager.default.fileExists(atPath: modelPath) {
            throw ValidationError("Model path not found: \(modelPath)")
        }
    }

    func run() async throws {
        let startedAt = iso8601Now()
        let thermalStart = currentThermalStateName()

        let runContext = try loadRunContext()
        let protocolConfig = try loadProtocolConfig()

        // ── Load the model bundle and tokenizer (real upstream API) ──
        // LanguageBundle(from:) — LanguageBundle.swift:26.
        let bundle = try LanguageBundle(from: modelPath)
        // loadTokenizer() — LanguageBundle.swift:93.
        let tokenizer = try await bundle.loadTokenizer()

        // ── Standard prompt: repeat until >= N tokens, truncate to exactly N
        // (docs/benchmark-protocol.md: "Repeated until exactly 128 tokens
        // when tokenized by the model under test"). ──
        let promptText = protocolConfig?.standardPrompt.text
            ?? "The quick brown fox jumps over the lazy dog. "
        var repeated = promptText
        // tokenizer.encode(text:) — usage as in CoreAILanguageModel.swift:668.
        var encoded = tokenizer.encode(text: repeated)
        var growSteps = 0
        while encoded.count < promptTokens && growSteps < 4096 {
            repeated += promptText
            encoded = tokenizer.encode(text: repeated)
            growSteps += 1
        }
        let prompt = encoded.prefix(promptTokens).map(Int32.init)
        let promptExact = prompt.count == promptTokens

        // ── Engine creation, exactly as Apple's llm-benchmark does
        // (BenchmarkMain.swift:60-73). ──
        let engineConfig = ModelConfig(
            name: bundle.name,
            tokenizer: bundle.tokenizer,
            vocabSize: bundle.vocabSize,
            maxContextLength: bundle.maxContextLength,
            serializedModel: [bundle.modelAssetPath],
            function: bundle.language.functionMap?.name(for: "main") ?? "main"
        )
        let configData = try JSONEncoder().encode(engineConfig)
        // EngineOptions(variant:kvCacheStrategy:kvCacheSize:) — all defaulted;
        // nil variant = auto-detect (EngineFactory.swift:258-266).
        let options = EngineOptions(variant: variant)
        FileHandle.standardError.write(Data("Preparing engine...\n".utf8))
        let engine = try await EngineFactory.createEngine(
            config: configData,
            modelURL: try bundle.requireModelURL(for: ModelBundle.ComponentKey.main),
            options: options
        )
        let engineType = String(describing: type(of: engine))
        let computeUnit = inferComputeUnit(engineTypeName: engineType)

        // Greedy sampling: temperature 0 is the deterministic path the API
        // offers (SamplingConfiguration.swift:113,133); there is no seed
        // parameter, so `seed` is recorded but not applied.
        let sampling = SamplingConfiguration(temperature: 0)

        // ── Warmup (discarded) ──
        for i in 0..<warmupRuns {
            FileHandle.standardError.write(Data("Warmup \(i + 1)/\(warmupRuns)...\n".utf8))
            _ = try await runTrial(
                index: -1,
                engine: engine,
                prompt: prompt,
                sampling: sampling,
                maxTokens: warmupGenerationTokens
            )
        }

        // ── Measured trials ──
        var trials: [TrialRecord] = []
        for i in 0..<measuredRuns {
            let record = try await runTrial(
                index: i + 1,
                engine: engine,
                prompt: prompt,
                sampling: sampling,
                maxTokens: generationTokens
            )
            let trialLine = "Trial \(i + 1)/\(measuredRuns): "
                + String(format: "%.2f", record.decodeTokensPerSecond)
                + " tok/s, ttft "
                + String(format: "%.1f", record.timeToFirstTokenMs)
                + " ms, thermal \(record.thermalStateAfter)\n"
            FileHandle.standardError.write(Data(trialLine.utf8))
            trials.append(record)
        }

        let thermalEnd = currentThermalStateName()

        // ── Summaries (median per protocol; stddev/p50/p95 per
        // docs/benchmark-protocol.md "Statistics") ──
        let throughputs = trials.map { $0.decodeTokensPerSecond }
        let ttfts = trials.map { $0.timeToFirstTokenMs }
        let metrics = [
            MetricSummary(
                metric: "decode_throughput",
                unit: "tokens_per_second",
                median: Stats.median(throughputs),
                stddev: Stats.stddev(throughputs),
                p50: Stats.percentile(throughputs, 50),
                p95: Stats.percentile(throughputs, 95),
                higherIsBetter: true
            ),
            MetricSummary(
                metric: "time_to_first_token",
                unit: "milliseconds",
                median: Stats.median(ttfts),
                stddev: Stats.stddev(ttfts),
                p50: Stats.percentile(ttfts, 50),
                p95: Stats.percentile(ttfts, 95),
                higherIsBetter: false
            ),
        ]

        // ── Device coarsening. The raw model identifier is only compared
        // in-process against the protocol mapping and printed to stderr for
        // the operator; it is never written to any output file
        // (docs/benchmark-protocol.md, Privacy Rules). ──
        var deviceClass = "unknown"
        var chipFamily: String? = nil
        var coarsened = false
        if let rawModel = sysctlString("hw.model") {
            FileHandle.standardError.write(
                Data("Raw device model (not persisted): \(rawModel)\n".utf8))
            if let mapping = protocolConfig?.deviceCoarsening?.mapping,
                let entry = coarsenDevice(rawModel: rawModel, mapping: mapping)
            {
                deviceClass = entry.deviceClass
                chipFamily = entry.chipFamily
                coarsened = true
            }
        }

        let osVersion = ProcessInfo.processInfo.operatingSystemVersion
        let pressure = trials.contains {
            ["serious", "critical"].contains($0.thermalStateBefore)
                || ["serious", "critical"].contains($0.thermalStateAfter)
        }
        let allComplete = trials.allSatisfy { $0.generatedTokens == generationTokens }

        let manifest = RunManifest(
            runnerVersion: benchRunnerVersion,
            protocolVersion: protocolConfig?.protocolVersion ?? benchProtocolVersion,
            runId: UUID().uuidString,
            startedAt: startedAt,
            finishedAt: iso8601Now(),
            modelId: modelId ?? runContext?.modelId ?? bundle.name,
            modelBundleName: bundle.name,
            artifactRevision: runContext?.artifactRevision,
            artifactSha256Root: runContext?.artifactSha256Root,
            artifactFilesTotal: runContext?.artifactFilesTotal,
            freshnessNonce: runContext?.freshnessNonce,
            seed: seed,
            sampling: "greedy(temperature=0)",
            deviceClass: deviceClass,
            chipFamily: chipFamily,
            promptTokens: promptTokens,
            generationTokens: generationTokens,
            warmupRuns: warmupRuns,
            measuredRuns: measuredRuns,
            metrics: metrics,
            environment: EnvironmentCapture(
                osVersion:
                    "\(osVersion.majorVersion).\(osVersion.minorVersion).\(osVersion.patchVersion)",
                osMajor: String(osVersion.majorVersion),
                lowPowerMode: ProcessInfo.processInfo.isLowPowerModeEnabled,
                thermalStateStart: thermalStart,
                thermalStateEnd: thermalEnd,
                engineType: engineType,
                computeUnitInferred: computeUnit
            ),
            selfCheck: SelfCheck(
                promptTokenCountExact: promptExact,
                greedySampling: true,
                samplingSeedApplied: false,
                thermalPressureDetected: pressure,
                allTrialsCompletedRequestedTokens: allComplete,
                deviceClassCoarsened: coarsened
            ),
            rawTrialsFile: "trials.jsonl"
        )

        try writeOutputs(manifest: manifest, trials: trials)
    }

    // MARK: - Trial

    /// One generation pass. Timing mirrors Apple's llm-benchmark
    /// (BenchmarkMain.swift:120-154): the wall clock starts before
    /// `engine.generate`, splits at the first streamed token (prefill /
    /// time-to-first-token), and decode throughput is computed over the
    /// remaining `count - 1` tokens only. Prefill cost is therefore reported
    /// via time_to_first_token, never folded into decode_throughput.
    private func runTrial(
        index: Int,
        engine: any InferenceEngine,
        prompt: [Int32],
        sampling: SamplingConfiguration,
        maxTokens: Int
    ) async throws -> TrialRecord {
        let thermalBefore = currentThermalStateName()

        // Give the engine a moment to finish prior async cleanup, then fully
        // reset KV state — same pattern as BenchmarkMain.swift:126-127.
        try? await Task.sleep(for: .milliseconds(50))
        try await engine.reset()

        let options = InferenceOptions(maxTokens: maxTokens, includeLogits: false)
        let start = SuspendingClock.now
        let stream = try engine.generate(
            with: prompt,
            samplingConfiguration: sampling,
            inferenceOptions: options
        )

        var firstTokenSeconds: Double = 0
        var decodeStart = SuspendingClock.now
        var count = 0

        for try await _ in stream {
            if firstTokenSeconds == 0 {
                let now = SuspendingClock.now
                firstTokenSeconds = seconds(from: start, to: now)
                decodeStart = now
            }
            count += 1
        }

        let decodeSeconds = seconds(from: decodeStart, to: .now)
        let totalSeconds = seconds(from: start, to: .now)
        let decodeTokens = max(0, count - 1)
        let throughput = decodeSeconds > 0 ? Double(decodeTokens) / decodeSeconds : 0

        return TrialRecord(
            trial: index,
            promptTokens: prompt.count,
            generatedTokens: count,
            timeToFirstTokenMs: firstTokenSeconds * 1000,
            decodeTokens: decodeTokens,
            decodeSeconds: decodeSeconds,
            decodeTokensPerSecond: throughput,
            totalSeconds: totalSeconds,
            peakMemoryMb: peakResidentBytes().map { Double($0) / (1024 * 1024) },
            thermalStateBefore: thermalBefore,
            thermalStateAfter: currentThermalStateName()
        )
    }

    private func seconds(
        from start: SuspendingClock.Instant,
        to end: SuspendingClock.Instant
    ) -> Double {
        let duration = end - start
        let (secs, atto) = duration.components
        return Double(secs) + Double(atto) / 1e18
    }

    // MARK: - IO

    private func loadRunContext() throws -> RunContext? {
        guard let runContextPath else { return nil }
        let data = try Data(contentsOf: URL(fileURLWithPath: runContextPath))
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(RunContext.self, from: data)
    }

    private func loadProtocolConfig() throws -> ProtocolConfig? {
        guard let protocolConfigPath else { return nil }
        let data = try Data(contentsOf: URL(fileURLWithPath: protocolConfigPath))
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(ProtocolConfig.self, from: data)
    }

    private func writeOutputs(manifest: RunManifest, trials: [TrialRecord]) throws {
        let outURL = URL(fileURLWithPath: NSString(string: outDir).expandingTildeInPath)
        try FileManager.default.createDirectory(at: outURL, withIntermediateDirectories: true)

        let lineEncoder = JSONEncoder()
        lineEncoder.keyEncodingStrategy = .convertToSnakeCase
        lineEncoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        var lines: [String] = []
        for trial in trials {
            let data = try lineEncoder.encode(trial)
            if let line = String(data: data, encoding: .utf8) {
                lines.append(line)
            }
        }
        let trialsURL = outURL.appendingPathComponent("trials.jsonl")
        try (lines.joined(separator: "\n") + "\n").write(
            to: trialsURL, atomically: true, encoding: .utf8)

        let manifestEncoder = JSONEncoder()
        manifestEncoder.keyEncodingStrategy = .convertToSnakeCase
        manifestEncoder.outputFormatting = [
            .prettyPrinted, .sortedKeys, .withoutEscapingSlashes,
        ]
        let manifestURL = outURL.appendingPathComponent("run-manifest.json")
        try manifestEncoder.encode(manifest).write(to: manifestURL)

        print("Wrote \(trialsURL.path)")
        print("Wrote \(manifestURL.path)")
    }
}
