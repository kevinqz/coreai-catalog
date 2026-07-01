# Core AI Catalog Philosophy

## Why this project exists

Model discovery is not enough.

Developers building for Apple platforms need to know:

- **what** a model is (capabilities, architecture, parameters)
- **where** it came from (original creator, conversion source, artifact host)
- **whether** the artifact is official or community-converted
- **whether** it runs on their target devices (iPhone, iPad, Mac)
- **what** license risks exist (commercial use, redistribution, derivatives)
- **what** benchmarks exist (throughput, latency, accuracy, and their confidence)
- **whether** an agent can reason over it safely (structured data, not vibes)

Apple Core AI models are scattered across upstream repos, Hugging Face accounts,
community zoos, and Apple's own recipe conversions. There is no central place
to answer "which model should I use for X on device Y, with license Z?"

Core AI Catalog solves this.

## One-liner

> **The agent-ready registry for Apple local AI.**
> Find the right model. Verify provenance. Check license risk. Install artifacts.

## What we optimize for

1. **Source grounding** — every record traces to a real URL. No invented data.
2. **Machine readability** — CLI, MCP, JSON exports, llms.txt, OpenAPI. All from one engine.
3. **Agent usability** — an AI agent can discover, compare, recommend, and install without human help.
4. **Reproducible recommendations** — same query, same result, every time, across processes.
5. **Conservative license language** — `commercial_use` is a triage label, not a permission. When in doubt, `check_license`.
6. **Task-first discovery** — users think "I need OCR", not "I need model #42".
7. **Apple local AI workflows** — on-device, offline, private. Not cloud, not generic ML.

## What this project IS

- A metadata and decision layer
- Source-grounded: every record traces to Hugging Face, GitHub, or Apple docs
- Agent-first: CLI, MCP server, JSON exports, llms.txt — all from the same engine
- A trust layer: separates original creator, conversion source, artifact host, and license
- An educational map: explains the Apple local AI ecosystem

## What this project is NOT

- **Not a model host** — it does not redistribute weights or artifacts
- **Not a benchmark lab** — it catalogues benchmarks, doesn't run them
- **Not an inference wrapper** — it doesn't run models for you
- **Not a Hugging Face clone** — it's a decision layer, not a model hub
- **Not an awesome list** — it's executable, verifiable, and queryable
- **Not affiliated with Apple** — independent project, Apple terminology used for clarity
- **Not legal advice** — license fields are triage labels, not permissions

## Design principles

### YAML is the source of truth

Markdown docs and JSON exports are derived views. When they disagree, YAML wins.

### Never infer unknown fields

If a field is `unknown`, report it as unknown. If the upstream doesn't disclose, use `not_published`. Do not guess, do not extrapolate, do not fill gaps with plausible values.

### Officiality is precise

The `officiality` block disambiguates *official of what*:

- `apple_export_recipe` — true only for Apple's official conversion recipes
- `apple_hosted_artifact` — true only if Apple hosts the artifact (currently always false)
- `community_packaged` — true for community-zoo packaged artifacts

### Benchmarks are append-only

Superseded values are retained with `confidence: needs_review` and a `superseded_by` pointer. Values are never overwritten.

### Separation of concerns

| Entity | File | What it tracks |
|---|---|---|
| Model facts | `catalog.yaml` | Capabilities, modalities, runtime, device support, license |
| Artifact provenance | `artifacts.yaml` | GitHub source, HF host, officiality |
| Benchmarks | `benchmarks.yaml` | Measurements (append-only, environment-scoped) |
| Sources | `sources.yaml` | Compact registry of primary/supporting sources |
| Upstream taxonomy | `upstreams.yaml` | Framework, conversion, host, benchmark, license sources |
| Terminology | `terms.yaml` | Verified Apple AI terms with official source citations |

### Schema versioning

- **Patch** (1.4.x): record updates, new models, metadata corrections
- **Minor** (1.x.0): new fields, backward-compatible schema additions
- **Major** (x.0.0): breaking schema changes (migration guide provided)

`export_schema_version` and `export_catalog_version` are embedded in every JSON export for consumer version detection.

## The bigger picture

```
Hugging Face Hub = model hub (weights, model cards, spaces)
Apple = runtime/platform ecosystem (Core AI, Core ML, MLX, Neural Engine)
Core AI Catalog = decision + provenance layer between them
```

This project sits between the model hub (where artifacts live) and the developer (who needs to choose). It doesn't host weights. It doesn't run inference. It makes the ecosystem **queryable, verifiable, and agent-ready**.

## Inspiration

This project takes inspiration from:

- **FastAPI** — instant developer experience, auto-generated docs, type-driven design
- **Django** — batteries-included stability, excellent documentation culture
- **Hugging Face Transformers** — unified task-based API, community contributions
- **Home Assistant** — local-first, privacy-first, community integrations
- **Pandas** — became the default mental model for tabular data

The goal: become the default mental model for "which Apple local AI model should I use?"
