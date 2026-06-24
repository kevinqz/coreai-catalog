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
- verification status

## Non-goals

This repository does not define workflows yet.

## Source of truth

- `catalog.yaml` — model metadata
- `sources.yaml` — source registry

Markdown files in `docs/` are generated or curated views.

## Core rule

Every model entry must include:

- source
- status
- confidence
- maturity
- last verified date

## Upstream

Primary upstream repository:

https://github.com/john-rocky/coreai-model-zoo
