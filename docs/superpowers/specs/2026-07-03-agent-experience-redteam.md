# Agent Experience (AX) SotA — Redteam & Roadmap for coreai-catalog

**Date:** 2026-07-03
**Author:** Lead architect (agent-authored, file-grounded)
**Scope:** How Apple Core AI `.aimodel` models get published today, where the agent-first contribution/benchmark/consumption loops break, the state-of-the-art target architecture, and a prioritized roadmap.
**Status snapshot (verified live in worktree):** catalog.yaml v2.1.0, `last_verified: 2026-07-01`, **80 models** (zoo=55, official=12, external=13); artifacts.yaml `metadata.count: 80` = actual 80; benchmarks.jsonl=65 vs benchmarks.yaml=66 (already drifted); MCP server = 12 read-only tools; CLI = 15 subcommands.

---

## 0. Executive framing

`coreai-catalog` is a **source-grounded, index-not-host registry** of community-converted Apple Core AI models. Its architecture (YAML source of truth → generated JSON/docs, HF hosts the bytes, GitHub holds only metadata) is exactly the pattern the 2025-2026 registry SotA converged on (Ollama-over-HF, ONNX-zoo-deprecation, mlx-community). The trust model (`apple_export_recipe` / `apple_hosted_artifact` / `community_packaged` officiality triage) also matches SotA almost exactly.

The gap is **Agent Experience (AX)**. The catalog is excellent at *agent read* (MCP/CLI/JSON, llms.txt, AGENTS.md) but every *agent write* path — add a model, submit a benchmark, integrate a model in Swift — either does not exist, is documented incorrectly, or dead-ends in an un-completable CI gate. Six independent redteam personas ran the loops live in the worktree; their findings are consolidated below and were verified against source. Verdicts: the overwhelming majority are **CONFIRMED**, a handful **PARTIAL** (real core, one overstated leg).

The single sentence: **an agent can discover and reason about the catalog perfectly, but cannot contribute to it without out-of-band human knowledge, and cannot integrate from it without guessing.**

---

## 1. Como funciona HOJE — how publishing actually works

### 1.1 The publishing chain (who converts, who hosts, who indexes)

