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
- in what environment, and on what date, was it observed?

## Single source of truth

`benchmarks.yaml` is the only place measurement values live. `catalog.yaml` model
records carry no inline benchmark numbers, so the two cannot drift. Any consumer that
needs a measurement joins on `model_id`.

## Versioning and provenance

Measurements are environment-scoped and append-only:

- Each record carries `environment` (OS / runtime context) and `observed` (date).
- Values that differ across OS or runtime versions are kept as separate records, not
  treated as conflicts.
- When upstream changes a value, the prior record is retained and marked
  `confidence: needs_review` with `superseded_by` pointing at the current record.
  Sourced measurements are never overwritten or deleted.

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
  environment: iOS 27 beta, coreai-pipelined engine
  observed: '2026-06-25'
  source: john-rocky-coreai-model-zoo
  confidence: medium
  superseded_by: null
  notes: Decode throughput from upstream README table.
```

## Rules

1. Benchmarks live only in `benchmarks.yaml`; never store measurement values inline in `catalog.yaml`.
2. Add records only when the value is traceable to a source.
3. Keep measurements separate by device, compute unit, precision and environment.
4. Record `environment` and `observed` for every measurement.
5. Append, never overwrite: supersede a stale value with `superseded_by` + `confidence: needs_review`.
6. Use `unknown` rather than guessing precision or runtime context; put caveats in `notes`.

## Future work

- Add prefill latency if source data exists.
- Add memory footprint and artifact-size measurements.
- Add source line references where practical.
