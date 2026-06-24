# Core AI Catalog

A compact, source-grounded catalog of Apple Core AI models, artifacts and provenance.

Core AI Catalog maps Apple Core AI-compatible model artifacts with granular metadata, source links, Hugging Face artifact references, GitHub/Hugging Face attribution, runtime requirements, device support and verification status.

> YAML is the source of truth. Markdown is the human view. Scripts generate derived docs.

## Why this exists

Apple Core AI model artifacts are spread across upstream repositories, model cards, official recipe conversions, community ports and Hugging Face artifact repos. This project organizes that information into a compact, machine-readable catalog that can be consumed by humans, agents and automation.

The goal is not to run models directly. The goal is to know, precisely and traceably:

- what model exists
- where it came from
- what it can do
- what it receives and outputs
- where the artifact is hosted
- who should be credited
- whether it is an official Apple recipe conversion or a community zoo port
- what runtime/device constraints are known
- which fields are confirmed and which remain unknown

## Current scope

| Area | Count |
|---|---:|
| Model records | 49 |
| Artifact provenance records | 49 |
| Source records | 13 |
| Main upstreams | 2 |

Main upstreams:

- `john-rocky/coreai-model-zoo`
- `apple/coreai-models`

Primary Hugging Face artifact owner currently mapped:

- `mlboydaisuke`

## Repository structure

```txt
coreai-catalog/
├── README.md
├── CREDITS.md
├── catalog.yaml
├── artifacts.yaml
├── sources.yaml
├── requirements.txt
├── schema/
│   ├── model.schema.json
│   └── artifact.schema.json
├── scripts/
│   ├── validate.py
│   ├── generate_docs.py
│   └── generate_artifact_docs.py
├── docs/
│   ├── index.md
│   ├── model-registry.md
│   ├── capability-matrix.md
│   ├── runtime-matrix.md
│   ├── artifact-provenance.md
│   ├── source-map.md
│   └── sota-maintenance.md
└── .github/
    └── workflows/
        └── validate.yml
```

## Source of truth

| File | Purpose |
|---|---|
| `catalog.yaml` | Model facts: name, family, capabilities, modalities, size, runtime, device support, benchmark notes, license status and verification status. |
| `artifacts.yaml` | Artifact provenance: GitHub source owner/repo/path, Hugging Face owner/repo/url and official recipe status. |
| `sources.yaml` | Registry of primary sources and supporting sources. |
| `CREDITS.md` | Human-readable attribution for GitHub and Hugging Face users/repositories. |
| `schema/*.json` | Validation contracts for model and artifact records. |
| `docs/*.md` | Generated or curated human views. |

## Core data model

A model entry in `catalog.yaml` represents model metadata:

```yaml
- id: qwen3-5-0-8b
  name: Qwen3.5-0.8B
  family: Qwen
  source_group: zoo
  capabilities:
    - chat
    - text-generation
  modalities:
    input:
      - text
    output:
      - text
  artifact:
    format: aimodel
    availability: available
  runtime:
    runtime_name: apple-core-ai
    runner: CoreAIRunner
  status: confirmed
  confidence: medium
```

An artifact entry in `artifacts.yaml` represents provenance and hosting:

```yaml
- id: qwen3-5-0-8b
  group: zoo
  github:
    owner: john-rocky
    repo: coreai-model-zoo
    path: https://github.com/john-rocky/coreai-model-zoo/blob/main/zoo/qwen3.5.md
  huggingface:
    owner: mlboydaisuke
    repo: qwen3.5-0.8B-CoreAI
    url: https://huggingface.co/mlboydaisuke/qwen3.5-0.8B-CoreAI
  is_official_recipe: false
```

## Model groups

| Group | Meaning |
|---|---|
| `zoo` | Community model port from `john-rocky/coreai-model-zoo`. |
| `official` | Artifact described upstream as an Apple official recipe conversion from `apple/coreai-models`. |
| `external` | External source, not yet used by the current catalog. |
| `unknown` | Not classified yet. |

## Official Apple recipe conversions

Entries with `source_group: official` in `catalog.yaml` and `is_official_recipe: true` in `artifacts.yaml` are treated as official Apple recipe conversion artifacts.

These entries credit:

- GitHub source: `apple/coreai-models`
- Artifact host: `mlboydaisuke` on Hugging Face

