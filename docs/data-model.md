# Data Model

This document describes the entities, fields, and relationships in the Core AI Catalog.

> YAML files are the source of truth. This document is curated — update it when the schema changes.

## Entities

### Model (`catalog.yaml`)

Model metadata: what it is, what it does, how it runs, and whether it can be trusted.

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique identifier (kebab-case) |
| `name` | string | Human-readable model name |
| `family` | string | Model family (e.g., Qwen, Gemma, LFM) |
| `source_group` | enum | `zoo` \| `official` \| `external` \| `unknown` |
| `source_path` | URL | Link to the source model card or README |
| `artifact_ref` | string | Foreign key → `artifacts.yaml` id |
| `capabilities` | string[] | What the model can do (e.g., `chat`, `vision-language`, `object-detection`) |
| `modalities.input` | string[] | Input types (e.g., `text`, `image`, `audio`) |
| `modalities.output` | string[] | Output types |
| `artifact.format` | enum | `aimodel` \| `mlpackage` \| `unknown` |
| `artifact.availability` | enum | `available` \| `unavailable` \| `unknown` |
| `size.parameters` | string | Parameter count (e.g., `0.8B`, `2B`) |
| `size.precision` | string | Numeric precision (e.g., `int8`, `fp16`) |
| `size.quantization` | string | Quantization scheme (e.g., `int8lin`, `int4`) |
| `size.artifact_size` | string | Download size (e.g., `969MB`, `not_published`) |
| `runtime.runtime_name` | enum | `apple-core-ai` \| `coreml` \| `unknown` |
| `runtime.runner` | enum | `CoreAIRunner`, `stock-runner`, `CoreAIDiffusionPipeline`, etc. |
| `runtime.stock_runtime` | bool\|`unknown` | Whether the stock Core AI runtime suffices |
| `runtime.custom_kernel` | bool\|`unknown` | Whether custom Metal kernels are needed |
| `runtime.patch_required` | bool\|`unknown` | Whether the `coreai-models` patch stack is needed |
| `runtime.tokenizer_required` | bool\|`unknown` | Whether a tokenizer bundle is needed |
| `runtime.processor_required` | bool\|`unknown` | Whether a processor bundle is needed |
| `runtime.aot_required` | bool\|`unknown` | Whether ahead-of-time compilation is required |
| `device_support.iphone` | bool\|`unknown` | Runs on iPhone |
| `device_support.ipad` | bool\|`unknown` | Runs on iPad |
| `device_support.mac` | bool\|`unknown` | Runs on Mac |
| `device_support.mac_only` | bool\|`unknown` | Mac-only (not iOS) |
| `license.name` | string | SPDX license name or custom name |
| `license.commercial_use` | enum | `likely` \| `check_license` |
| `status` | enum | `confirmed` \| `needs_review` \| `deprecated` \| `unknown` |
| `maturity` | enum | `stable` \| `active` \| `experimental` \| `research` \| `unknown` |
| `confidence` | enum | `high` \| `medium` \| `low` \| `needs_review` |
| `sources[]` | string[] | Foreign keys → `sources.yaml` or `upstreams.yaml` IDs |
| `last_verified` | date | YYYY-MM-DD |
| `notes` | string\|null | Free-form caveats |

### Artifact (`artifacts.yaml`)

Converted artifact provenance: where it was converted, where it is hosted, and its officiality.

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique identifier (matches a `catalog.yaml` model id) |
| `group` | enum | `zoo` \| `official` \| `external` \| `unknown` |
| `github.owner` | string | GitHub org/user of the conversion source |
| `github.repo` | string | GitHub repo name |
| `github.path` | string\|null | URL to the specific model card or README |
| `huggingface.owner` | string | HF account hosting the artifact |
| `huggingface.repo` | string | HF repo name |
| `huggingface.url` | URL | Full HF URL |
| `huggingface.path` | string\|null | Optional sub-path within the repo (e.g., `tree/main/vl`) |
| `officiality.apple_export_recipe` | bool | True only for Apple official recipe conversions |
| `officiality.apple_hosted_artifact` | bool | True only if Apple hosts the artifact |
| `officiality.community_packaged` | bool | True for community-zoo packaged artifacts |

### Benchmark (`benchmarks.jsonl`)

