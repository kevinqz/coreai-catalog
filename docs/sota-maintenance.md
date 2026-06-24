# SotA Maintenance Plan

This repository should stay compact, granular and source-grounded.

## Target architecture

```txt
catalog.yaml     = model facts
sources.yaml     = source registry
artifacts/       = artifact provenance by group/family
schema/          = validation contracts
scripts/         = validators and doc generators
docs/            = generated or curated human views
```

## Current priorities

1. Consolidate artifact provenance into normalized YAML files.
2. Generate `docs/artifact-provenance.md` from `artifacts/*.yaml`.
3. Keep `unknown` instead of guessing.
4. Review licenses with explicit source URLs.
5. Keep `catalog.yaml` focused on model metadata.
6. Keep artifact hosting and credits outside `catalog.yaml` when possible.

## Validation goals

- `python scripts/validate.py`
- `python scripts/generate_docs.py`
- `python scripts/generate_artifact_docs.py`

## Manual cleanup

Remove any temporary files created during connector testing:

```bash
rm -f docs/test.yaml docs/t2.md
```

## Next data model upgrade

Add an `artifact_ref` field to each model in `catalog.yaml`:

```yaml
artifact_ref: qwen3-5-0-8b
```

Then keep download, host and provenance data in `artifacts/`.
