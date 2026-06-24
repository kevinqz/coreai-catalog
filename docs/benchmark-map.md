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

The benchmark registry is an initial v0.3 scaffold. It includes a small set of normalized throughput examples from the upstream `john-rocky/coreai-model-zoo` README.

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
  notes: Reported in upstream README throughput table.
```

## Rules

1. Add benchmark records only when a source is traceable.
2. Keep measurements separate by device, compute unit and precision.
3. Use `unknown` rather than guessing precision or runtime context.
4. Put caveats in `notes`.
5. Use `confidence: needs_review` when measurement context is incomplete.

## Future work

- Expand all throughput rows from upstream tables.
- Add prefill latency if source data exists.
- Add memory footprint and artifact-size measurements.
- Add generation-time metrics for image/audio models.
- Add source line references where practical.
