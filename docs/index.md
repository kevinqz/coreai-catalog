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

- Models: 65
- Artifacts: 65
- Sources: 13
- Upstream taxonomy entries: 53
- Benchmark records: 61
- Terminology records: 42

> Counts are generated automatically by `scripts/generate_index.py`. Never edit this section manually.

## Source of truth

- `../catalog.yaml`
- `../artifacts.yaml`
- `../sources.yaml`
- `../upstreams.yaml`
- `../benchmarks.yaml`
- `../terms.yaml`
- `../CREDITS.md`

## Generated exports

Run:

```bash
python scripts/export_json.py
```

This generates JSON views under `dist/`.

