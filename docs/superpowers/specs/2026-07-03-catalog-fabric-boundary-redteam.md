# Catalog ↔ Fabric Boundary — Redteam & Verdict

**Date:** 2026-07-03
**Method:** 3 boundary auditors ran the catalog and fabric side by side with **live contract tests** (real `register --dry-run` AND non-dry-run against a scratch catalog copy, real catalog validators/tests on the injected entry, real `gh api`/`curl` on the fabric repo). The simulate/verify/synthesis phases were cut off by a monthly spend limit; the map phase (the highest-value, live-executed slice) completed and **two auditors independently reproduced the top P0** by running real commands — convergent, not speculative.
**Design intent under audit:** complementary (no overlapping responsibility), mutually aware (each surfaces the other at the moment of need), deeply conversant but **not dependent** (no runtime import; conversation via data contracts + PRs + cross-references), totally seamless for agents and humans.

---

## Headline

**The architecture is SotA and the data contracts are real, but the boundary is not yet functional.** The one loop that justifies fabric's existence — convert a new model → land it in the catalog — has a **0% completion rate by construction today**, and both repos' green CI actively hides it. `catalog.yaml` contains **zero `source_group: fabric` models**; all three fabric recipes are still `status: draft`.

---

## 1. Responsibility matrix — complementary?

**Split of responsibility: A−.** Clean, correctly layered, no runtime import in either direction, neither hosts weights:

| Concern | Fabric | Catalog |
|---|---|---|
| convert / Gate A+B parity / HF publish | ✅ owns | — (deliberately absent) |
| recipes | ✅ owns | — |
| index / entries / readiness score | — | ✅ owns |
| discovery / governance / MCP+CLI read surface | — | ✅ owns |
| benchmark protocol + sigstore attestation | — | ✅ owns |
| install digest verification | — | ✅ owns |

Parity (fabric, correctness-vs-upstream) vs benchmark (catalog, performance-with-attestation) vs installer digest (catalog, bytes-on-disk) are three genuinely distinct concerns, not overlap.

**Split of implementation: C (5/10).** Four concerns are implemented **twice with divergent rules and already drifting**, because the shared field contract lives only in prose comments + a stale vendored schema snapshot — not one executable artifact:

1. **Entry generation** — `fabric register.build_model_entry` vs `catalog contribute.build_model_entry`: two parallel generators of the same contract; fabric's emits audit-illegal values.
2. **License triage** — fabric 3-value `license_terms` enum + `PERMISSIVE_LICENSES` allowlist vs catalog 4-value enum + `NON_PERMISSIVE_LICENSE_TERMS` + `applies_to` join. Different vocab, different copyleft semantics, and **fabric models bypass the catalog's license-laundering guard entirely**.
3. **`huggingface.files` digests** — fabric hashes every file (incl. non-LFS); catalog backfill records LFS-only and `--refresh` clobbers fabric's non-LFS digests.
4. **The `coreai-fabric` `sources.yaml` record** — hardcoded in both repos with conflicting `trust`/`volatility` (`maintainer_primary`/`low` vs `project_primary`/`medium`).

---

## 2. Mutual-awareness scorecard

**No hard dependency: ✅ confirmed** — no runtime imports either way; `register` reads the catalog's live schemas from a clone at run time (loose coupling done right).

**Fabric → catalog: A−.** Deep and accurate: `README`, `AGENTS.md §6` (full register manual + failure-mode table), `llms.txt`, `GOVERNANCE.md`, and the `register` command are all catalog-aware; `AGENTS.md`'s claim that "current audits accept the fabric↔external pairing" is **verified true** (`audit.py:51 ALLOWED_GROUP_PAIRINGS = {'fabric': {'external'}}`). Gap is **freshness, not existence**: fabric is blind to everything the catalog added after the field-contract commit — `bundle_kind`, `min_os`, `io_contract`, `upstream_repo`, the sigstore bench lane, verification tiers (zero doc matches).

**Catalog → fabric: D (~40%, narrow).** Where it exists it's excellent (`CONTRIBUTING.md` + `AGENTS.md` full 5-step flow, `sources.yaml` watched source, issue-form dropdown, `getting-started.md` link — all locked by 2 doc tests). But fabric is **absent from every moment-of-need and every agent-bootstrap surface**: `README.md`, `llms.txt`, `llms-full.txt`, `agent.json`, `GOVERNANCE.md`, `openapi.yaml`, the **entire `site/`**, all **16 MCP tools**, every CLI not-found/zero-result message, the porting-candidates issue body, the model-request validation comments, `copilot-instructions.md`, `docs/data-model.md`. An agent entering via the advertised agent path (agent.json / llms.txt / MCP) **can never learn fabric exists**.

---

## 3. Integration verdict — deep conversation without dependency

**Currently: F — the lane cannot complete.** Proven by two independent live simulations (non-dry-run `register` against a scratch catalog copy):

