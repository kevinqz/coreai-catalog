# Changelog

All notable changes to CoreAI Catalog are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [1.2.0] — 2026-06-30

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

## [1.1.0] — 2026-06-30

### Added
- MCP server with 9 tools (`search_models`, `get_model`, `compare_models`, `recommend_model`, `check_license`, `get_benchmarks`, `get_artifact`, `explain_term`, `get_capabilities`)
- `llms.txt` for LLM discovery
- Agent skills for model selection and license triage
- `coreai-catalog-mcp` entry point in pyproject.toml

## [1.0.0] — 2026-06-29

### Added
- Pip-installable CLI with 8 commands: `search`, `show`, `list`, `scores`, `compare`, `recommend`, `install`, `doctor`
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
