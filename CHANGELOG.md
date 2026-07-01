# Changelog

All notable changes to Core AI Catalog are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [2.0.3] — 2026-07-01

### Fixed — release hygiene and docs consistency

- **CI version assertion** — replaced hardcoded version string in
  `validate.yml` with dynamic read from `catalog.yaml`. Never goes stale again.
- **CHANGELOG** — added missing v2.0.1 and v2.0.2 entries.
- **llms.txt + llms-full.txt** — `pip install -e .` → `pip install coreai-catalog`.
- **Site SEO** — enriched meta description, OpenGraph tags, `<noscript>` fallback
  with model count and JSON API link for crawlers.
- **Roadmap** — removed stale "Publish to PyPI" from future (already done).

## [2.0.2] — 2026-07-01

### Fixed — PyPI published

- **PyPI** — `coreai-catalog` v2.0.2 published. `pip install coreai-catalog` works.
- **Publish workflow** — fixed `dist_package/*` → `dist_pkg/*` path, added
  `TWINE_USERNAME=__token__`, added `sync_package_data` step.
- **Install instructions** — reverted all docs to `pip install coreai-catalog`.

## [2.0.1] — 2026-07-01

### Fixed — PyPI publish workflow

- Initial attempt to publish to PyPI (failed: wrong dist path).
- Fixed: build artifacts to `dist_pkg/` to avoid conflict with `dist/*.json`.

## [2.0.0] — 2026-07-01

### Added — searchable web UI (GitHub Pages)

- **`site/`** — static, zero-dependency web UI for model exploration:
  - `index.html` + `style.css` + `app.js` (26KB total, no framework)
  - Loads `dist/search-index.json` via fetch
  - Filters: capability, device (iPhone/iPad/Mac), license, source group, sort by
  - Full-text search across model names, capabilities, and families
  - Model detail modal: full metadata, benchmarks, install command, artifact URL
  - Tasks tab: browse all 89 task keywords grouped by capability
  - About tab: quick start, resources, agent integration, Python API
  - Dark theme, mobile-responsive, keyboard-accessible (ESC closes modal)
- **`.github/workflows/pages.yml`** — auto-deploys to GitHub Pages on push
  - URL: https://kevinqz.github.io/coreai-catalog/

### Breaking — major version bump (1.x → 2.0)

No breaking schema changes. The major bump reflects the project maturing from
a catalog into a **decision infrastructure platform** with web UI, Python API,
agent integration, and distribution pipeline. Schema version stays at 1.0.

## [1.7.0] — 2026-07-01

### Added — public Python library API

- **`coreai_catalog.api.Catalog`** — clean, stable programmatic interface:
  ```python
  from coreai_catalog import Catalog
  catalog = Catalog.load()
  catalog.search(capability="vision-language", device="iphone")
  catalog.recommend(task="ocr", device="iphone")
  catalog.compare("qwen3-vl-2b", "unlimited-ocr")
  catalog.license_report("qwen3-vl-2b")
  catalog.tasks()
  catalog.capabilities()
  ```
- **`coreai_catalog/__init__.py`** — exports `Catalog` for `from coreai_catalog import Catalog`
- **20 new tests** (`tests/test_public_api.py`) covering all API methods

### Added — schema versioning documentation

- **`docs/concepts/schema-versioning.md`** — SemVer policy for schema changes,
  consumer guidance (agents, Python API, raw JSON), validation guarantees.

## [1.6.0] — 2026-07-01

### Added — task-first discovery

- **`coreai-catalog tasks`** — new CLI command listing all 89 task synonyms
  grouped by capability (25 capabilities). Supports `--json`.
- **`recommend --explain`** — shows the full decision tree: task → resolved
  capabilities → device/license filters → ranking algorithm → top-N.
- **MCP `get_tasks` enriched** — now groups synonyms by capability with counts
  (was flat list). Backward compatible: still returns count + all tasks.

## [1.5.0] — 2026-07-01

### Added — structured documentation

- **`PROJECT_PHILOSOPHY.md`** — why the project exists, design principles,
  non-goals, inspiration from FastAPI/Django/Transformers/Home Assistant.
