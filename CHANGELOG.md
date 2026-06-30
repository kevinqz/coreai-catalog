# Changelog

All notable changes to CoreAI Catalog are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [1.2.5] — 2026-06-30

### Added — DX/UX improvements
- New `coreai-catalog capabilities` command (alias `caps`) — list all capabilities
  with model counts, directly in the CLI (was MCP-only)
- `show -v` / `--verbose` flag — display full notes without truncation
- `install --dry-run` now shows artifact download size
- `search --help` now shows example capability values (chat, vision-language,
  speech-to-text, etc.) so users don't have to guess

### Fixed — DX/UX improvements
- `doctor` now only prints install instructions for tools that actually failed
  (was unconditionally printing all 3 install commands)
- `recommend "robot vision"` now prioritizes vision-language models above
  object-detection (VLMs are what most users want for robot vision)
- Aligned CLI description and pyproject.toml with Apple terminology:
  "Core AI models for Apple Silicon"

### Changed
- pyproject.toml: add jsonschema to dependencies, remove dead package-data
- Terminology: "Core AI" (space) per Apple convention, not "CoreAI"

### Changed
- Consolidated 10 redundant scripts into one unified `scripts/generate.py`
- Moved all export logic to `coreai_catalog/exports.py` (single source for JSON/JSONL/scores)
- Unified scoring/search/recommend logic into `coreai_catalog/catalog.py`
- Eliminated all code duplication between scripts and the package

### Added
- **Agent-ready layer:** `agent.json` manifest, `llms-full.txt` comprehensive context, `openapi.yaml` REST contract
- MCP server (9 read-only tools) for Claude Desktop, Cursor, and MCP-compatible agents
- `llms.txt` for LLM discovery
- CLI `--json` output on all query commands
- Weekly upstream sync CI (scans Hugging Face + GitHub for gaps, creates issues)

### Removed
- Deleted scripts: `generate_docs.py`, `generate_artifact_docs.py`, `generate_terms_docs.py`, `generate_index.py`, `generate_compare.py`, `export_json.py`, `export_search.py`, `query.py`, `readiness_score.py`, `recommend.py`

## [1.2.1] — 2026-06-30

### Fixed
- Sync `pyproject.toml` version 1.1.0 → 1.2.0
- Fix all stale script references in README.md and docs/generated-files.md
- Clean `.gitignore` comment, remove nested egg-info

### Added
- `llms-full.txt` (comprehensive context map)
- `agent.json` (machine-readable manifest)
- `openapi.yaml` (OpenAPI 3.1 REST contract mirroring MCP tools)
- `CHANGELOG.md` (Keep a Changelog format)
- `export_schema_version` + `export_catalog_version` in all JSON exports

## [1.2.2] — 2026-06-30

### Fixed — Dogfood round 1 (12 bugs squashed)
- Fix `aot_required` scoring inversion (catalog.py): +5 was going to models that
  require AOT instead of those that don't — 59 models underscored, 19 overscored
- Fix 3 models with `parameters=unknown` → `not_published`
- Fix `llms-full.txt` scoring table: missing `confidence=medium → +3` tier
- MCP `search_models`: add `total_matches` + `truncated` fields
- MCP `search_models`: surface `devices_unknown` for iPad/others
- MCP `recommend_model`: secondary sort prioritizes first resolved capability
  (RAG now ranks embeddings above chat models)
- CLI: add `--json` flag to `show` and `list` commands
- CLI: fix `scores` table column misalignment
- CLI: sort search results by readiness score descending
- CLI: show valid task keywords when `recommend` finds nothing
- CLI: add secondary sort by parameter count for deterministic tie-breaking
- OpenAPI: make `Benchmark.value` nullable (matches actual data)

## [1.2.3] — 2026-06-30

### Fixed — Dogfood round 2 (crashes, consistency, data quality)
- Guard `None` inputs in `get_model()`, `compare_models()`, `check_license()`,
  `get_benchmarks()`, `get_artifact()` — no more raw tracebacks
- Clamp `search_models` limit to [0, 10000] (negative limits were slicing)
- Deduplicate `compare_models` input IDs
- Empty task in `recommend_model`/`resolve_task` returns empty list
- Unify CLI `--json` schemas with MCP across search, show, list, compare, recommend
  (devices as list, consistent field names, full benchmark fields)
- Remove 4 HF URLs from `github.path` fields in artifacts.yaml
- Fix 33 benchmarks with `precision: unknown` → `not_published`
- Add `precision` + `notes` to search-index.json benchmark entries

### Added
- `scripts/deep_audit.py` — comprehensive auditor for semantic data quality

## [1.1.0] — 2026-06-30

### Added
- MCP server with 9 tools (`search_models`, `get_model`, `compare_models`, `recommend_model`, `check_license`, `get_benchmarks`, `get_artifact`, `explain_term`, `get_capabilities`)
- `llms.txt` for LLM discovery
- Agent skills for model selection and license triage
- `coreai-catalog-mcp` entry point in pyproject.toml

## [1.0.0] — 2026-06-29

### Added
- Pip-installable CLI with 10 commands: `search`, `show`, `list`, `scores`, `compare`, `recommend`, `install`, `uninstall`, `installed`, `doctor`
- Model installer (`huggingface-cli` integration with local tracking)
- `doctor` command for environment health check
- Readiness scores (0-100) with letter grades
- Decision layer: denormalized `search-index.json` + `models.jsonl`
- 32 comparison tables under `docs/compare/`

### Data
- 78 models (65 zoo/official + 13 external from 8 HF converters)
- 78 artifacts, 66 benchmarks, 42 terms, 65 upstreams, 20 sources

## [0.9.0] — 2026-06-29

### Added
- Query and recommendation engine with task-to-capability mapping
- Readiness score algorithm (13 weighted factors)

## [0.8.0] — 2026-06-28

### Added
- Coverage expansion: more models, benchmarks, and terminology entries

## [0.7.0] — 2026-06-28

### Added
- Trust foundation: officiality struct, provenance tracking, cross-reference validation

## [0.6.0] — 2026-06-27

### Added
- Automation suite: schema validation, data-quality audit, upstream sync scanner
- 3 new models from sync scanner
- Expanded to 62 models, hardened schemas, backfilled all technical data
- 42 Apple AI terminology entries

## [0.5.0] — 2026-06-26

### Added
- Verified Apple AI terminology layer (terms.yaml + schema)
- 32 comparison tables

## [0.4.0] — 2026-06-26

### Changed
- Replaced `is_official_recipe` boolean with structured `officiality` block
- Apple AI terminology layer (42 terms with official source citations)

## [0.3.0] — 2026-06-25

### Added
- Single-source-of-truth benchmark model with provenance
- Append-only benchmarks with supersession tracking
- Cross-reference integrity validation