Normalized measurement: a single environment-scoped data point, append-only.

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique identifier |
| `model_id` | string | Foreign key → `catalog.yaml` model id |
| `metric` | enum | `decode_throughput`, `inference_latency`, `image_generation_latency`, etc. |
| `unit` | enum | `tokens_per_second`, `seconds`, `megabytes`, etc. |
| `value` | number\|null | The measured value |
| `device` | string\|null | Hardware (e.g., `iPhone 17 Pro`, `M4 Max`) |
| `compute_unit` | enum\|null | `GPU` \| `ANE` \| `CPU` |
| `precision` | string\|null | Precision used during measurement |
| `environment` | string | OS/runtime context (e.g., `iOS 27 beta, coreai-pipelined engine`) |
| `observed` | date | YYYY-MM-DD |
| `source` | string | Foreign key → `sources.yaml` or `upstreams.yaml` ID |
| `confidence` | enum | `high` \| `medium` \| `low` \| `needs_review` |
| `superseded_by` | string\|null | ID of a newer measurement that supersedes this one |
| `notes` | string\|null | Free-form context |

### Source (`sources.yaml`)

Compact registry of primary and supporting sources.

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique identifier |
| `title` | string | Human-readable title |
| `type` | string | `github_repository`, `github_file`, `github_directory`, `huggingface_user`, etc. |
| `url` | URL | Canonical URL |
| `owner` | string | Owner/org |
| `repo` | string | Repo name (if GitHub) |
| `trust` | string | Trust level (`official_primary`, `community_primary`, `artifact_host`, etc.) |
| `volatility` | string | `high` \| `medium` \| `low` |
| `last_checked` | date | YYYY-MM-DD |
| `notes` | string | Description |

### Upstream (`upstreams.yaml`)

Source taxonomy organized in 7 groups, each with entries describing framework sources, conversion sources, artifact hosts, etc.

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique identifier |
| `title` | string | Human-readable title |
| `category` | string | Taxonomy category |
| `owner` | string | Owner/org |
| `repo` | string | Repo name (if applicable) |
| `url` | URL | Canonical URL |
| `trust` | string | Trust level |
| `applies_to[]` | string[] | Model IDs or conceptual tags this upstream covers |
| `notes` | string | Description |

#### Upstream groups

| Group | Purpose |
|---|---|
| `framework_sources` | Apple frameworks and tooling (Core AI docs, Core ML, coreai-torch, coreai-opt) |
| `conversion_sources` | Repos that perform model conversions (coreai-model-zoo) |
| `artifact_hosts` | Platforms hosting converted artifacts (Hugging Face accounts) |
| `benchmark_sources` | Repos with benchmark data |
| `sample_sources` | Sample apps and integration examples |
| `original_model_sources` | Original model creators (Qwen, Google, Meta, etc.) |
| `license_sources` | License references |

### Term (`terms.yaml`)

Verified Apple AI terminology with official source citations.

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique identifier |
| `label` | string | Human-readable label |
| `apple_layer` | enum | `system_surface`, `developer_framework`, `model_provider`, `provider_protocol`, `ai_primitive`, `artifact_format`, `developer_tool`, `model` |
| `definition` | string | Clear definition |
| `official_source` | URL | Link to Apple's official documentation |
| `verification` | string | Verification status (e.g., `confirmed_wwdc2026`) |
| `status` | string | `official`, etc. |
| `relations[]` | string[] | Typed relations to other terms (format: `relation_type:target_id`) |

## Relationships

```
catalog.models[].artifact_ref  →  artifacts.artifacts[].id
catalog.models[].sources[]     →  sources.sources[].id
catalog.models[].sources[]     →  upstreams.*[any group][].id
benchmarks.benchmarks[].model_id  →  catalog.models[].id
benchmarks.benchmarks[].source    →  sources.sources[].id
benchmarks.benchmarks[].source    →  upstreams.*[any group][].id
upstreams.original_model_sources[].applies_to[]  →  catalog.models[].id  OR  conceptual tag
terms.terms[].relations[]    →  terms.terms[].id  (via "relation_type:target_id" format)
```

## Cardinality

- One **model** has exactly one **artifact** (1:1 via `artifact_ref`).
- One **model** can have zero or more **benchmarks** (1:N via `model_id`).
- One **model** references one or more **sources** (N:N via `sources[]`).
- One **upstream** can apply to multiple models (N:N via `applies_to[]`).
- One **term** can relate to zero or more other terms (N:N via `relations[]`).

## Validation pipeline

```
schema/*.json  →  JSON Schema validation (validate.py)
       ↓
cross-references  →  referential integrity (validate.py)
       ↓
data-quality audit  →  9 categories, zero unknowns (audit.py)
       ↓
generated docs  →  markdown views (generate.py)
       ↓
JSON exports  →  machine-readable views (generate.py --json)
       ↓
sync scan  →  upstream gap detection (sync_upstream.py)
```
