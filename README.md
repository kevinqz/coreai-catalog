# Core AI Catalog

A compact, source-grounded catalog of Apple Core AI models, artifacts, upstreams, benchmarks and provenance.

Core AI Catalog maps Apple Core AI-compatible model artifacts with granular metadata, source links, Hugging Face artifact references, GitHub/Hugging Face attribution, runtime requirements, device support, benchmark records and verification status.

> YAML is the source of truth. Markdown is the human view. JSON is the generated machine/API export.

## Status

**Version:** v0.3 foundation

v0.3 moves the project from structural completeness to verification depth. The catalog now separates model facts, converted artifact provenance, source taxonomy, benchmark records and generated exports.

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
- which benchmark records exist
- which fields are confirmed and which remain unknown

## Current scope

| Area | Count / status |
|---|---:|
| Model records | 49 |
| Artifact provenance records | 49 |
| Source records | 13 |
| Main upstreams | 2 |
| Upstream taxonomy layers | 7 |
| Benchmark records | 39 |
| JSON exports | generated via script |

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
├── upstreams.yaml
├── benchmarks.yaml
├── requirements.txt
├── schema/
│   ├── model.schema.json
│   ├── artifact.schema.json
│   ├── upstream.schema.json
│   └── benchmark.schema.json
├── scripts/
│   ├── validate.py
│   ├── generate_docs.py
│   ├── generate_artifact_docs.py
│   └── export_json.py
├── docs/
│   ├── index.md
│   ├── model-registry.md
│   ├── capability-matrix.md
│   ├── runtime-matrix.md
│   ├── artifact-provenance.md
│   ├── upstream-map.md
│   ├── benchmark-map.md
│   ├── source-map.md
│   ├── v0.3-verification.md
│   ├── sota-maintenance.md
│   └── generated-files.md
└── .github/
    └── workflows/
        └── validate.yml
