# Benchmark Quality: How to Read Measurements

Benchmarks in the catalog are **normalized, environment-scoped, and append-only**. This
page explains the structure of `benchmarks.yaml`, how confidence levels work, why
measurements are never overwritten, and how to interpret throughput, latency, and
realtime factor metrics.

## Where benchmarks live

Measurements live in **`benchmarks.yaml`**, never inline in `catalog.yaml`. Model
records carry no numbers. This separation ensures:

- One model can have many measurements (different devices, compute units, precisions).
- Measurements are independently sourced and dated.
- Superseded values are retained for provenance, not silently replaced.

## Record structure

Every benchmark entry has these fields:

```yaml
- id: qwen3-5-0-8b-iphone17pro-gpu-toks      # unique, descriptive
  model_id: qwen3-5-0-8b                       # → catalog.models[].id
  metric: decode_throughput                    # what is being measured
  unit: tokens_per_second                      # unit of the value
  value: 71.9                                  # the measured number
  device: iPhone 17 Pro                        # hardware
  compute_unit: GPU                            # GPU, ANE, or CPU
  precision: inferred:int8                     # precision at inference time
  environment: iOS 27 beta, coreai-pipelined engine  # OS + runtime context
  observed: '2026-06-25'                       # when the measurement was taken
  source: john-rocky-coreai-model-zoo          # who measured it
  confidence: medium                           # trust level
  notes: Decode throughput from upstream README table.
  higher_is_better: true                       # direction of goodness
```

### Field reference

| Field | Type | Purpose |
|---|---|---|
| `id` | string | Unique identifier; convention: `{model}-{device}-{unit}-...` |
| `model_id` | string | Join key to `catalog.yaml` |
| `metric` | string | What is measured (e.g. `decode_throughput`, `inference_latency`, `realtime_factor`) |
| `unit` | string | Physical unit (e.g. `tokens_per_second`, `milliseconds`, `seconds`) |
| `value` | number or `not_published` | The measurement; `not_published` when upstream doesn't disclose a number |
| `device` | string | Hardware (e.g. `iPhone 17 Pro`, `M4 Max`) |
| `compute_unit` | enum | `GPU`, `ANE`, or `CPU` |
| `precision` | string | Inference precision (e.g. `int8`, `int4`, `fp16`, `inferred:int8`) |
| `environment` | string | OS version + runtime + conditions |
| `observed` | date | When the measurement was recorded |
| `source` | string | Who produced the measurement |
| `confidence` | enum | `high`, `medium`, `low`, or `needs_review` |
| `higher_is_better` | boolean | Whether a higher value is better |
| `superseded_by` | string (optional) | Points to the replacement record if superseded |

## Append-only semantics

The benchmark registry is **append-only**. Values are never edited or deleted. When a
new measurement supersedes an old one:

1. The **old** record stays in place but gets `confidence: needs_review` and a
   `superseded_by` pointer to the new record.
2. The **new** record is appended with its own `id`, `observed` date, and `confidence`.

### Real supersession example

```yaml
# OLD — superseded
- id: official-qwen3-0-6b-m4max-gpu-macos26-toks
  model_id: official-qwen3-0-6b
  metric: decode_throughput
  unit: tokens_per_second
  value: 1121                          # ← old value
  device: M4 Max
  environment: macOS 26
  observed: '2026-06-24'
  confidence: needs_review             # ← demoted
  superseded_by: official-qwen3-0-6b-m4max-gpu-toks
  notes: Figure recorded at catalog authoring (macOS 26); not reproduced in
    current upstream, which reports 484 tok/s on M4 Max (macOS 27 beta).

# NEW — current
- id: official-qwen3-0-6b-m4max-gpu-toks
  model_id: official-qwen3-0-6b
  value: 484                           # ← current value
  device: M4 Max
  environment: stock CoreAI runtime, M4 Max
  observed: '2026-06-25'
  confidence: medium
```

Why retain the old record? **Provenance.** If someone references the 1121 figure, the
catalog can explain exactly when and why it changed. History is never lost.

## Confidence levels

| Level | Meaning | Typical source |
|---|---|---|
| **`high`** | Verified, reproducible, or from official recipes with controlled methodology | Official recipe benchmarks with documented trial counts |
| **`medium`** | Plausible and sourced, but not independently reproduced by the catalog | Upstream README tables, community benchmarks |
| **`low`** | Value present but uncertain; partial information | `not_published` values, unverified claims |
| **`needs_review`** | Superseded by a newer measurement; retained for provenance only | Demoted via `superseded_by` |

