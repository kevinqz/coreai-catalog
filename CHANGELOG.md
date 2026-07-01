# Changelog

All notable changes to Core AI Catalog are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [1.3.1] — 2026-07-01

### Added — new model: RWKV-7 Goose 1.5B
- **RWKV-7 Goose 1.5B** (`rwkv7-goose-1-5b`) — first pure-recurrent /
  linear-attention LLM on Core AI. No attention, no KV cache — O(1)
  per-token decode with constant memory and unbounded context. WKV7
  delta-rule matrix-state time-mix + sqrelu channel-mix. int8 weight-only
  quant (FFN only; recurrence projections kept fp16). Mac-only,
  Apache-2.0, experimental. Detected by the new source-monitor cron job.
  Model count: 78 → 79.

### Added — source-monitor automation
- **`scripts/check_sources.sh`** — watchdog script that monitors 6 GitHub
  repos, 6 HuggingFace Core AI artifact accounts, and 8 upstream model
  orgs for new commits/models. Runs every 3h via Hermes cron. Silent when
  nothing changes.
- New source: `rwkv-upstream` (HuggingFace model page).

### Fixed — 3-round red-team (R1 functional + R2 cross-system + R3 docs)

**R2: --json error paths (3 MAJOR bugs):**
- `search --json` with 0 results: was returning human text, now returns
  `{"count": 0, "total_matches": 0, "truncated": false, "models": []}`
- `show --json` with nonexistent model: was returning human text, now returns
  `{"error": "Model '...' not found"}`
- `compare --json` with nonexistent/insufficient models: same fix, returns
  JSON error objects

**R1: verified 0 functional bugs:**
- Readiness scores manually verified for 5 models (all match)
- Search counts match YAML for all tested capabilities
- CLI↔MCP parity confirmed (identical fields in search/caps/recommend)
- TASK_MAP: all 89 tasks resolve to at least 1 model
- Version consistency: all 4 source files + 9 dist files say 1.3.0

**R3: verified 0 docs/structure bugs:**
- All 11 MCP tools present in agent.json, llms.txt, openapi.yaml
- All 78 models have all 19 required fields
- Real-world agent simulation: all 6 scenarios pass
- YAML key ordering consistent across all models

### Added — test suite expanded to 68 tests
- `TestJSONErrorPaths` (5 new tests): verifies all CLI `--json` error paths
  return valid JSON, never plain text

## [1.3.0] — 2026-07-01

### Fixed — Red-team R3: CLI↔MCP parity, version consistency
- **Version sync** — catalog.yaml, pyproject.toml, agent.json, openapi.yaml, and
  all `dist/*.json` exports now carry `1.3.0` (were stale at `1.2.0` since 9
  commits). `readiness-scores.json` now also includes `export_catalog_version`.
- **CLI `search --json` / `list --json`** — added `artifact_url` and
  `devices_unknown` fields to match MCP `search_models` output exactly.
- **MCP `recommend_model`** — `devices` field normalized from raw dict to list
  (matches CLI output shape).
- **MCP `recommend_model`** — added `license` parameter (parity with CLI
  `-l`/`--license` filter).
- **MCP `get_capabilities`** — added `benchmark_count` field (parity with CLI).
- **CLI `scores`** — added secondary sort by model ID for deterministic
  tie-breaking (9 models tied at score 93, 11 at 83, etc.).
- **CLI `search`** — added valid-capability and valid-family hints when search
  returns 0 results.

### Added — Red-team R3: discoverability, task coverage
- **CLI `--version` / `-V` flag** — prints `coreai-catalog 1.3.0` and exits.
- **CLI `version` subcommand** — shows version, model count, benchmark count,
  term count, and last-verified date (supports `--json`).
- **TASK_MAP expanded from 40→87 entries** — added `translation`,
  `summarization`, `code generation`, `math`, `question answering`, `image
  classification`, `image captioning`, `visual question answering`, `voice
  cloning`, `document understanding`, `video understanding`, `multimodal chat`,
  `3d reconstruction`, and 27 more. 50 common tasks that previously returned
  0 models now resolve correctly.
- **`openapi.yaml`** — added `/api/tasks` and `/api/version` endpoints;
  added `license` parameter to `/api/recommend`; added `benchmark_count` to
  capabilities schema.
- **`agent.json`** — replaced phantom `install_model` with actual MCP tools
  `get_tasks` and `get_version`; tool list now matches MCP server exactly.
- **`readiness-scores.json`** — includes `export_schema_version` and
  `export_catalog_version` for consumer version detection.

### Fixed — Red-team R3: parameter parsing (35% of models affected)
- **`_parse_params` rewritten** — previously 27/78 models (35%) sorted as `inf`
  due to non-standard parameter formats. Now handles `E2B`/`E4B` (effective
  parameters), `nano`/`small`/`medium`/`large`/`xlarge` (size tiers),
  `sub-2B`, `35B / ~3B active` (compound), `809M / ~1.5GB` (weight+param),
  `2B (BitNet b1.58)` (parenthetical), and more. Only 2 models remain as `inf`
  (genuinely no parameter count: upscale factor `×4`, weight-only `~1.7GB`).

### Fixed — Red-team R3: terminology alignment
- `llms.txt`, `openapi.yaml`, `agent.json` — "CoreAI" → "Core AI" (Apple's
  official convention with space).
- `openapi.yaml` — tool count "9 tools" → "11 tools" in description.

## [1.2.9] — 2026-06-30

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