Apple ships **recipes, not artifacts**. `apple/coreai-models` (BSD-3, created 2026-06-08) provides export recipes + a Swift runtime, `apple/coreai-torch` the converter, `apple/coreai-optimization` the compression toolchain. Apple publishes **zero** `.aimodel` files on Hugging Face and states "We are not accepting pull requests at launch." External new-model recipe PRs are closed unmerged (SmolLM2 #76, Phi-4-mini #75). **Artifact hosting and recipe expansion are permanently delegated to the community — the exact layer this catalog occupies.**

The community substrate is `john-rocky/coreai-model-zoo` (created 2026-06-10, two days after Apple), a single-maintainer repo (Daisuke Majima) with a **bus factor of exactly 1** and zero external PRs ever merged. All weights live on Hugging Face, concentrated on one personal account.

**The dependency, in numbers (verified live):**

| Fact | Count | Source |
|---|---|---|
| Total models | 80 | `catalog.yaml` metadata |
| `source_group: zoo` | 55 | `catalog.yaml` |
| `source_group: official` | 12 | `catalog.yaml` |
| `source_group: external` | 13 | `catalog.yaml` |
| `source_path` → `github.com/john-rocky/coreai-model-zoo` | 64/80 | `catalog.yaml` |
| artifacts with `github.owner = john-rocky` | 67/80 | `artifacts.yaml` |
| artifacts with `huggingface.owner = mlboydaisuke` | **67/80 (84%)** | `artifacts.yaml` |
| ...including ALL zoo (55) AND ALL official (12) | 67 | `artifacts.yaml` |
| `officiality.apple_hosted_artifact = true` | **0/80** | `artifacts.yaml` |

The independent converter tail (13 externals + a few zoo-adjacent): `gafiatulin`=4, `Intiser`=2, `warshanks`=2, `bryanbblewis11`=2, `CarstenL`=1, `mweinbach`=1, `lenitas`=1.

**"Official" is a misnomer worth stating precisely:** official entries are `apple_export_recipe: true` (converted via Apple's recipes) but still `community_packaged: true`, hosted by `mlboydaisuke`. Apple hosts nothing.

### 1.2 How a model is added today (the real 4-file flow)

Per `CONTRIBUTING.md` and `templates/`:

1. Append a hand-written entry to `catalog.yaml` — **19 required fields**, `additionalProperties: false` (`schema/model.schema.json`).
2. Append an `artifacts.yaml` entry whose `id` == the model's `artifact_ref`, with an `officiality` block that must be logically consistent with `source_group` (audit-enforced), **and manually bump `artifacts.yaml metadata.count`**.
3. Add `sources.yaml` / `upstreams.yaml` records if any converter/host/upstream is new.
4. Optionally append a `benchmarks.jsonl` row.
5. Run `python scripts/validate.py`, `python scripts/audit.py` (9 categories), `python scripts/generate.py`, then `git diff --exit-code docs/ dist/`.
6. Commit YAML + regenerated derivatives, open a PR. **Human merge only — there is no model-PR automation lane.**

### 1.3 How a benchmark is added today

`benchmarks.jsonl` is append-only (65 entries, all `upstream_readme_manual/scripted`, `device_verified: false`, **zero signatures**). The *intended* path is: run the protocol (`benchmarks/protocol-config.json` v1.0) → POST to a Cloudflare "privacy relay" that coarsens device data, Ed25519-signs, and opens a bot PR → `benchmark-validate.yml` runs 8 auto-merge gates → `gh pr merge --squash`. **The relay is reference code only** (`.internal/relay/worker-reference.ts`; "actual deployment lives in a separate private repo"), **no relay URL exists anywhere in the repo**, direct unsigned PRs are rejected by design, and the worker hardcodes `device_verified: false` so even a signed submission can never satisfy the gate. The only completable path is a maintainer-reviewed issue form.

### 1.4 How a model is consumed today

`coreai-catalog install <id>` downloads from HF via the `hf` CLI (no `--revision`, no sha256 — verification = counting `*.aimodel` dirs), writes a `manifest.json`, and generates a `snippet.swift`. The snippet is one of 6 templates picked by runner bucket, explicitly labeled "Conceptual", and does not compile. `examples/` contains **only 4 README.md files, zero `.swift` files, zero `Package.swift`**. All typed IO questions are deferred to the external `apple/coreai-models` repo.

---

## 2. Redteam findings by theme

Severity legend: **P0** = breaks the loop / trust hole; **P1** = forces failure or misdirection; **P2** = papercut/friction; **P3** = cosmetic-but-wrong-fact. Verdicts as verified against source.

### 2.1 Theme A — The contribution loop (adding a model)

| # | Finding | Sev | Verdict |
|---|---|---|---|
| A1 | **Following `CONTRIBUTING.md` §4 verbatim yields a permanently red PR.** Step 4 tells you to append a benchmark row; any PR touching `benchmarks.jsonl` triggers `benchmark-validate.yml`, whose Ed25519 gate hard-fails unsigned lines ("direct PRs must go through the relay"). No relay URL is documented; CONTRIBUTING never mentions the signature requirement, the 1-line rule, or splitting PRs. The agent cannot reach green and cannot discover why. | **P0** | CONFIRMED (`CONTRIBUTING.md:97-109` vs `benchmark-validate.yml:3-7,32-46`, `verify_benchmark_signature.py:44-46`) |
| A2 | **Artifact schema forces fabricated GitHub provenance for HF-only conversions.** `artifact.schema.json` makes `github:{owner,repo}` required; an HF-only conversion has no GitHub repo, so the established convention is to fabricate a github block mirroring the HF coords (`whisper-large-v3-turbo-carstenl`). A source-grounded registry mandating fake provenance is a trust hole. | **P0** | CONFIRMED (`schema/artifact.schema.json:6,19`; `artifacts.yaml` CarstenL/Intiser entries) |
| A3 | **`templates/model-entry.yaml` suggests enum values the schema rejects.** Template comments offer `status: unverified`, `maturity: deprecated`, `availability: not_published` — all rejected by `model.schema.json`. Worse, `not_published` collides with the CONTRIBUTING rule to prefer `not_published` over `unknown`, teaching the wrong value for `availability` (whose only fallback is `unknown`). | **P1** | CONFIRMED (`templates/model-entry.yaml:21,44-45` vs `model.schema.json:95-98,204-210`) |
| A4 | **CONTRIBUTING's benchmark example is triple-invalid.** Uses `observed` (schema: `observed_date`, `additionalProperties:false`), `extraction_method: upstream-readme` (not in enum), `os_major` as number; prose required-list omits schema-required `compute_unit`. | **P1** | CONFIRMED (`CONTRIBUTING.md:102-109` vs `benchmark.schema.json`) |
| A5 | **Dual benchmark stores publish contradictory data.** A valid JSONL benchmark counts in `dist/leaderboard.json` (built from JSONL) but is absent from `dist/benchmarks.json` and `docs/compare` (built from legacy `benchmarks.yaml`), and is never audited (`audit.py` reads YAML). The JSONL→export reshape also drops `device_class` (leaderboard shows `device: null`). 65 vs 66 entries already drifted. | **P1** | CONFIRMED (`exports.py:45`, `generate.py:285`, `audit.py:38` read YAML; `catalog.py:236-257` prefers JSONL; `formatters.py` whitelists `device` not `device_class`) |
| A6 | **No scaffolding write path.** 15 CLI subcommands, none create entries; 12 MCP tools, all read-only; `model-request.md` is free-form markdown collecting ~8 of 19 schema-required fields. No issue-form-to-PR bot; only benchmarks auto-merge. Adding a model is 4-file YAML surgery. | **P1** | CONFIRMED (`cli.py:1284-1397`, `mcp_server/server.py`, `.github/workflows/`) |
| A7 | **Hand-maintained `metadata.count` bump documented nowhere.** `audit.py` cat.8 fails when `metadata.count != len(artifacts)`; CONTRIBUTING and the artifact template never mention it. Actionable error → recoverable, but a pure papercut generator. | **P2** | CONFIRMED (`artifacts.yaml:4`, `audit.py:177-185`) |
| A8 | **`sources.yaml` has no schema.** Invented `trust`/`volatility` vocabulary passes silently; the trust-metadata file is the one unvalidated entity type. | **P2** | CONFIRMED (no `schema/source.schema.json`; `validate.py:63,85` uses sources only as an id set) |
| A9 | **Validation is fail-slow.** `validate.py` exits at the first failing entity category; three coexisting errors need three round-trips. No error aggregation, no fix hints. | **P2** | CONFIRMED (`validate.py:27-40,55-57,125-162`) |
| A10 | **Discovery-layer docs carry stale facts.** CONTRIBUTING's generated-files table lists `benchmarks.yaml` and omits `.jsonl`/`compare`/`tasks`; AGENTS.md tells agents to append to `benchmarks.yaml`; `server.py:56` says "79 models" (catalog has 80). Wrong facts ingested during discovery, in a source-grounded project. | **P3** | CONFIRMED (`CONTRIBUTING.md:9-17`, `AGENTS.md:104`, `server.py:56`) |

### 2.2 Theme B — The benchmark loop (submitting a score)

| # | Finding | Sev | Verdict |
|---|---|---|---|
| B1 | **No benchmark runner exists.** The protocol says "Load model via CoreAIRunner" but the repo has zero executable measurement code — no Swift harness, no `Package.swift`, no CLI runner. An agent must author a Swift app from a prose spec before producing one number; `gemma-4-12b` additionally needs `custom_kernel`/`patch_required` zoo patches the catalog neither ships nor links. | **P0** | CONFIRMED (no `.swift`/`Package.swift` in repo; `docs/benchmark-protocol.md`; `catalog.yaml` gemma-4-12b runtime) |
| B2 | **No completable submission transport.** Relay endpoint doesn't exist publicly; direct PRs fail the signature gate by design; the issue form requires a human. Fully autonomous submission is architecturally impossible, not merely undocumented. | **P0** | CONFIRMED (repo-wide grep: no relay URL; `worker-reference.ts:11-12`; `verify_benchmark_signature.py:44-46`) |
| B3 | **Auto-merge is unreachable even via the relay; Mac results can never be device-verified.** Gates require `device_verified==true` + `extraction_method==app_benchmark_protocol`, but the worker hardcodes `device_verified:false` ("Phase 3"). DeviceCheck (`verify_devicecheck.py`) is invoked by no workflow and is iOS-only — a Mac CLI agent (the catalog's core persona) is permanently locked out of the trusted tier. | **P0** | CONFIRMED (`worker-reference.ts:142-146`, `benchmark-validate.yml:82-83`; DeviceCheck unwired) |
| B4 | **CONTRIBUTING benchmark instructions produce invalid entries and never mention signing.** (Same drift as A4, plus zero mention of the Ed25519/1-line rules.) | **P1** | CONFIRMED |
| B5 | **Three conflicting device-coarsening tables; a base M4 MacBook is misclassified as "M4 Max".** `protocol-config.json` maps `Mac16→mac-m4-max`; docs agree; the worker has no `Mac16` entry and maps `Mac15,11+→M4 Max`; actual JSONL uses the bare chip string. `Mac16,1` is the base M4 (~120 GB/s) binned with M4 Max (~546 GB/s) — ~4.5× bandwidth gap corrupting medians and any physics gate. | **P1** | CONFIRMED (`protocol-config.json`, `benchmark-protocol.md`, `worker-reference.ts:88-125`, `benchmarks.jsonl`) |
| B6 | **Even a merged benchmark is partly invisible.** `docs/compare` and `dist/benchmarks.json` and `audit.py` still read `benchmarks.yaml`. (PARTIAL: leaderboard/search-index/CLI/MCP DO see JSONL via `Catalog.load`, so it's not fully write-only — it's missing from compare docs, `dist/benchmarks.json`, and audit counts.) | **P1** | PARTIAL (`generate.py:285`, `exports.py:45`, `audit.py:39` read YAML; but `exports.py:87,321` read `cat.benchmarks`=JSONL) |
| B7 | **Install yields unpinned, unverifiable bytes.** No HF revision pin, no sha256; success = counting `*.aimodel` dirs. A benchmark cannot name which bytes it measured; the benchmark schema has no artifact-revision/digest field. Upstream can silently swap weights. | **P1** | CONFIRMED (`installer.py:139-166`; `artifacts.yaml`; `benchmark.schema.json`) |
| B8 | **No `bench` entrypoint anywhere.** No CLI `bench` verb, no MCP draft/validate/submit benchmark tool. | **P2** | CONFIRMED (`cli.py`, `mcp_server/server.py`) |
| B9 | **Trust gates evaluate self-reported or absent fields.** Missing thermal data defaults to `unknown` and *passes* the thermal gate (omitting telemetry is easier than providing it); outlier check passes any cohort <5 (true for every current cohort). Only the signature is actually verifiable. | **P2** | CONFIRMED (`benchmark-validate.yml:85`, `outlier_check.py:56-57`) |
| B10 | **The signature pipeline's own integration test never runs in CI.** `tests/test_benchmark_pipeline.py` skips without the uncommitted `.internal/relay-privkey.pem`, and CI only runs `tests.test_error_resilience`. | **P3** | CONFIRMED (`test_benchmark_pipeline.py:29-35`, `validate.yml:78`) |

### 2.3 Theme C — The consumption loop (integrating in Swift)

| # | Finding | Sev | Verdict |
|---|---|---|---|
| C1 | **The installed snippet for the #1 OCR recommendation is a text-only chat template with no image input path.** `unlimited-ocr` (runner `stock-runner`, inputs `[document_image, image]`) is routed to the LLM bucket and emits `session.respond(to: "Hello, how are you?")` — zero image/attachment/vision calls — for a document-image model. The one runnable-looking artifact points *away* from the task. | **P0** | CONFIRMED (reproduced via `_generate_swift_snippet`; `installer.py:352-374`; `catalog.yaml` unlimited-ocr) |
| C2 | **No machine-readable typed-IO contract exists anywhere.** The only IO structure is `modalities.input/output` free-form strings. No Swift type, no tensor shape/dtype, no preprocessing spec (despite `processor_required:true`), no output decoding rules, no entrypoint binding. The GraphModel fallback literally says "Input key names vary by model — check the model spec in apple/coreai-models". The `.aimodel` bundle's own `metadata.json` carries real typed metadata the installer never parses. | **P0** | CONFIRMED (`model.schema.json:61-85`; `installer.py:392-399`; `apple-terminology-map.md`) |
| C3 | **Nothing binds the installed artifact to the Swift code.** Weights land in `~/.coreai-catalog/...` but the snippet inits `CoreAILanguageModel()` with no path; the fallback assumes `Bundle.main`. No doc explains getting the `.aimodel` from the home-dir cache into an iOS app bundle. For an iOS target a Mac-side cache path is definitionally wrong. | **P1** | CONFIRMED (`installer.py:88-104,364,388`; no Xcode-integration doc) |
| C4 | **The OCR example contradicts the catalog and nothing compiles.** `examples/ocr-swiftui/README.md` says Apache-2.0 / Encoder while `catalog.yaml` says MIT / transformer; all example code is "conceptual", zero `.swift` files exist. | **P1** | CONFIRMED (`ocr-swiftui/README.md:101-102` vs `catalog.yaml`) |
| C5 | **`bundle_kind` heuristic mis-buckets the OCR model as `llm`** in `dist/model-manifest.json` (the closest agent-facing integration contract), because it's derived at export time and `document-ocr` matches no vision bucket. A remote agent using the manifest takes the same wrong turn. | **P1** | CONFIRMED (`model-manifest.json`; `exports.py:273-288`) |
| C6 | **Output contract is ambiguous.** `[markdown, html, latex]` with no selection/parsing semantics: notes imply automatic mixed output, the example implies prompt control. The agent can't write the parser. Catalog-wide: 18 uncontrolled output strings incl. both `score` and `scores`. | **P1** | CONFIRMED (`catalog.yaml`; `model.schema.json:75-83`; 18 unique outputs verified) |
| C7 | **`processor_required`/`tokenizer_required` are dead-end booleans.** No which-processor, no config location, no preprocessing ops, no `max_image_px`. `context_window` exists on 1/80 models. | **P2** | CONFIRMED (`catalog.yaml`; `model.schema.json:155-166`) |
| C8 | **Remote/MCP agents cannot obtain any integration code.** Snippets are install-gated (CLI-only); no MCP tool or dist export carries them. (PARTIAL: `docs/getting-started.md` does signpost `examples/`, but that doc is itself unreachable from any agent-facing surface.) | **P2** | PARTIAL (grep: no `snippet`/`examples/` in `server.py`/`exports.py`; `getting-started.md:75-97` exists but unlinked) |
| C9 | **Post-install the agent has no file-level knowledge:** no revision pin, no hashes, no bundle inventory. The docstring claims hash verification; no hashing code exists. | **P2** | CONFIRMED (`installer.py:7,76,139-166`; `artifacts.yaml`) |
| C10 | **Example caveats make unsourced capability claims** ("handles printed and handwritten text in multiple languages") absent from `catalog.yaml`, violating the project's own never-fabricate discipline. | **P3** | CONFIRMED (`ocr-swiftui/README.md:109` vs `catalog.yaml`; `SKILL.md:52`) |

### 2.4 Theme D — Trust & abuse surface

| # | Finding | Sev | Verdict |
|---|---|---|---|
| D1 | **Artifact/upstream substitution is undetectable** (no revision pin, no sha256, no derivation check). `validate.py`'s only "provenance" check is a substring self-consistency test; the installer's hash step is a permanent no-op. An attacker can point `artifact_ref` at their own repo or swap weights post-merge; agents install malicious/mismatched bytes. | **P0** | CONFIRMED (`validate.py:97-106`, `audit.py:110-123`, `installer.py:76`, no digest fields) |
| D2 | **License laundering.** No join between a model's claimed license and its upstream's actual terms. Claiming "Apache-2.0 / likely" for a Gemma/Llama/SAM derivative passes validate + audit; `check_license` then reports it commercial-safe. (`deep_audit.py` has license logic but is wired into no workflow and only checks the inverse direction.) | **P0** | CONFIRMED (`model.schema.json:192-203`; no license join in validate/audit; `deep_audit.py` unwired) |
| D3 | **Benchmark fabrication passes all value gates.** Outlier check returns pass for cohort<5 (every current cohort) and for `MAD==0`; no memory-bandwidth ceiling, no tokens/elapsed consistency. A fabricated benchmark also adds +10 readiness, gaming recommendations. (Auto-merge still needs a relay signature, so fabrication needs relay/key access — but the *value* gates are blind.) | **P1** | CONFIRMED (`outlier_check.py:57-70`; `catalog.py` SCORING_WEIGHTS) |
| D4 | **Benchmark trust collapses to one committed relay pubkey** with no rotation, revocation, or per-submitter identity binding. Key leak → auto-flowing fabrications; honest external contributors locked out. | **P1** | CONFIRMED (`verify_benchmark_signature.py:27`; no rotation/revocation anywhere) |
| D5 | **JSONL benchmarks bypass `audit.py` entirely** (duplicate-ID / date-format checks never run on the source of truth). (PARTIAL: dangling `source`/`model_id` refs and bad dates in JSONL *are* caught by `validate.py` + per-line schema; the real gap is no duplicate-benchmark-ID check for JSONL + stale YAML audit.) | **P1** | PARTIAL (`audit.py:39`; `validate.py:108-114` does cross-ref JSONL) |
| D6 | **Prompt injection via unsanitized free-text `notes`/`name`** surfaced verbatim by MCP `get_model`/`recommend_model`, zero sanitization. A data-to-instruction confusion vector into downstream agents. (PARTIAL: the model-selection SKILL doesn't explicitly say "read notes", but the MCP output surface is real.) | **P1** | PARTIAL (`model.schema.json:236-238`; `server.py:180`; `catalog.py:528`; no sanitizer) |
| D7 | **Typosquat/homoglyph IDs & alias collisions** — `audit.py` catches only exact-duplicate IDs (Counter); no NFKC/edit-distance/reserved-namespace check. (PARTIAL: `install <alias>` does NOT resolve via `aliases.json` — it's exact ID lookup — so the specific alias-hijack mechanism doesn't exist; the human/agent-confusion risk does.) | **P1** | PARTIAL (`audit.py:52-62`; `cli.py:661-663` exact lookup; `aliases.json` has no consumers) |
| D8 | **`source_group: external`/`unknown` bypass officiality logic, and self-declared sources satisfy the cross-ref** (a PR can add its own `sources.yaml` record in the same change → self-referential provenance). | **P2** | CONFIRMED (`audit.py:144-161`; `validate.py:93-95`; no trusted-host allowlist) |

### 2.5 Theme E — Resilience (zoo collapse & drift)

| # | Finding | Sev | Verdict |
|---|---|---|---|
| E1 | **No revision pinning or hash verification anywhere** — a force-pushed or swapped HF artifact is silently installed and trusted; the manifest hardcodes `source_available:True`. Only 1/80 artifacts has a `verification` block, and its `sha` is null. "Verified" refers to a URL, not to bytes. | **P0** | CONFIRMED (`installer.py:76,106-108,145-166`; `artifacts.yaml`) |
| E2 | **Deletion/takedown is undetectable.** `sync_upstream.py`'s `removed_from_upstream` key is dead code and it always exits 0; `validate_links.py` is wired into no workflow; `source_monitor.py` only flags NEW models. If the zoo or `mlboydaisuke` vanished, 64/80 source URLs + 67/80 artifacts 404 with CI staying green. | **P0** | CONFIRMED (`sync_upstream.py:98,199`; no `validate_links` in workflows; `source_monitor.py:109`) |
| E3 | **84% of artifacts hang off one personal HF account whose identity is hardcoded in 3 tools, with zero mirror support.** The schema allows one `huggingface` block — a mirror can't even be recorded. Failover to `coreai-community` needs edits across ≥3 scripts + `artifacts.yaml` + README + CREDITS. No doc mentions mirroring/takedown. | **P1** | CONFIRMED (67/80; `sync_upstream.py:111`, `source_monitor.py:31`, `check_sources.sh:43`; single HF block in schema) |
| E4 | **No deprecation/supersession lifecycle.** `deprecated` status is inert in search/recommend/scoring (only `confirmed` gets +10); no `superseded_by`; `last_verified` only regex-checked, never staleness-checked. Upstream v2 releases are undetectable. | **P1** | CONFIRMED (`catalog.py:82-99,440-441`; `audit.py:188-192`; no consumer of deprecated) |
| E5 | **No `.aimodel` format-version / toolchain-version tracking.** No `format_version`, `converted_by`, or `min_os` field — an Apple format revision is inexpressible; a fleet-wide break would be silent. | **P1** | CONFIRMED (grep: no such fields in `model.schema.json`/`catalog.yaml`; `artifact.schema.json` conversion_script is a bare path) |
| E6 | **Deployed site hard-depends on `raw.githubusercontent.com` main-branch URLs** while `pages.yml` copies only `site/*` (not `dist/`). Any of {raw availability, repo public, branch named `main`} failing blanks the UI. Avoidable SPOF — the same push already has validated `dist/` in the checkout. | **P2** | CONFIRMED (`site/app.js:8-10,40-56`; `pages.yml` build step) |
| E7 | **The artifact `verification` field is populated for 1/80** — and that one says `unverified`, `sha: null`. Two "verified" vocabularies (catalog-side + installer-side), neither backed by an executed check. | **P2** | CONFIRMED (`grep -c verification: artifacts.yaml == 1`; `installer.py:106-108`) |
| E8 | **The only availability watchdog (`check_sources.sh`) hardcodes the maintainer's laptop path** and can't run in CI. Bus factor = one laptop being on. | **P2** | CONFIRMED (`check_sources.sh:10`) |
| E9 | **Freshness metadata is hand-maintained and never audited for staleness** — `source-grounded` claims can silently rot; `volatility` has zero consumers. | **P3** | CONFIRMED (`audit.py:188-192`; `sources.yaml`; grep) |

### 2.6 Theme F — Maintainer AX (running the registry as an agent)

| # | Finding | Sev | Verdict |
|---|---|---|---|
| F1 | **Benchmark auto-merge lane is structurally impossible** — 0% auto-merge by construction; every submission lands in the curator queue. The signature round-trip is never even exercised in CI. | **P0** | CONFIRMED (`benchmark-validate.yml:82-83,172-186`; `worker-reference.ts:146`; `test_benchmark_pipeline.py` skips) |
| F2 | **Official docs/templates produce schema-invalid, CI-failing PRs** (A3+A4+A10 combined: template enums, benchmark example, AGENTS.md `benchmarks.yaml` playbook). The documented contract disagrees with the enforced contract. | **P0** | CONFIRMED |
| F3 | **Validators are fail-fast and prose-only** — no `--json`, no GitHub annotations, no file/line mapping. An auto-triage agent must regex free prose out of Actions logs. Given that agentic-PR merge success correlates with strict, *actionable* CI, this is the highest-leverage triage gap. | **P1** | CONFIRMED (`validate.py:38,55-57`; `audit.py` plain text; no argparse) |
| F4 | **`scripts/discover.py` is orphaned and its dedup can't match anything.** Not a CLI subcommand, not scheduled; `repo_key='org/name'` compared against converter-owned HF repos (stored as bare names without owner) — the membership test can *never* match; name fallback is exact-set, not fuzzy. Already-ported models rescore as top candidates. | **P1** | CONFIRMED (`discover.py:7-12,125,131-144`; `cli.py` 15 subcommands; no workflow) |
| F5 | **Source monitor files a duplicate issue every 3 hours** (stateless, no existing-issue check) and never drafts entries. Up to 8 duplicate issues/day per backlog item. | **P1** | CONFIRMED (`source-monitor.yml:6,41-56`; `source_monitor.py:109`) |
| F6 | **No executable governance.** No CODEOWNERS, no GOVERNANCE.md, no `on: issues`/@-mention workflow, and a free-form `model-request.md` missing most schema-required fields. No path from "issue filed" to "draft PR". | **P1** | CONFIRMED (`.github/` listing; workflow triggers; `model-request.md`) |
| F7 | **Dual benchmark stores** (audit/generate/exports read YAML, CI enforces JSONL) — auto-merged data is unaudited and missing from compare docs. (PARTIAL as B6.) | **P1** | PARTIAL |
| F8 | **No deletion/drift detection + no content pinning** for a catalog 84% dependent on one HF account. (Consolidates D1/E1/E2.) | **P2** | CONFIRMED |
| F9 | **Version/count facts drift across surfaces** with no single-source enforcement (`server.py` "79", manual `metadata.count`, `publish.py` bumps only 2 of 6 surfaces). | **P2** | CONFIRMED (`server.py:56`; `publish.py`; `copilot-instructions.md:43-44`) |
| F10 | **MCP error responses lack the actionable hints the CLI already has** — bare `{"error": "not found"}` vs the CLI's near-miss suggestions and valid-value lists; `resolve_task` silently guesses. | **P3** | CONFIRMED (`cli.py:150-171,594-599` vs `server.py:157,302,340`; `catalog.py` resolve_task fallback) |

**Tally:** 8 P0, 20 P1, 12 P2, 6 P3 (46 distinct findings; several appear across themes). No finding was refuted; the PARTIALs (B6, C8, D5, D6, D7, F7) have a real core with one overstated evidence leg.

---

## 3. The SotA target architecture — a fully agent-first catalog

The design principle (Netlify's AX doctrine, four pillars): **Access, Context, Tools, Orchestration**, all optimizing the *shortest path for an agent to achieve an outcome*. Every write path funnels into a **PR gated by schema CI** (the gh-aw "safe outputs" philosophy) so agents contribute autonomously while humans keep merge authority. Below, each loop's target state.

### 3.1 Agent-writable contribution (draft → validate → PR)

**One contract, four entry points, one gate** (the models.dev pattern):

- **New MCP write tools** that validate locally then open a PR via the GitHub API using the caller's token, with **MCP elicitation** to fill missing required fields and show a rendered diff before the irreversible PR:
  - `draft_model(...)` → assembles `catalog.yaml` + `artifacts.yaml` (+ `sources.yaml`) edits, bumps `metadata.count`, runs validate/audit/generate, returns a diff.
  - `submit_model(...)` → forks/branches/PRs the validated draft.
  - `validate_entry(kind, payload)` → pre-flight any model/artifact/benchmark entry, returning **aggregated** field-level errors with fix hints (never one-at-a-time).
- **New CLI command** `coreai-catalog contribute model` (interactive + flag-driven): prompts for schema fields with enum validation (enums rendered *from* the schema), writes all touchpoints, runs the local gate, opens a branch/PR via `gh`.
- **GitHub Issue Forms** (`model-request.yml`, replacing free-form markdown) whose fields map 1:1 to `model.schema.json` (dropdowns for every enum), parsed by an action into a **draft PR** — codeless contribution for repo-clone-less agents.
- **`@claude` / Copilot enabled** so free-text submissions ("add model X from this URL") land as reviewable PRs.

**Schema-as-single-contract:** generate `templates/*.yaml` and all CONTRIBUTING/AGENTS examples *from* the JSON Schemas at `generate.py` time; a CI doc-test validates every fenced example and template against its schema so drift fails the build. Add `schema/source.schema.json`. Aggregate validator errors + emit GitHub annotations with file+line.

### 3.2 Autonomous benchmark submission with attestation (zero central hardware)

The credible pipeline is layered (MLPerf + lm-eval-harness + BOINC + sigstore + Geekbench + physics), needing **no central GPU/Mac**:

1. **Pinned open-source runner** `coreai-catalog bench run <id>`: implements `protocol-config.json`, captures environment + thermal telemetry (`ProcessInfo.thermalState` / `powermetrics`, reject `Throttle: yes`), fixed seeds, median-of-N with warmup discard, emits **raw per-trial JSONL + a run manifest** embedding runner version, artifact **sha256 + HF revision**, seed, a **freshness nonce** (repo HEAD SHA), and self-check flags.
2. **Sigstore keyless signing** (`cosign attest-blob --type https://coreai-catalog.dev/benchmark-run/v1`) binds the manifest to the submitter's real **GitHub OIDC identity** in Rekor's append-only log — replacing the private-relay SPOF and giving any agent a completable signature step.
3. **CI gate** (`verify-benchmark-pr.yml`): verify signature/identity == PR author + Rekor inclusion; schema + internal-consistency (tokens/elapsed math); **physics plausibility** — decode tok/s ≤ ~95% of per-chip memory-bandwidth ceiling (`chips.yaml`); canary checks; recompute summaries from raw JSONL.
4. **BOINC-style quorum tiers** (`verification_tier` schema field): `Unverified (n=1)` → `Community-verified` when a second independent identity reproduces within tolerance (exact for seeded quality, ±10% for throughput); `Hardware-attested` reserved for iOS App Attest companion-app submissions; `Maintainer-verified`; `Disputed`. **Tier-aware auto-merge** (not binary `device_verified`).
5. **MLPerf-style flag/challenge window** + append-only history; display medians with `n=`, never a single best run.

Single benchmark store: `benchmarks.jsonl` read by `generate.py`, `exports.py`, `audit.py`; `benchmarks.yaml` retired; `device_class` preserved into exports.

### 3.3 Machine-readable typed Swift-IO contracts per model

Add an authored `io_contract` block to `model.schema.json`, bootstrapped by parsing each `.aimodel` bundle's `metadata.json` at install/CI time:

```
io_contract:
  entrypoint: {framework, type, init_pattern}
  inputs:  [{name, modality, swift_type, tensor:{shape,dtype,layout},
             preprocessing:{resize,normalization,color_format,sample_rate},
             constraints:{max_context,max_image_px,max_audio_s}}]
  outputs: [{name, swift_type, decoding:{format_selector,coordinate_convention,
             label_vocab_ref,embedding_dim,score_range,detokenization}}]
  session: {stateful, streaming}
  files:   {tokenizer_ref, processor_ref}   # paths in the pinned HF revision
```

- **`bundle_kind` becomes authored** (schema enum incl. `ocr`/`vlm`), with the `exports.py` heuristic demoted to a validator that fails on disagreement (e.g. image-input model bucketed `llm`).
- **Snippets generated from the contract, modality-aware** (image input → attachment code path; the contract interpolates the resolved local artifact path + `.aimodel` bundle name). A CI check asserts every generated snippet references each declared input modality.
- **Compile-checked example packages** — one SwiftPM package per `bundle_kind`, `swift build` in a macOS CI job (the transformers-to-mlx machine-verified-examples pattern), versioned against the Core AI SDK.
- **Expose the contract** in `dist/model-manifest.json` and a new MCP `get_integration_snippet(model_id)` so remote agents aren't install-gated. Enumerate the modality vocabulary (fix `score`/`scores`) and publish a modality→Swift-type doc generated from the schema.
- **Documented last mile:** `coreai-catalog install --xcode-project <path>` (or printed drag-in instructions with the resolved bundle filename); iOS vs macOS load guidance.

### 3.4 Upstream-agnostic publishing protocol (stop being zoo-dependent WITHOUT hosting weights)

The catalog stays an **index, never a host** (validated by Ollama-over-HF). Independence comes from a **recipe-based publishing protocol** anyone — including agents — can execute:

- **`coreai-catalog publish-artifact` skill/command** (the winning move historically = owning the default publish command, à la `mlx_lm.convert`): convert upstream → `.aimodel` (Apple recipe or zoo re-authoring) → run **codified Gate A/B parity checks** (the zoo's `PORTING.md` convention: graph cosine ≥ 0.999, per-token logit cosine ≥ 0.999 + greedy token-exact for LLMs) → generate a **normalized model card** (provenance, `base_model`, toolchain versions, gate outputs, device benchmarks) → **upload to the publisher's OWN HF repo** (default target: the `coreai-community` org, open-join, where Pedro Cuenca/HF's Apple lead already sits) → generate the `catalog.yaml`/`artifacts.yaml` entries → stage a catalog PR for human acceptance.
- **Provenance as verifiable data, not schema-forced fiction:** make `github` optional (`anyOf(github, huggingface)`); add per-artifact `converted_by:{tool, version, recipe_url}`, `revision` (HF commit hash), per-file `sha256`, `format_version`, an optional `mirrors: [{owner,repo,revision}]` array, and `recipe_source` (`apple-official | zoo-port | independent`). Weight readiness by verification tier and recipe source.
- **Content-addressed install:** download by pinned revision, verify digests, fail hard on mismatch; CI flags when an indexed repo mutates past the verified revision. This ends the weight-swap and host-concentration exposure without hosting a byte.
- **License pass-through enforcement:** `audit.py` joins each model's declared license to its upstream's terms; auto-forces `commercial_use: check_license` for any derivative of a `review_required` upstream.

### 3.5 Discovery automation & executable governance

- **`coreai-catalog discover`** as a real subcommand + weekly workflow that upserts a *single pinned* "Porting candidates" issue; dedup fixed via an authored `upstream_repo` (`org/name`) field + HF `base_model` metadata (also fixes `sync_upstream.py`/`source_monitor.py` fuzzy matching).
- **Source monitor** dedups against open `source-monitor` issues and, on detection, an agent job (gh-aw safe-outputs) fetches the HF/zoo metadata, fills the templates, runs the local gate, and its **only permitted output is a draft PR** — Kevin reviews a validated diff, not a link list.
- **Deletion/drift detection:** wire `validate_links.py` into a daily workflow that populates `removed_from_upstream` and flips a per-model `availability` field; retire `check_sources.sh` into the scheduled Action.
- **Lifecycle:** `superseded_by` + `deprecation:{date,reason}`; search/recommend exclude deprecated by default; a staleness-budget audit category per volatility tier; weekly upstream-release diffing.
- **`GOVERNANCE.md` as checkable rules** an agent executes and a human countersigns: *mergeable = CI green + `source_path` resolves HTTP 200 + officiality consistent + license compatible with upstream + submitter-linked provenance*. Add `.github/CODEOWNERS`.
- **Single-source facts:** derive `metadata.count`, the MCP instruction string, `agent.json`/`openapi`/README stats at generate time; extend the CI sync-gate to cover them; assert no hardcoded model counts outside generated files.
- **MCP error parity:** shared not-found/empty-filter/unresolved-task helpers returning suggestions + hints (AX "shortest path").

---

## 4. Prioritized roadmap

Ordering rule from the agentic-PR literature: **strict, actionable CI is the single highest-leverage investment** because it is what makes agent PRs mergeable. So the P0 tier front-loads (a) unblocking the documented loops and (b) the schema/CI contract, before net-new tooling.

### P0 — Unblock the loops & close the two trust holes (weeks 1-3)

| Deliverable | Addresses | Concrete change |
|---|---|---|
| **Fix the CONTRIBUTING/benchmark deadlock** | A1, A4, B2, B4, F1, F2 | Document that model PRs must NOT touch `benchmarks.jsonl`; route unsigned `upstream_readme_*` entries to a labeled curator lane instead of hard-fail; state the relay is not yet public; correct the benchmark example (`observed_date`, enum, `compute_unit`). |
| **Schema-generated docs/templates + doc-test CI** | A3, A4, A10, F2, F9 | Generate `templates/*.yaml` + CONTRIBUTING examples from schemas; CI validates every fenced example/template; derive all counts/version strings at generate time; fix `server.py` "79→80". |
| **`validate_entry` MCP tool + `contribute model` CLI (draft→validate→PR)** | A6, F3, F6 | New write tools; aggregate all validation errors with fix hints; emit GitHub annotations. |
| **Content-addressing: `revision` + per-file `sha256` in `artifacts.yaml`; verifying installer** | B7, C9, D1, E1, F8 | Make `github` optional (`anyOf`); install `--revision`, verify digests, fail on mismatch; stop hardcoding `verified:True`. |
| **License-upstream join in `audit.py`** | D2 | Force `commercial_use: check_license` for `review_required` derivatives; fail on permissive-over-restrictive claims. |
| **Single benchmark store** | A5, B6, D5, F7 | Point `generate.py`/`exports.py`/`audit.py` at `benchmarks.jsonl`; preserve `device_class`; retire `benchmarks.yaml`; CI guard against its return. |
| **`schema/source.schema.json` + validate `sources.yaml`** | A8, D8 | Enums for `type`/`trust`/`volatility`; require ≥1 source to resolve to a trusted-host allowlist, not a same-PR record. |
| **Wire `validate_links.py` into a daily workflow; populate `removed_from_upstream`** | E2, F8 | File an `availability-regression` issue; flip per-model `availability`. |

### P1 — Agent-first write paths & typed IO (weeks 3-8)

| Deliverable | Addresses | Concrete change |
|---|---|---|
| **Pinned open-source runner `coreai-catalog bench run`** | B1, B8 | SwiftPM harness implementing `protocol-config.json`; raw JSONL + manifest (sha256, revision, seed, nonce, thermal, self-checks); published via GitHub Releases with artifact attestations. |
| **Sigstore keyless submit + `verify-benchmark-pr.yml`** | B2, B3, B9, D3, D4, F1 | `cosign attest-blob` bound to GitHub OIDC; CI verifies identity==author; `chips.yaml` physics ceiling; `verification_tier` field + tier-aware auto-merge; medians with `n=`. |
| **`io_contract` schema block + authored `bundle_kind`** | C1, C2, C5, C6, C7 | Parse `.aimodel` `metadata.json`; snippet generator becomes modality-aware; CI asserts snippet references each input modality; enumerate modality vocab. |
| **Compile-checked example packages + install last-mile docs** | C3, C4, C8, C10 | One SwiftPM package per `bundle_kind`, `swift build` in macOS CI; generate example capability tables from `catalog.yaml`; `install --xcode-project`; `get_integration_snippet` MCP tool. |
| **`draft_model`/`submit_model` MCP tools + issue-form-to-PR** | A6, F6 | Elicitation for missing fields + diff preview; `model-request.yml` issue form (1:1 with schema); parser action → draft PR; enable `@claude`. |
| **Recipe-based publishing: `publish-artifact` skill + provenance fields** | E3, E5, §3.4 | `converted_by`, `format_version`, `recipe_source`, `mirrors[]`; Gate A/B parity report convention; default publish target `coreai-community`. |
| **Discovery + governance automation** | E4, F4, F5, F6 | Real `discover` subcommand + pinned-issue workflow; `upstream_repo` field fixes dedup; `superseded_by`/`deprecation`; source-monitor dedup + draft-PR job; `GOVERNANCE.md` + `CODEOWNERS`. |
| **Prompt-injection hardening + typosquat detection** | D6, D7 | Delimit/typed untrusted free-text in MCP output + PR-time injection lint; NFKC + edit-distance/confusable check in `audit.py`; reserve alias namespace. |

### P2 — Resilience, self-host, polish (weeks 8-12)

| Deliverable | Addresses | Concrete change |
|---|---|---|
| **Self-host `dist/` on Pages** | E6 | `cp -r dist _site/dist` in `pages.yml`; `app.js` fetches relative `./dist/...` with raw URLs as fallback only. |
| **Required tri-state `verification` per artifact** | E7 | `unverified` / `smoke_passed` / `parity_report{url,sha}`; installer copies catalog state into manifest; weight readiness by tier. |
| **Portable availability watchdog** | E8, E9 | Retire `check_sources.sh` into the Action; auto-refresh `sources.yaml last_checked` via bot PR; staleness audit category per volatility tier. |
| **`metadata.count` auto-computed; remaining count/version single-source** | A7, F9 | Drop the manual bump; extend sync-gate. |
| **MCP error-hint parity + `resolve_task` pointer** | F10 | Shared helpers: near-miss ids, valid-filter values, `did_resolve:false` + `get_tasks` pointer. |
| **CI runs the signature round-trip** | B10 | Ephemeral Ed25519 keypair inside the test; run the pipeline test in `validate.yml`. |

---

## 5. Closing

The catalog's *bones are SotA*: index-not-host, officiality triage, YAML→generated derivatives, MCP/CLI/llms.txt/AGENTS.md read surface. What is missing is the **agent-write half of every loop** and the **verifiable-provenance layer** that makes autonomous contribution safe. The window is unusually open — the Apple Core AI ecosystem is three weeks old, `coreai-community` has ~7 models (not 7,000), no artifact has meaningful downloads, and canonical status is genuinely up for grabs. The team that ships the **default publish command + parity-gated provenance + agent-writable MCP tools** while the ecosystem is small plausibly becomes the naming/verification authority before consolidation happens elsewhere. Every P0 item is a file edit plus a deterministic local check that mirrors CI — i.e., the whole P0 tier is itself agent-completable.
