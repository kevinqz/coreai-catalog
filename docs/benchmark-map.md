# Benchmark Map

`benchmarks.yaml` is the normalized benchmark registry for Core AI Catalog.

## Purpose

Benchmarks are intentionally separate from `catalog.yaml` so model facts do not become overloaded with measurement-specific rows.

`benchmarks.yaml` answers:

- which model was measured?
- what metric was measured?
- on what device?
- using which compute unit?
- what source reported the value?
- how confident is the record?

## Current status

The registry holds normalized decode-throughput records (iPhone 17 Pro GPU/ANE and M4 Max GPU) plus image-generation, segmentation and transcription latency records, traced to the upstream `john-rocky/coreai-model-zoo` README and `official/` performance tables. It covers every model the upstream reports a measurement for.

## Record shape

```yaml
- id: qwen3-5-0-8b-iphone17pro-gpu-toks
  model_id: qwen3-5-0-8b
  metric: decode_throughput
  unit: tokens_per_second
  value: 71.9
  device: iPhone 17 Pro
  compute_unit: GPU
  precision: unknown
  source: john-rocky-coreai-model-zoo
  confidence: medium
  notes: Decode throughput from upstream README table (iOS 27 / macOS 27 beta, coreai-pipelined GPU engine).
```

## Rules

1. Add benchmark records only when a source is traceable.
2. Keep measurements separate by device, compute unit and precision.
3. Use `unknown` rather than guessing precision or runtime context.
4. Put caveats in `notes`.
5. Use `confidence: needs_review` when measurement context is incomplete.

## Future work

- Add prefill latency if source data exists.
- Add memory footprint and artifact-size measurements.
- Add QAT-variant throughput rows where the upstream reports them.
- Reconcile the `official-qwen3-0-6b` inline-vs-upstream discrepancy (1121 macOS-26 vs 484 M4 Max).
- Add source line references where practical.
