# CoreAIBenchRunner

Reference benchmark runner for the coreai-catalog benchmark protocol
(`benchmarks/protocol-config.json` v1.0). Produces the raw per-trial JSONL
and the signed-manifest input that `coreai_catalog/bench.py` assembles into
a `benchmarks.jsonl` candidate line (`extraction_method:
app_benchmark_protocol`).

## Requirements

- **macOS 27.0 or newer.** The `apple/coreai-models` runtime declares
  `platforms: [.macOS("27.0"), .iOS("27.0")]` (upstream `Package.swift:12`),
  so this package does too. On macOS 26.x the package resolves but will not
  build or run.
- Xcode / Swift toolchain with the macOS 27 SDK.
- An installed model artifact (`coreai-catalog install <model-id>`).

## Build

```sh
cd bench/CoreAIBenchRunner
swift build -c release
# binary: .build/release/coreai-bench-runner
```

## Run (usually via the orchestrator)

The supported entry point is the Python orchestrator, which resolves the
installed artifact, collects sha256/revision provenance from
`artifacts.yaml`, and validates the outputs:

```sh
python3 -m coreai_catalog.bench <model-id>
```

Direct invocation:

```sh
.build/release/coreai-bench-runner \
  --model-path ~/.coreai-catalog/models/<model-id>/artifacts/<bundle-dir> \
  --model-id <model-id> \
  --protocol-config ../../benchmarks/protocol-config.json \
  --run-context run-context.json \
  --out-dir bench-out
```

Outputs in `--out-dir`:

- `trials.jsonl` — one JSON object per measured trial (raw timings, peak
  memory, per-trial thermal state).
- `run-manifest.json` — runner version, protocol version, model id,
  artifact revision + sha256 root (echoed from the orchestrator's run
  context, never invented), seed, freshness nonce, thermal states, and
  self-check flags. This file is the payload for signing/attestation.

## Scope and honesty notes

- Implements the protocol's LLM metrics (`decode_throughput`,
  `time_to_first_token`). The other protocol metrics (diffusion, speech,
  segmentation, detection) need their own harnesses and are not implemented.
- Sampling is greedy (`SamplingConfiguration(temperature: 0)`), the only
  deterministic path the upstream API offers; the public API has no seed
  parameter, so `--seed` is recorded in the manifest with
  `sampling_seed_applied: false`.
- Decode throughput is measured over the decode window only (first streamed
  token → last token); prefill cost is reported separately as
  `time_to_first_token`. This mirrors Apple's own `llm-benchmark` tool
  (upstream `swift/Sources/Tools/benchmark/BenchmarkMain.swift`).
- The raw device model (`hw.model`) is compared against the protocol's
  coarsening table in-process and printed to stderr only; it is never
  written to any output file.