- `register`'s own generated entry passes catalog **schema** validation and `validate.py`/`generate.py`, then **fails `audit.py` (exit 1)**: `build_model_entry` hardcodes `runtime.stock_runtime/custom_kernel/patch_required` to `"unknown"` (register.py:82-84) and `aot_required` defaults to `"unknown"` — the recipe schema has no fields to override them, and `audit.py` rejects `unknown`s. `_apply_and_open_pr` aborts before any PR. **Honest recipe values make it uncompletable by construction.**
- Even past audit, the entry **violates catalog test invariants**: no `bundle_kind`, no `min_os` (3 failing tests in `test_p1_iocontract.py`) — despite fabric literally documenting the macOS-27 floor.
- **Both CIs are green while the composition is red.** Fabric tests `register` against a **157-line-stale** vendored schema snapshot (false green, 54 tests, 0.13s); catalog CI runs only **2 of ~14 test modules** (`validate.yml:84,129`) — skipping every contract test, including the one that claims the fabric lane is completable (it tests a hand-copied entry, not fabric's generator output).
- **No cross-contract CI in either direction** — the "conversation" is never executed. This is the single missing structural piece.
- **`register` is not third-party-usable**: `_apply_and_open_pr` pushes to the catalog clone's `origin` and `gh pr create --repo kevinqz/coreai-catalog` — works only for a user with push access. No fork path. The explicit publisher persona can't complete it.
- **The fabric repo is private → HTTP 404 for the world**, while the public catalog routes contributors *and its own link-checker* at it.

---

## 4. Seamlessness scorecard (per loop)

| Loop | Grade | Evidence |
|---|---|---|
| Discover / consume (read) | **A** | agents + humans navigate cleanly |
| Contribute entry (P0 work) | **A−** | draft/submit/validate excellent, aggregated errors |
| Convert → publish → register | **F** | breaks at the final gate; green suites hide it |
| Human on the site | **F** | actively misrouted to coremltools + the zoo (`site/index.html:633`) |
| Model-request for a not-yet-converted model | **D** | dead-ends "artifact host missing" even with `source_group=fabric` — demands HF coords for an artifact that doesn't exist, zero routing to the tool that makes it |

---

## 5. SotA verdict — split vs merge

The two-repo split is **the right topology** (Ollama-over-HF, mlx-community precedent): conversion and indexing are genuinely different objects, and keeping fabric out of the catalog keeps the catalog a pure index. The steelman for merging (fabric as a catalog subcommand) fails because conversion needs the Apple toolchain + macOS 27 and would bloat the `pip install coreai-catalog` surface. **Keep them separate.** What's missing is not a merge — it's (a) a single executable contract instead of two drifting copies, and (b) a scheduled cross-contract test so the "deep conversation" is actually exercised.

---

## 6. Prioritized fixes

### P0 — the boundary is a lie until these land
1. **Make `register` emit a catalog-valid entry.** Fabric `build_model_entry` must author `bundle_kind` (from recipe/pipeline_tag), `min_os` (the macOS-27 floor fabric already documents), `upstream_repo` (from `recipe.upstream.hf_repo` — it has it), and must NOT emit audit-illegal `unknown` runtime fields (either add recipe fields or omit/derive them per what `audit.py` actually accepts). *[fabric: register.py, recipe.schema.json]*
2. **Catalog CI must run the full test suite.** `validate.yml` runs 2 of ~14 modules; run them all so `bundle_kind`/`min_os` invariants and the fabric-lane contract test are actually enforced. *[catalog: .github/workflows/validate.yml]*
3. **Cross-contract CI** (the "conversing without depending" mechanism): a scheduled fabric workflow that clones the catalog, runs `register` for a seed recipe, and asserts the output passes the catalog's live `validate + audit + full tests`. Turns silent drift into a red build. *[fabric: new workflow]*
4. **Fix the site + agent surfaces.** Replace the zoo/coremltools conversion aside on the site with the fabric story; add fabric to `README`, `llms.txt`, `llms-full.txt`, `agent.json`, `GOVERNANCE.md`, MCP not-found/zero-result hints, the porting-candidates issue body, and the model-request dead-end. Extend the fabric-awareness regression test from 2 surfaces to all of them. *[catalog: many]*
5. **Fabric visibility — maintainer decision.** Every catalog→fabric pointer is a dead link while the repo is private. Either make it public or gate the pointers behind a "coming soon" until it is.

### P1 — unify the drifting contracts
6. Single entry-generator: fabric imports nothing from the catalog, but its generator and the catalog's `contribute.build_model_entry` should be conformance-tested against the same golden fixtures so they can't diverge silently.
7. Reconcile license-triage vocab (fabric 3-value ↔ catalog 4-value) and route fabric models through the catalog's license-laundering guard.
8. `register` should replay all ~8 catalog CI gates locally (not 3) before claiming "PR arrives green"; add fork support; flip recipe status to `registered` on **merge**, not on PR open.
9. Refresh fabric's vendored schema snapshots (or fetch live in CI); reconcile the `huggingface.files` digest rules and the duplicate `sources.yaml` record; reconcile the `coreai-community` vs personal-namespace default with fabric's own "your OWN namespace" story.

---

## 7. Note on this audit's completeness

The verify and synthesis phases (adversarial re-check + human/consumer/lifecycle/SotA personas) were cut off by a spend limit. The findings above are from the map phase only and are **UNVERIFIED by a second adversarial pass** — but each is grounded in a cited live command execution, and the two headline P0s were independently reproduced by two separate auditors running real commands. Treat P0/P1 as high-confidence; the P2/P3 tail (duplicate digest writers, namespace defaults, status-on-open) as code-grounded but single-sourced.
