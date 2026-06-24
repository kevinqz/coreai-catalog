# Core AI Catalog

A compact, source-grounded catalog of Apple Core AI models.

## Goal

Map Apple Core AI model artifacts with complete, granular and verifiable metadata.

This catalog tracks:

- models
- families
- capabilities
- modalities
- artifact format
- size and variants
- runtime requirements
- device support
- benchmark metadata
- licenses
- source links
- Hugging Face artifact references
- GitHub and Hugging Face attribution
- official Apple recipe conversion status
- verification status

## Non-goals

This repository does not define workflows yet.

## Source of truth

- `catalog.yaml` — model metadata
- `sources.yaml` — source registry
- `CREDITS.md` — GitHub and Hugging Face attribution

Markdown files in `docs/` are generated or curated views.

## Core rule

Every model entry should include:

- source
- status
- confidence
- maturity
- last verified date
- GitHub upstream provenance
- Hugging Face artifact provenance when available

## Official Apple recipe conversions

Entries with `source_group: official` refer to artifacts described upstream as unmodified conversions from Apple's official `apple/coreai-models` recipes.

## Credits

See `CREDITS.md`.

## Docs

See `docs/index.md` for model tables, runtime notes, sources and Hugging Face artifact references.

## Upstream

Primary upstream repository:

https://github.com/john-rocky/coreai-model-zoo