```

Generated JSON exports are written to `dist/` when `scripts/export_json.py` runs.

## Source of truth

| File | Purpose |
|---|---|
| `catalog.yaml` | Model facts: name, family, capabilities, modalities, size, runtime, device support, license status and verification status. Measurements live in `benchmarks.yaml`, not here. |
| `artifacts.yaml` | Converted artifact provenance: GitHub conversion source, Hugging Face owner/repo/url and official recipe status. |
| `sources.yaml` | Compact registry of primary/supporting sources already used by the catalog. |
| `upstreams.yaml` | Source taxonomy for framework, conversion, artifact host, benchmark, sample, original model and license sources. |
| `benchmarks.yaml` | Normalized benchmark records by model, metric, device, compute unit and source. |
| `CREDITS.md` | Human-readable attribution for GitHub and Hugging Face users/repositories. |
| `schema/*.json` | Validation contracts for model, artifact, upstream and benchmark records. |
| `docs/*.md` | Generated or curated human views. |
| `dist/*.json` | Generated machine-readable exports. |

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

An artifact entry in `artifacts.yaml` represents converted artifact provenance and hosting:

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

An upstream entry in `upstreams.yaml` represents source taxonomy:

```yaml
- id: qwen
  title: Qwen original model family
  category: original_model
  platform: huggingface
  owner: Qwen
  url: https://huggingface.co/Qwen
  trust: original_model_primary
  applies_to:
    - qwen3-5-0-8b
    - qwen3-vl-2b
```

A benchmark entry in `benchmarks.yaml` represents a normalized measurement:

```yaml
- id: qwen3-5-0-8b-iphone17pro-gpu-toks
  model_id: qwen3-5-0-8b
  metric: decode_throughput
  unit: tokens_per_second
  value: 71.9
  device: iPhone 17 Pro
  compute_unit: GPU
  environment: iOS 27 beta, coreai-pipelined engine
  observed: '2026-06-25'
  source: john-rocky-coreai-model-zoo
  confidence: medium
```

Measurements are the single source of truth in `benchmarks.yaml` (model records carry no inline numbers). Each row is environment-scoped and append-only: values that differ across OS/runtime versions are kept as separate dated records, and a superseded value is retained with `confidence: needs_review` and a `superseded_by` pointer rather than overwritten.

## Source layers

| Layer | File/category | Purpose |
|---|---|---|
| Model facts | `catalog.yaml` | What the model is and what it does. |
| Converted artifact | `artifacts.yaml` | Where the Core AI artifact lives and who converted/hosts it. |
| Framework/runtime | `upstreams.yaml > framework_sources` | Apple Core AI, Core ML and tooling context. |
| Original model | `upstreams.yaml > original_model_sources` | Original creators/model-family sources. |
| License | `upstreams.yaml > license_sources` | License documents and review flags. |
| Benchmarks | `benchmarks.yaml` | Measurement rows, source IDs and confidence. |
| Human docs | `docs/*.md` | Tables, maps and curated summaries. |
| Machine exports | `dist/*.json` | Generated JSON outputs for agents/APIs. |

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

## Original model attribution

Original model creators are tracked separately from converted artifact hosts. This avoids conflating:

- original model creator
- Apple official recipe source
- community conversion source
- Hugging Face artifact host
- license source

Examples:

| Model family | Original upstream | Converted artifact host |
|---|---|---|
| Qwen | `Qwen` | `mlboydaisuke` |
| Gemma | `google` | `mlboydaisuke` |
| Mistral | `mistralai` | `mlboydaisuke` |
| SAM | `facebook` / Meta | `mlboydaisuke` |
| RF-DETR | `Roboflow` | `mlboydaisuke` |

See `upstreams.yaml` and `docs/upstream-map.md`.

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

## Validation and generation

Install dependencies:

```bash
pip install -r requirements.txt
```

Validate records:

```bash
python scripts/validate.py
```

Regenerate Markdown docs:

```bash
python scripts/generate_docs.py
python scripts/generate_artifact_docs.py
```

Export JSON:

```bash
python scripts/export_json.py
```

The GitHub Actions workflow runs validation, docs generation and JSON export on push and pull request.

## Documentation

`generated` docs are produced from the YAML source by scripts and must not be
hand-edited; `curated` docs are maintained manually (see `docs/generated-files.md`).

| Doc | Type | Description |
|---|---|---|
| `docs/index.md` | curated | Docs entry point and file map. |
| `docs/model-registry.md` | generated | Human-readable model table (`scripts/generate_docs.py`). |
| `docs/artifact-provenance.md` | generated | Artifact ownership and hosting view (`scripts/generate_artifact_docs.py`). |
| `docs/capability-matrix.md` | curated | Models grouped by capability. |
| `docs/runtime-matrix.md` | curated | Runtime concepts and flags. |
| `docs/upstream-map.md` | curated | Framework/original-model/license upstream map. |
| `docs/benchmark-map.md` | curated | Benchmark registry explanation. |
| `docs/source-map.md` | curated | Source and upstream map. |
| `docs/v0.3-verification.md` | curated | Verification checklist for v0.3. |
| `docs/sota-maintenance.md` | curated | Maintenance plan and data-model direction. |
| `docs/generated-files.md` | curated | Generated vs curated file policy. |

## Attribution

This project is a catalog and attribution layer. It does not claim ownership of upstream model artifacts or source repositories.

Primary credits are recorded in:

- `CREDITS.md`
- `sources.yaml`
- `artifacts.yaml`
- `upstreams.yaml`

Key credited sources include:

- `john-rocky/coreai-model-zoo`
- `john-rocky/CoreML-Models`
- `apple/coreai-models`
- `apple/coremltools`
- `john-rocky/apple-silicon-llm-bench`
- `john-rocky/coreai-samples`
- Hugging Face user `mlboydaisuke`
- original model creators listed in `upstreams.yaml`

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
5. Keep `artifacts.yaml` focused on converted artifact provenance and hosting.
6. Keep `upstreams.yaml` focused on original model, framework, license and benchmark sources.
7. Keep `benchmarks.yaml` focused on normalized measurement records.
8. Keep `sources.yaml` focused on compact source registry.
9. Generate Markdown and JSON views from YAML whenever possible.
10. Credit original model creator, conversion source and artifact host separately.
11. Update `last_verified` when a source is rechecked.

## Roadmap

Current milestone:

- v0.3 — validation depth, upstream taxonomy, benchmark registry and JSON exports.

Next milestone:

- v0.4 — exact model-card URL for every original model, exact license URL per model, artifact checksums/hashes where available, and generated JSON release artifacts.

Later:

- Split large YAML files into `data/models/*.yaml` if the catalog grows significantly.
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

Primary community upstream:

- https://github.com/john-rocky/coreai-model-zoo

Official Apple recipe upstream:

- https://github.com/apple/coreai-models

Additional upstream taxonomy:

- `upstreams.yaml`
- `docs/upstream-map.md`
