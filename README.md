# Core AI Catalog

A compact, source-grounded catalog of Apple Core AI models.

## Goal

Map Apple Core AI model artifacts with complete, granular and verifiable metadata.

This catalog tracks models, families, capabilities, modalities, artifact format, size and variants, runtime requirements, device support, benchmark metadata, licenses, source links, Hugging Face artifact references, GitHub and Hugging Face attribution, official Apple recipe conversion status, and verification status.

## Non-goals

This repository does not define model workflows yet.

## Source of truth

- `catalog.yaml` — model metadata
- `artifacts.yaml` — artifact provenance, GitHub/Hugging Face ownership, download references
- `sources.yaml` — source registry
- `CREDITS.md` — human attribution

Markdown files in `docs/` are generated or curated views.

## Current scope

- Models: 49
- Artifact records: 49
- Source records: 13

## Official Apple recipe conversions

Entries with `source_group: official` refer to artifacts described upstream as conversions from Apple's official `apple/coreai-models` recipes.

## Validation

```bash
pip install -r requirements.txt
python scripts/validate.py
python scripts/generate_docs.py
python scripts/generate_artifact_docs.py
```

## Upstream

Primary upstream repository: https://github.com/john-rocky/coreai-model-zoo
