# Generated Files Policy

Core AI Catalog uses YAML as the source of truth.

## Source files

These files are intended to be edited directly:

- `catalog.yaml`
- `artifacts.yaml`
- `sources.yaml`
- `upstreams.yaml`
- `benchmarks.yaml`
- `schema/*.json`
- `scripts/*.py`

## Generated files

These files or folders are produced by scripts:

- `docs/model-registry.md` from `scripts/generate_docs.py`
- `docs/artifact-provenance.md` from `scripts/generate_artifact_docs.py`
- `dist/*.json` from `scripts/export_json.py`

## Curated docs

These docs are maintained manually until generators are expanded:

- `docs/index.md`
- `docs/capability-matrix.md`
- `docs/runtime-matrix.md`
- `docs/upstream-map.md`
- `docs/benchmark-map.md`
- `docs/source-map.md`
- `docs/v0.3-verification.md`
- `docs/sota-maintenance.md`
- `docs/generated-files.md`

## Rule

When a generated file is out of date, update the YAML source first and regenerate the derived file.
