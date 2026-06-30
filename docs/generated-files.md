# Generated Files Policy

Core AI Catalog uses YAML as the source of truth.

## Source files

These files are intended to be edited directly:

- `catalog.yaml`
- `artifacts.yaml`
- `sources.yaml`
- `upstreams.yaml`
- `benchmarks.yaml`
- `terms.yaml`
- `schema/*.json`
- `scripts/*.py` (validate, audit, sync_upstream, generate)

## Generated files

These files are produced by `scripts/generate.py`:

- `docs/index.md`
- `docs/model-registry.md`
- `docs/artifact-provenance.md`
- `docs/apple-terminology-map.md`
- `docs/compare/*.md`
- `dist/*.json` (catalog, artifacts, benchmarks, sources, upstreams, terms, coreai-catalog bundle)
- `dist/search-index.json`, `dist/models.jsonl`, `dist/readiness-scores.json`

Run `python scripts/generate.py` to regenerate everything, or `--docs` / `--json` for partial runs.

## Curated docs

These docs are maintained manually:

- `docs/capability-matrix.md`
- `docs/runtime-matrix.md`
- `docs/upstream-map.md`
- `docs/benchmark-map.md`
- `docs/source-map.md`
- `docs/data-model.md`
- `docs/v0.3-verification.md`
- `docs/sota-maintenance.md`
- `docs/generated-files.md`

## Rule

When a generated file is out of date, update the YAML source first and regenerate the derived file.