- **`docs/getting-started.md`** — 60-second → 5-minute → 10-minute walkthrough.
- **`docs/concepts/`** — 4 concept docs:
  - model-vs-artifact.md (original model → conversion → host → install flow)
  - core-ai-vs-core-ml-vs-mlx.md (Apple ML runtime landscape)
  - license-risk.md (reading license fields, decision tree)
  - benchmark-quality.md (append-only semantics, confidence levels)
- **`docs/tasks/`** — 32 auto-generated per-capability pages with model tables,
  task synonyms, install commands, and scoring.
- **`dist/tasks/`** — 89 task JSON files + index.json for agent consumption.
  Each contains sorted models, best-overall, best-iphone, best-commercial picks.

### Added — community contribution infrastructure

- **`templates/model-entry.yaml`** — copy-pasteable YAML skeleton for new models.
- **`templates/artifact-entry.yaml`** — same for artifacts.
- **`.github/ISSUE_TEMPLATE/`** — model-request, bug-report, benchmark-submission.

### Added — task page generation engine

- **`coreai_catalog/task_pages.py`** — generates markdown task pages and JSON exports.
- Integrated into `scripts/generate.py` — runs automatically with all other exports.

## [1.4.0] — 2026-07-01

### Added — PyPI distribution ready

- **`pyproject.toml`** — full PyPI metadata (classifiers, keywords, authors, URLs)
- **Package data** — YAMLs + schemas bundled in `coreai_catalog/data/` so the catalog works after `pip install` without cloning the repo
- **`_find_catalog_root()`** — 3-tier search: CWD → walk-up → bundled package data
- **`.github/workflows/publish.yml`** — auto-publish to PyPI on tag push
- **`scripts/sync_package_data.py`** — syncs YAMLs into package before build

### Added — 60-second demo moment

- **`recommend` output redesigned** — each recommendation now shows:
  readiness score with grade, device support, license icon, install command,
  and artifact URL. Footer has bolded quick-start command.
- **`install --json`** — structured output: model_id, status, path, artifact_url, size
- **`uninstall --json`** — structured output: model_id, status
- **`examples/` directory** — 3 complete Swift integration examples:
  - `ocr-swiftui/` — Unlimited-OCR (document text extraction)
  - `vlm-chat/` — Qwen3-VL 2B (vision-language chat)
  - `embeddings-rag/` — EmbeddingGemma 300M (on-device semantic search + RAG)

### Changed — all install/uninstall error paths return JSON with `--json`

- `install` not-found: `{"error": "Model '...' not found"}`
- `install` already-installed: `{"model_id": "...", "status": "already_installed"}`
- `install` dry-run: `{"model_id": "...", "status": "dry_run"}`
- `uninstall` not-installed: `{"model_id": "...", "status": "not_installed"}`

## [1.3.1] — 2026-07-01

### Fixed — dist/ exports now committed (raw GitHub URLs resolve)

- **Problem:** `dist/` was `.gitignored`, so every doc citing `dist/*.json`
  URLs (agent.json, llms.txt, llms-full.txt, openapi.yaml, AGENTS.md)
  returned 404 on raw GitHub. The "agent-ready" promise was broken.
- **Fix:** removed `dist/` from `.gitignore`, committed all 10 JSON exports.
  Verified: `catalog.json`, `readiness-scores.json`, `coreai-catalog.json`
  all return HTTP 200 on raw GitHub.
- Updated docs to clarify exports are committed, not local-only. Added raw
  GitHub base URL to llms.txt, llms-full.txt, AGENTS.md.
- **CI:** added "Verify dist/ and docs/ are in sync" step
  (`git diff --exit-code docs/ dist/`).
- **CI:** fixed version assertion `1.3.0` → `1.3.1`.

### Fixed — README.md sync (stale since v1.2)

- Version `v1.2` → `v1.3.1`, status section rewritten.
- Model/artifact counts `78` → `79`, sources `20` → `21`, upstreams `65` → `66`.
- Scripts tree: added `deep_audit.py`, `derive_fields.py`, `check_sources.sh`.
- MCP tools table: added `get_tasks`, `get_version` (was listing 9 of 11).
- Task synonyms `40` → `89`.
- Roadmap: replaced v0.3–v0.6 with full v0.3 → v1.3.1 timeline.
- `llms.txt`, `agent.json`: `78+` → `79` (exact count, not range).
- `openapi.yaml`: `78+` → `79`.

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
- Schema: added `recurrent` to architecture enum.

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
