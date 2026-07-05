# Core AI Catalog

[![PyPI](https://img.shields.io/pypi/v/coreai-catalog.svg)](https://pypi.org/project/coreai-catalog/)
![CI](https://github.com/kevinqz/coreai-catalog/actions/workflows/validate.yml/badge.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

🌐 **[Live site: kevinqz.github.io/coreai-catalog](https://kevinqz.github.io/coreai-catalog/)** — searchable web UI with model cards, filters, and benchmarks.

A compact, source-grounded catalog of Apple Core AI models, artifacts, upstreams, benchmarks, provenance and a verified Apple AI terminology layer.

Core AI Catalog maps Apple Core AI-compatible model artifacts with granular metadata, source links, Hugging Face artifact references, GitHub/Hugging Face attribution, runtime requirements, device support, benchmark records and verification status.

> YAML is the source of truth. Markdown is the human view. JSON is the generated machine/API export.

## Scope and disclaimer

This catalog tracks **open-source models and their Apple Core AI artifacts** — provenance, runtime, licenses and benchmarks — plus a verified reference layer of Apple AI terminology grounded in official Apple sources. It does not redistribute model weights, re-document Apple's APIs, or treat Apple's proprietary Foundation Models as downloadable artifacts.

Not affiliated with or endorsed by Apple. `commercial_use` fields are triage labels, not legal advice or permissions — always verify the upstream model, code and artifact licenses yourself.

## Status

**Version:** v2.2.3 — [PyPI](https://pypi.org/project/coreai-catalog/) · [Live site](https://kevinqz.github.io/coreai-catalog/) · [CI](https://github.com/kevinqz/coreai-catalog/actions/workflows/validate.yml)

95 Apple Core AI models with artifact provenance, benchmarks, verified terminology, per-entry suitability facets (deployability / lifecycle / entry_completeness), and an MCP server for agent-native model discovery, comparison, and recommendation.

**Version contract:** PyPI = GitHub tag = `catalog.yaml` = `agent.json` = `openapi.yaml` = `README.md`. All surfaces carry the same version number.

## Quick Start

```bash
pip install coreai-catalog

# Find the right model for your task
coreai-catalog recommend --task "private OCR on iPhone" --license likely

# Install it (downloads .aimodel from Hugging Face)
coreai-catalog install unlimited-ocr

# Compare alternatives
coreai-catalog compare unlimited-ocr qwen3-vl-2b
```

See [`examples/`](./examples/) for Swift integration snippets (OCR, VLM chat, embeddings/RAG).

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
| Model records | 95 |
| Artifact provenance records | 96 |
| Source records | 26 |
| Main upstreams | 2 |
| Upstream taxonomy entries | 68 |
| Benchmark records | 65 |
| Terminology records | 42 |
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
├── AGENTS.md
├── CONTRIBUTING.md
├── CREDITS.md
├── pyproject.toml
├── catalog.yaml
├── artifacts.yaml
├── sources.yaml
├── upstreams.yaml
├── benchmarks.jsonl
├── terms.yaml
├── requirements.txt
├── schema/
│   ├── model.schema.json
│   ├── artifact.schema.json
│   ├── upstream.schema.json
│   ├── benchmark.schema.json
│   └── term.schema.json
├── scripts/
│   ├── validate.py
│   ├── audit.py
│   ├── deep_audit.py
│   ├── derive_fields.py
│   ├── generate.py
│   ├── sync_upstream.py
│   └── validate_links.py
├── coreai_catalog/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── catalog.py
│   ├── exports.py
│   └── installer.py
├── mcp_server/
│   ├── __init__.py
│   └── server.py
├── skills/
│   ├── coreai-model-selection/
│   └── coreai-license-triage/
├── llms.txt
├── docs/
│   ├── index.md
│   ├── model-registry.md
│   ├── capability-matrix.md
│   ├── runtime-matrix.md
│   ├── artifact-provenance.md
│   ├── upstream-map.md
│   ├── benchmark-map.md
│   ├── source-map.md
│   ├── apple-terminology-map.md
│   ├── data-model.md
│   ├── compare/
│   ├── v0.3-verification.md
│   ├── sota-maintenance.md
│   └── generated-files.md
└── .github/
    └── workflows/
        └── validate.yml
```

JSON exports are generated by `scripts/generate.py` and committed to `dist/`. They are available via raw GitHub URLs (e.g. `https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/catalog.json`) without cloning the repo. Current exports include `catalog.json`, `artifacts.json`, `benchmarks.json`, `benchmarks-aggregate.json`, `terms.json`, `sources.json`, `upstreams.json`, `search-index.json`, `readiness-scores.json`, `transforms-graph.json`, `model-manifest.json`, and `coreai-catalog.json`.

## Benchmark provenance

Benchmark records are stored as JSONL with per-entry provenance fields (`extraction_method`, `confidence`, `device_class`, `device_verified`) so every measurement traces to a verifiable source. The intake pipeline is fully signed and automated:

- **Signed intake** — submissions are signed with Ed25519, validated by a GitHub Action (signature + schema + outlier check), and auto-merged into the public dataset if all checks pass.
- **Privacy-preserving** — device identifiers are coarsened to chip class (e.g. `A18 Pro`), no PII is collected or retained (see [`docs/privacy-policy.md`](./docs/privacy-policy.md)), and aggregate statistics with fewer than 3 samples are suppressed to prevent de-anonymization (k=3).
- **Device coarsening** — raw model identifiers (`iPhone17,1`) are mapped to chip-class labels before publication; time precision is stripped to date-only.

See [`docs/anchor-cohort.md`](./docs/anchor-cohort.md) for the anchor-device reference cohort and [`docs/privacy-policy.md`](./docs/privacy-policy.md) for the full data-collection and consent policy.

## Source of truth

| File | Purpose |
|---|---|
| `catalog.yaml` | Model facts: name, family, capabilities, modalities, size, runtime, device support, license status and verification status. Measurements live in `benchmarks.jsonl`, not here. |
| `artifacts.yaml` | Converted artifact provenance: GitHub conversion source, Hugging Face owner/repo/url and official recipe status. |
| `sources.yaml` | Compact registry of primary/supporting sources already used by the catalog. |
| `upstreams.yaml` | Source taxonomy for framework, conversion, artifact host, benchmark, sample, original model and license sources. |
| `benchmarks.jsonl` | Normalized benchmark records by model, metric, device, compute unit and source (append-only JSONL, one JSON object per line). |
| `terms.yaml` | Verified Apple AI terminology, tagged by ecosystem layer, each citing an official Apple source. |
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
  officiality:
    apple_export_recipe: false
    apple_hosted_artifact: false
    community_packaged: true
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

A benchmark entry in `benchmarks.jsonl` represents a normalized measurement
(one JSON object per line):

```json
{"id": "qwen3-5-0-8b-iphone17pro-gpu-toks", "model_id": "qwen3-5-0-8b", "metric": "decode_throughput", "value": 71.9, "unit": "tokens_per_second", "device_class": "A18 Pro", "os_major": "27", "compute_unit": "GPU", "extraction_method": "upstream_readme_manual", "device_verified": false, "confidence": "medium", "observed_date": "2026-06-25", "source": "john-rocky-coreai-model-zoo", "notes": "Decode throughput from upstream README table."}
```

Measurements are the single source of truth in `benchmarks.jsonl` (model records carry no inline numbers). Each row is environment-scoped and append-only: values that differ across OS/runtime versions are kept as separate dated records, and a superseded value is retained with `confidence: needs_review` and a `superseded_by` pointer rather than overwritten.

## Source layers

| Layer | File/category | Purpose |
|---|---|---|
| Model facts | `catalog.yaml` | What the model is and what it does. |
| Converted artifact | `artifacts.yaml` | Where the Core AI artifact lives and who converted/hosts it. |
| Framework/runtime | `upstreams.yaml > framework_sources` | Apple Core AI, Core ML and tooling context. |
| Original model | `upstreams.yaml > original_model_sources` | Original creators/model-family sources. |
| License | `upstreams.yaml > license_sources` | License documents and review flags. |
| Benchmarks | `benchmarks.jsonl` | Measurement rows, source IDs and confidence. |
| Human docs | `docs/*.md` | Tables, maps and curated summaries. |
| Machine exports | `dist/*.json` | Generated JSON outputs for agents/APIs. |

## Model groups

| Group | Meaning |
|---|---|
| `fabric` | First-party conversion produced via [coreai-fabric](https://github.com/kevinqz/coreai-fabric) — the agent-first conversion pipeline. |
| `zoo` | Community model port from `john-rocky/coreai-model-zoo` (indexed reference upstream). |
| `official` | Artifact described upstream as an Apple official recipe conversion from `apple/coreai-models`. |
| `external` | External source (e.g. an independent community conversion) not from the zoo, fabric, or an Apple recipe. |
| `unknown` | Not classified yet. |

### Where new conversions come from

New `.aimodel` conversions flow through **[coreai-fabric](https://github.com/kevinqz/coreai-fabric)**, the first-party agent-first conversion pipeline: an agent (or human) writes a recipe, runs `convert → verify` (parity-checked), publishes the artifact to their *own* Hugging Face namespace, and `register` opens the catalog PR. This catalog stays an index — it never hosts weights and never converts. The community zoo is an **indexed reference upstream**, not the required path. See [`CONTRIBUTING.md`](CONTRIBUTING.md#contributing-a-new-conversion).

## Official Apple recipe conversions

Entries with `source_group: official` in `catalog.yaml` and `officiality.apple_export_recipe: true` in `artifacts.yaml` are treated as official Apple recipe conversion artifacts. The `officiality` block disambiguates *official of what*: `apple_export_recipe` (converted via an Apple recipe), `apple_hosted_artifact` (Apple hosts the artifact — `false` for all current entries), and `community_packaged` (packaged/hosted by the community).

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
- 1.58-bit ternary LLMs
- vision-language models
- GUI grounding / computer use
- document OCR
- visual document retrieval (ColBERT / MaxSim)
- audio understanding
- text-to-speech
- speech-to-text (ASR + transducer / TDT)
- embeddings
- reranking
- image-text similarity (CLIP)
- object detection
- instance segmentation
- promptable segmentation
- monocular depth
- image generation
- super-resolution
- text-to-video
- image-to-3D (Gaussian splatting)
- text-to-audio (generative music)
- diffusion LLMs (dLLM)
- vision-language-action (VLA / robotics)

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
python scripts/generate.py --docs
```

Export JSON, search indexes, and readiness scores:

```bash
python scripts/generate.py --json
```

Or generate everything at once:

```bash
python scripts/generate.py
```

The GitHub Actions workflow runs validation, generation, CLI smoke test, and MCP assertion on every push and pull request.

## CLI

Install the CLI for the full experience:

```bash
pip install coreai-catalog
```

### Commands

```bash
# Discover models
coreai-catalog search --capability vision-language --device iphone
coreai-catalog list                          # all models (suitability facets in dist/search-index.json)
coreai-catalog scores                        # deployability/curation readiness — deprecated headline; see docs/concepts/suitability-facets.md
coreai-catalog capabilities                  # list all capabilities with model counts

# Plan modality transformation pipelines
coreai-catalog transforms                    # show the full transform graph
coreai-catalog transforms --from audio       # list models that accept audio input
coreai-catalog transforms --from audio --to image  # plan a pipeline from audio to image

# Inspect a model
coreai-catalog show qwen3-vl-2b              # full details: caps, devices, runtime, provenance, benchmarks
coreai-catalog show qwen3-vl-2b -v           # verbose — full notes, not truncated
coreai-catalog compare qwen3-vl-2b unlimited-ocr  # side-by-side

# Get recommendations
coreai-catalog recommend --task "robot vision" --device iphone
coreai-catalog recommend --task "private on-device OCR" --device iphone
coreai-catalog recommend --task "voice assistant" --device mac

# Install a model (downloads from Hugging Face, writes manifest + Swift snippet)
coreai-catalog install qwen3-vl-2b           # downloads artifact, generates snippet.swift
coreai-catalog install qwen3-vl-2b --dry-run # preview download size without downloading
coreai-catalog installed                     # list locally installed models
coreai-catalog uninstall qwen3-vl-2b

# Check your environment
coreai-catalog doctor                        # checks Python, Xcode, coreai-torch, coreai-opt, HF CLI, disk

# Discover models worth porting to Core AI (module: coreai_catalog/discover.py)
python scripts/discover.py                     # scan Hugging Face for models with Core AI potential
python scripts/discover.py --format markdown   # pinned-issue body (what discover.yml publishes weekly)

# Release a new version (pre-flight checks → version bump → tag → build → PyPI)
coreai-catalog publish --version 2.2.0       # full release
coreai-catalog publish --dry-run             # preview the release steps without uploading
```

All commands support `--json` for programmatic consumption by agents and automation.

## MCP server (Agent API)

The catalog ships an [MCP server](https://modelcontextprotocol.io/) that exposes 16 tools to AI agents (Claude Desktop, Cursor, any MCP-compatible client).

### Setup

```bash
pip install "coreai-catalog[mcp]"
```

### Configure in Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "coreai-catalog": {
      "command": "coreai-catalog-mcp"
    }
  }
}
```

Or use the installed entry point directly:

```json
{
  "mcpServers": {
    "coreai-catalog": {
      "command": "python",
      "args": ["-m", "mcp_server.server"]
    }
  }
}
```

Or use the installed entry point:

```json
{
  "mcpServers": {
    "coreai-catalog": {
      "command": "coreai-catalog-mcp"
    }
  }
}
```

### Available tools (16)

**Read-only query tools (12)** — also mirrored in the OpenAPI spec:

| Tool | Description |
|---|---|
| `search_models` | Filter by capability, device, license, family, source, modality |
| `get_model` | Full model details: capabilities, runtime, provenance, benchmarks |
| `compare_models` | Side-by-side comparison of 2+ models |
| `recommend_model` | Task-based recommendations (89 task synonyms mapped) |
| `check_license` | License and commercial use triage for a model |
| `get_benchmarks` | All benchmark records for a model |
| `get_artifact` | Artifact provenance and download info |
| `explain_term` | Apple AI terminology lookup (42 verified terms) |
| `get_capabilities` | List all capabilities with model counts |
| `get_tasks` | List all supported task synonyms and their mappings |
| `get_version` | Catalog version, model count, last-verified date |
| `query_transforms` | Plan multi-hop modality transformation pipelines between Core AI models (graph, `--from`, `--from --to`) |

**Write / contribution tools (3)** — MCP-only, gated (no static-hosting equivalent):

| Tool | Description |
|---|---|
| `validate_entry` | Pre-flight a candidate model/artifact/benchmark/source entry against its schema + cross-reference rules (aggregated errors, fix hints); no writes |
| `draft_model` | Assemble `catalog.yaml` + `artifacts.yaml` entries from a payload, validate, and return the would-be diff; no writes |
| `submit_model` | Write the drafted entries, run the local validate/audit gate (rolled back on failure), and open a PR (`confirm=true` required; a human merges) |

**Integration tool (1)** — MCP-only:

| Tool | Description |
|---|---|
| `get_integration_snippet` | Contract-driven Swift integration code for a model without installing it (typed `io_contract`, image code path for image-input models) |

### Example agent interaction

```
User: I need a vision-language model that runs on iPhone for robot perception.

Agent calls: search_models(capability="vision-language", device="iphone")
→ Returns 6 candidates with readiness scores

Agent calls: compare_models(["qwen3-vl-2b", "minicpm-v-4-6"])
→ Returns side-by-side comparison

Agent calls: check_license("qwen3-vl-2b")
→ Returns Apache-2.0, commercial_use: likely

Agent recommends: Qwen3-VL 2B — benchmarked, iPhone-supported, Apache-2.0
```

## Query and decision

All query and decision tools are built into the CLI (see above) and the MCP server (see below). There is no separate `scripts/query.py` or `scripts/recommend.py` — the CLI is the single entry point for both humans and automation.

## Documentation

`generated` docs are produced from the YAML source by scripts and must not be
hand-edited; `curated` docs are maintained manually (see `docs/generated-files.md`).

| Doc | Type | Description |
|---|---|---|
| `docs/getting-started.md` | curated | 60-second → 10-minute walkthrough |
| `docs/index.md` | generated | Docs entry point and counts (`scripts/generate.py`). |
| `docs/model-registry.md` | generated | Human-readable model table (`scripts/generate.py`). |
| `docs/artifact-provenance.md` | generated | Artifact ownership and hosting view (`scripts/generate.py`). |
| `docs/apple-terminology-map.md` | generated | Verified Apple AI terminology by layer (`scripts/generate.py`). |
| `docs/tasks/` | generated | Per-capability task pages with model tables (`scripts/generate.py`). |
| `docs/concepts/` | curated | Model vs artifact, runtime landscape, license risk, benchmark quality. |
| `docs/data-model.md` | curated | Entity model and relationship documentation. |
| `docs/capability-matrix.md` | curated | Models grouped by capability. |
| `docs/runtime-matrix.md` | curated | Runtime concepts and flags. |
| `docs/upstream-map.md` | curated | Framework/original-model/license upstream map. |
| `docs/benchmark-map.md` | curated | Benchmark registry explanation. |
| `docs/source-map.md` | curated | Source and upstream map. |
| `docs/sota-maintenance.md` | curated | Maintenance plan and data-model direction. |
| `docs/generated-files.md` | curated | Generated vs curated file policy. |
| `PROJECT_PHILOSOPHY.md` | curated | Why the project exists, design principles, non-goals. |

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

## Governance

Merge rules live in [`GOVERNANCE.md`](./GOVERNANCE.md) as **checkable rules**
an agent can evaluate and a human countersigns: a PR is mergeable when CI is
green, every added source URL resolves HTTP 200, officiality is consistent,
the license claim is compatible with the upstream's terms, and provenance is
linked. Merge authority for all catalog data files is assigned via
[`.github/CODEOWNERS`](./.github/CODEOWNERS).

**Requesting a model without cloning the repo:** file the
[model-request issue form](./.github/ISSUE_TEMPLATE/model-request.yml) — its
fields map 1:1 to `schema/model.schema.json` (dropdowns for every enum).
`model-request-to-pr.yml` validates the submission with the same aggregated
validation core as `coreai-catalog contribute model --dry-run`, comments the
verdict on the issue, and opens a **draft PR** with the generated entries
when everything is clean.

## Discovery automation

Two scheduled workflows keep the porting backlog visible without issue spam
(each **upserts a single pinned issue** — never duplicates):

- **`discover.yml`** (weekly): scans upstream Hugging Face orgs with
  `coreai_catalog/discover.py`, dedups against the catalog via the authored
  `upstream_repo` field, HF `base_model` lineage metadata, and a
  normalized-name fuzzy fallback, then upserts the pinned
  **Porting candidates** issue (label `porting-candidates`) with ranked,
  scored candidates.
- **`source-monitor.yml`** (every 3 hours): watches known converter HF
  accounts and upstream repos for new Core AI artifacts, and upserts the
  pinned **Source Monitor** issue (label `source-monitor`) including
  machine-readable candidate stubs — partial `catalog.yaml`/`artifacts.yaml`
  entries a future agent job can turn into draft PRs.

## Maintenance rules

1. One meaningful model variant should have one catalog entry.
2. Do not collapse variants when size, device support, runtime, quantization, license or artifact changes.
3. Use `unknown` instead of guessing.
4. Keep `catalog.yaml` focused on model facts.
5. Keep `artifacts.yaml` focused on converted artifact provenance and hosting.
6. Keep `upstreams.yaml` focused on original model, framework, license and benchmark sources.
7. Keep `benchmarks.jsonl` focused on normalized measurement records.
8. Keep `sources.yaml` focused on compact source registry.
9. Generate Markdown and JSON views from YAML whenever possible.
10. Credit original model creator, conversion source and artifact host separately.
11. Update `last_verified` when a source is rechecked.

## Roadmap

Current milestone:

- v2.1.0 — Signed benchmark intake pipeline (Ed25519 → GitHub Action → auto-merge), privacy-preserving dataset (k=3 suppression, coarsened device data), JSONL benchmark format with per-entry provenance, benchmark-aggregate export, anchor-cohort reference doc. **Shipped.**

Earlier:

- v2.0.0 — Web UI (GitHub Pages): model explorer, task browser, filters, search.

- v1.7.0 — Public Python library API (`from coreai_catalog import Catalog`), schema versioning docs.
- v1.6.0 — Task-first discovery: `tasks` command, `recommend --explain`, enriched MCP get_tasks.
- v1.5.0 — Structured docs (philosophy, getting-started, concepts, task pages), community templates, issue templates.
- v1.4.0 — PyPI-ready, 60-second demo, Swift examples, recommend redesign.
- v1.3.x — RWKV-7 Goose 1.5B, source-monitor cron, adversarial review, dist/ committed, docs sync.

- v1.3.0 — CLI↔MCP parity, TASK_MAP expanded 40→89, `version` command, terminology alignment ("Core AI").
- v1.2.x — Fuzzy search, capability aliases, ANSI auto-detect, recommend --license, installer hardening, DX improvements.
- v1.0 — Error resilience: 8 crash fixes + 63-test suite + CI integration.
- v0.6 — Technical backfill (precision, quantization, runtime flags), non-LLM benchmarks, terminology to 42 terms.
- v0.5 — Expanded model coverage: ternary LLM, GUI grounding, visual retrieval, transducer ASR, video, 3D, diffusion LLM, VLA.
- v0.4 — Verified Apple AI terminology layer, artifact officiality, benchmark provenance.
- v0.3 — Validation depth, upstream taxonomy, benchmark registry.

Later:

- Split large YAML files into `data/models/*.yaml` if the catalog grows significantly.
- Richer model cards, per-model pages, and SEO optimization on the web UI.
- Additional filters: runtime, maturity, confidence, artifact availability, modality.
- Automated source verification (via `scripts/validate_links.py`).

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