Current official entries include:

- gpt-oss-20B
- Qwen3 0.6B
- Qwen3 4B
- Qwen3 8B
- Gemma 3 4B IT
- Gemma 3 12B IT
- Mistral 7B v0.3
- FLUX.2 klein 4B
- SAM 3
- Whisper large-v3-turbo

## Capabilities covered

The catalog currently covers:

- chat / text generation
- instruction following
- reasoning / agentic LLMs
- MoE LLMs
- vision-language models
- document OCR
- audio understanding
- text-to-speech
- speech-to-text
- embeddings
- reranking
- object detection
- instance segmentation
- promptable segmentation
- monocular depth
- image generation
- super-resolution

## Devices and runtime metadata

The catalog tracks known runtime/device facts when available:

- Apple Core AI artifact format
- `.aimodel` availability
- stock runtime vs community runtime
- runner name
- tokenizer requirement
- processor requirement
- custom Metal kernel requirement
- patch/workaround requirement
- AOT requirement
- iPhone/iPad/Mac support
- Mac-only status

Unknown or unverified values are intentionally kept as `unknown` instead of guessed.

## Validation

Install dependencies:

```bash
pip install -r requirements.txt
```

Validate model and artifact records:

```bash
python scripts/validate.py
```

Regenerate docs:

```bash
python scripts/generate_docs.py
python scripts/generate_artifact_docs.py
```

The GitHub Actions workflow also runs validation and doc generation on push and pull request.

## Generated docs

| Doc | Description |
|---|---|
| `docs/model-registry.md` | Human-readable model table. |
| `docs/capability-matrix.md` | Models grouped by capability. |
| `docs/runtime-matrix.md` | Runtime concepts and flags. |
| `docs/artifact-provenance.md` | Artifact ownership and hosting view. |
| `docs/source-map.md` | Source and upstream map. |
| `docs/sota-maintenance.md` | Maintenance plan and data-model direction. |

## Attribution

This project is a catalog and attribution layer. It does not claim ownership of upstream model artifacts or source repositories.

Primary credits are recorded in:

- `CREDITS.md`
- `sources.yaml`
- `artifacts.yaml`

Key credited sources include:

- `john-rocky/coreai-model-zoo`
- `john-rocky/CoreML-Models`
- `apple/coreai-models`
- `john-rocky/apple-silicon-llm-bench`
- `john-rocky/coreai-samples`
- Hugging Face user `mlboydaisuke`

## License handling

Licenses are tracked per model when known. Some entries are marked as `check_license` when commercial-use terms need explicit review.

Important rule:

> The repository license, upstream code license, model license and artifact-hosting license may differ.

For sensitive licenses such as Gemma Terms, Meta SAM License, LFM Open License or OpenRAIL-style licenses, treat `commercial_use: check_license` as requiring manual review before use.

## Maintenance rules

1. One meaningful model variant should have one catalog entry.
2. Do not collapse variants when size, device support, runtime, quantization, license or artifact changes.
3. Use `unknown` instead of guessing.
4. Keep `catalog.yaml` focused on model facts.
5. Keep `artifacts.yaml` focused on provenance and hosting.
6. Keep `sources.yaml` focused on source registry.
7. Generate Markdown views from YAML whenever possible.
8. Credit both GitHub and Hugging Face sources.
9. Prefer primary sources over secondary summaries.
10. Update `last_verified` when a source is rechecked.

## Roadmap

Near-term:

- Add richer license URLs per model.
- Add checksum/hash fields where upstream provides them.
- Add model-card source line references where practical.
- Add CI check that generated docs are up to date.
- Add artifact URL reachability checks.
- Add normalized benchmark schema.

Later:

- Split large YAML files into `data/models/*.yaml` if the catalog grows significantly.
- Export `catalog.json` and `artifacts.json` for API/agent consumption.
- Add a small static site or searchable UI.
- Add periodic source verification.

## Non-goals

This repository does not currently define:

- model workflows
- app logic
- inference pipelines
- benchmarking harnesses
- model conversion scripts
- runtime implementations

Those belong in separate repositories or future layers.

## Upstream

Primary upstream repository:

- https://github.com/john-rocky/coreai-model-zoo

Official recipe upstream:

- https://github.com/apple/coreai-models
