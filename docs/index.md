# Core AI Catalog Docs

## Core views

- [Model Registry](./model-registry.md)
- [Capability Matrix](./capability-matrix.md)
- [Runtime Matrix](./runtime-matrix.md)
- [Artifact Provenance](./artifact-provenance.md)
- [Upstream Map](./upstream-map.md)
- [Benchmark Map](./benchmark-map.md)
- [Source Map](./source-map.md)
- [Generated Files Policy](./generated-files.md)
- [v0.3 Verification Checklist](./v0.3-verification.md)
- [SotA Maintenance Plan](./sota-maintenance.md)

## Counts

- Models: 49
- Artifacts: 49
- Sources: 13
- Upstream taxonomy layers: 7
- Benchmark records: 36

## Source of truth

- `../catalog.yaml`
- `../artifacts.yaml`
- `../sources.yaml`
- `../upstreams.yaml`
- `../benchmarks.yaml`
- `../CREDITS.md`

## Generated exports

Run:

```bash
python scripts/export_json.py
```

This generates JSON views under `dist/`.
