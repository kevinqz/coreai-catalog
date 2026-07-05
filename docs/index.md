# Core AI Catalog Docs

## Core views

- [Model Registry](./model-registry.md)
- [Capability Matrix](./capability-matrix.md)
- [Runtime Matrix](./runtime-matrix.md)
- [Artifact Provenance](./artifact-provenance.md)
- [Upstream Map](./upstream-map.md)
- [Benchmark Map](./benchmark-map.md)
- [Source Map](./source-map.md)
- [Apple Terminology Map](./apple-terminology-map.md)
- [Data Model](./data-model.md)
- [Generated Files Policy](./generated-files.md)
- [v0.3 Verification Checklist](./v0.3-verification.md)
- [SotA Maintenance Plan](./sota-maintenance.md)

## Counts

- Models: 83
- Artifacts: 83
- Sources: 24
- Upstream taxonomy entries: 68
- Benchmark records: 65
- Terminology records: 42

> Counts are generated automatically by `scripts/generate.py`. Never edit this section manually.

## Source of truth

- `../catalog.yaml`
- `../artifacts.yaml`
- `../sources.yaml`
- `../upstreams.yaml`
- `../benchmarks.jsonl`
- `../terms.yaml`
- `../CREDITS.md`

## Generated exports

Run:

```bash
python scripts/generate.py --json
```

This generates JSON views under `dist/`.

