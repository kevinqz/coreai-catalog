# SotA Maintenance Plan

This repository should stay compact, granular and source-grounded.

## Target architecture

```txt
catalog.yaml     = model facts
artifacts.yaml   = artifact provenance and download references
sources.yaml     = source registry
schema/          = validation contracts
scripts/         = validators and doc generators
docs/            = generated or curated human views
```

## Rules

1. One model variant = one catalog entry.
2. One downloadable artifact = one artifact entry.
3. Use `unknown` instead of guessing.
4. Keep license review explicit.
5. Generate docs from YAML when possible.
6. Keep GitHub/Hugging Face provenance in `artifacts.yaml`.

## Validation

```bash
python scripts/validate.py
python scripts/generate_docs.py
python scripts/generate_artifact_docs.py
```
