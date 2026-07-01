# Model vs Artifact: Understanding Provenance

When a developer installs a Core AI model, they touch **four distinct entities** that
are easy to conflate. This page disentangles them so you can answer the most important
question in the catalog: *where did this come from, and can I trust it?*

## The four layers

| # | Entity | Who is responsible | Where it lives in the catalog |
|---|--------|-------------------|-------------------------------|
| **a** | **Original model** | The team that trained and released the weights | `upstreams.yaml → original_model_sources` |
| **b** | **Core AI artifact conversion** | The person/repo that wrote the recipe and converted weights → `.aimodel` | `catalog.yaml → source_path`, `artifacts.yaml → github` |
| **c** | **Artifact host** | The Hugging Face (or other) account that stores the downloadable bundle | `artifacts.yaml → huggingface` |
| **d** | **Benchmark source** | The repo that measured throughput/latency/RTF | `benchmarks.yaml → source`, `upstreams.yaml → benchmark_sources` |

These four entities can be — and usually are — **four different people or organizations**.

## Flow diagram

```
┌──────────────────┐
│  (a) Original    │  Qwen team trains Qwen3-VL
│      Model       │  Hugging Face: Qwen/Qwen3-VL-2B-Instruct
└────────┬─────────┘
         │ trained weights (Apache-2.0)
         ▼
┌──────────────────┐
│  (b) Conversion  │  john-rocky writes conversion recipe
│      Recipe      │  github.com/john-rocky/coreai-model-zoo
└────────┬─────────┘
         │ recipe + verification (top-1 exact vs HF)
         ▼
┌──────────────────┐
│  (c) Artifact    │  mlboydaisuke hosts the .aimodel bundle
│      Host        │  huggingface.co/mlboydaisuke/Qwen3-VL-2B-CoreAI
└────────┬─────────┘
         │ developer downloads
         ▼
┌──────────────────┐
│  Developer       │  coreai-catalog install qwen3-vl-2b
│  Installs        │  Swift app loads .aimodel via CoreAIKit
└──────────────────┘

  (d) Benchmark    │  john-rocky/apple-silicon-llm-bench measures
     Source        │  33.5 tok/s on iPhone 17 Pro → benchmarks.yaml
```

## Worked example: Qwen3-VL-2B

**catalog.yaml** (model metadata):

```yaml
- id: qwen3-vl-2b
  name: Qwen3-VL 2B
  family: Qwen
  source_group: zoo
  source_path: https://github.com/john-rocky/coreai-model-zoo/blob/main/zoo/qwen3-vl.md
  license:
    name: Apache-2.0
    commercial_use: likely
```

**artifacts.yaml** (artifact provenance):

```yaml
- id: qwen3-vl-2b
  group: zoo
  github:
    owner: john-rocky
    repo: coreai-model-zoo
    path: https://github.com/john-rocky/coreai-model-zoo/blob/main/zoo/qwen3-vl.md
  huggingface:
    owner: mlboydaisuke
    repo: Qwen3-VL-2B-CoreAI
    url: https://huggingface.co/mlboydaisuke/Qwen3-VL-2B-CoreAI
  officiality:
    apple_export_recipe: false
    apple_hosted_artifact: false
    community_packaged: true
```

**upstreams.yaml** (original model attribution):

```yaml
- id: qwen
  title: Qwen original model family
  category: original_model
  platform: huggingface
  owner: Qwen
  url: https://huggingface.co/Qwen
  trust: original_model_primary
  applies_to:
    - qwen3-vl-2b
```

So for a single model you can trace: **Qwen** (original) → **john-rocky** (conversion) →
**mlboydaisuke** (host) → **john-rocky/apple-silicon-llm-bench** (benchmark). Four entities,
three different people, one Apache-2.0 license.

## The `source_group` field

`catalog.yaml` assigns every model a `source_group` that classifies its lineage:

| `source_group` | Meaning | Conversion recipe | Current count |
|----------------|---------|-------------------|---------------|
| `official` | Apple's official export recipe (from `apple/coreai-models`) | Apple-authored | 10 |
| `zoo` | Community port from `john-rocky/coreai-model-zoo` | Community-authored | 69 |
| `external` | External source, not yet mapped | Varies | 0 |

The catalog validates a strict rule: **`source_group: official` implies `officiality.apple_export_recipe: true`**, and `source_group: zoo` implies `apple_export_recipe: false`. This prevents accidental mislabeling of community work as official Apple output.

## The `officiality` block

The `officiality` block in `artifacts.yaml` answers the question *"official of what?"*
by separating three independent facts:

| Field | True means | False means |
|-------|-----------|-------------|
| `apple_export_recipe` | Apple authored the conversion recipe | Community authored the recipe |
| `apple_hosted_artifact` | Apple hosts the downloadable bundle | Someone else hosts it (currently **always false**) |
| `community_packaged` | Community packaged/hosted the bundle | Apple or no community packaging involved |

> **Key insight:** Apple may author an official recipe but not host the artifact. All
> current official artifacts are hosted by community members on Hugging Face.

### Official recipe example: gpt-oss-20B

```yaml
# catalog.yaml
- id: official-gpt-oss-20b
  source_group: official
  runtime:
    runner: stock-runner
    stock_runtime: true
  confidence: high

# artifacts.yaml
- id: official-gpt-oss-20b
  officiality:
    apple_export_recipe: true
    apple_hosted_artifact: false
    community_packaged: true
```

Official-recipe artifacts typically run on the **stock Core AI runtime** without custom
kernels or patches, and carry `confidence: high`.

### Community zoo example: Gemma 4 E2B

```yaml
# catalog.yaml
- id: gemma-4-e2b
  source_group: zoo
  runtime:
    stock_runtime: false
    patch_required: true
    aot_required: true
  confidence: medium

# artifacts.yaml
- id: gemma-4-e2b
  officiality:
    apple_export_recipe: false
    apple_hosted_artifact: false
    community_packaged: true
```

Community zoo artifacts often need patches, AOT compilation, or custom kernels and tend to
carry `confidence: medium`.

## Why this separation matters

1. **License attribution** — the original model license (e.g. Apache-2.0 from Qwen) is
   separate from any license on the conversion code or the hosting repo. See
   [License Risk](./license-risk.md).
2. **Trust calibration** — an official Apple recipe with stock runtime is lower risk than
   a community port requiring custom Metal kernels.
3. **Bug reporting** — if the artifact is broken, you report to the converter
   (`john-rocky`), not the original trainer (Qwen) or the host (`mlboydaisuke`).
4. **Benchmark context** — benchmarks are measured by specific sources under specific
   conditions. See [Benchmark Quality](./benchmark-quality.md).

## Cross-reference keys

The catalog uses these join keys to connect layers:

```
catalog.models[].artifact_ref      →  artifacts.artifacts[].id
benchmarks.benchmarks[].model_id   →  catalog.models[].id
upstreams.original_model_sources[]
  [].applies_to[]                  →  catalog.models[].id
```

These are validated by schema and cross-reference integrity checks on every CI run.