Most catalog benchmarks carry `confidence: medium` because they are transcribed from
upstream README tables rather than independently re-measured. This is honest: the
catalog catalogues benchmarks, it does not run them.

```yaml
# Low confidence — value not published as a single number
- id: adcsr-x4-iphone17pro-gpu-latency
  value: not_published
  confidence: low
  notes: Value not published as single-tile ms; iPhone 17 Pro verified.
```

## Why measurements are environment-scoped

A benchmark number is meaningless without its context. The same model can produce
wildly different results depending on:

- **Device** — iPhone 17 Pro vs M4 Max (different thermal envelopes, memory bandwidth).
- **Compute unit** — GPU vs ANE vs CPU (see the 5× GPU-vs-ANE gap below).
- **Precision** — int4 vs int8 vs fp16 (affects both speed and quality).
- **OS / runtime version** — macOS 26 vs macOS 27 beta, stock vs pipelined engine.
- **Conditions** — warm vs cold, low-power mode, AOT compiled, streaming mode.

### Same model, three environments

```yaml
# Qwen3.5-0.8B on iPhone 17 Pro GPU
- id: qwen3-5-0-8b-iphone17pro-gpu-toks
  compute_unit: GPU
  value: 71.9                          # tok/s

# Same model on iPhone 17 Pro ANE
- id: qwen3-5-0-8b-iphone17pro-ane-toks
  compute_unit: ANE
  value: 14.7                          # tok/s — 5× slower on ANE

# Same model on M4 Max GPU
- id: qwen3-5-0-8b-m4max-gpu-toks
  compute_unit: GPU
  value: 210                           # tok/s — 3× faster on desktop GPU
```

This is why each row carries `device`, `compute_unit`, `precision`, and `environment`:
without them, the number is not actionable.

## Reading metrics: throughput vs latency vs RTF

The catalog uses three primary metric families:

| Metric | Unit | Direction | Use case | Example |
|---|---|---|---|---|
| `decode_throughput` | tok/s | higher | LLM/VLM/TTS decode speed | Qwen3-VL-2B: 33.5 tok/s (iPhone) |
| `inference_latency` | ms | lower | Detection, depth, embeddings | RF-DETR Nano: 8.6 ms (M4 Max) |
| `image_generation_latency` | seconds | lower | Diffusion image gen | FLUX.2 klein: 17.4 s (M4 Max) |
| `transcription_latency` | ms | lower | ASR wall-clock | Whisper: 180 ms (M4 Max) |
| `realtime_factor` | × | higher | ASR/TTS speed vs realtime | Parakeet: 47.9× (iPhone) |

### Throughput (`decode_throughput`)

Used for **generative models** (LLMs, VLMs, TTS). Measures tokens produced per second
during decode. **Higher is better.** Compare only within the same device + compute unit
+ precision — a 71.9 tok/s figure on iPhone GPU is not comparable to 210 tok/s on M4 Max.

### Latency (`inference_latency`, `image_generation_latency`)

Used for **non-generative models** (detectors, segmenters, embedders) and end-to-end
task timing. Measures wall-clock time for a single inference. **Lower is better.**
Also used for diffusion: FLUX.2 reports 17.4 s per 1024px image at 4 steps.

### Realtime factor (`realtime_factor`)

Used for **audio models** (ASR, TTS). Measures speed relative to realtime — RTF 10×
means the model processes audio 10× faster than it plays. **Higher is better.** RTF > 1
is real-time-capable. Example: VoxCPM TTS has RTF 0.9 on iPhone (slightly sub-realtime),
while Parakeet ASR hits RTF 47.9 (14.84s clip transcribed in 0.31s).

## Querying benchmarks

Join `benchmarks.yaml` entries by `model_id` to `catalog.yaml` entries by `id`:

```
benchmarks.benchmarks[].model_id  →  catalog.models[].id
```

Via CLI: `coreai-catalog show qwen3-vl-2b` (includes benchmark section), or
`coreai-catalog compare qwen3-vl-2b minicpm-v-4-6` for side-by-side. Via MCP:
call `get_benchmarks(model_id="qwen3-vl-2b")`.

## Summary

- Benchmarks live in `benchmarks.yaml`, not inline in model records.
- Every measurement is **environment-scoped** (device, compute unit, precision, OS).
- The registry is **append-only** — superseded values are demoted, never deleted.
- Confidence levels (`high` / `medium` / `low` / `needs_review`) tell you how much to
  trust a number.
- Choose the right metric for your task: throughput for generation, latency for
  detection, RTF for audio.

For model selection context, see [Model vs Artifact](./model-vs-artifact.md).
For license filtering before benchmarking, see [License Risk](./license-risk.md).
