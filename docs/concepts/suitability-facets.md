# Model suitability facets

This is the canonical reference for how the catalog answers *"which model should I
pick?"*. It replaces the single `readiness_score` composite (now deprecated as a
headline) with three **orthogonal, honestly-named axes**, and keeps model quality
where it belongs: in benchmark **values**.

> **TL;DR for agents:** do **not** rank or gate on `readiness_score`. It is a
> curation/deployability composite that is *blind to model quality* and inversely
> tracks capability. Filter and sort on the decomposed **`deployability`** facets,
> read **`lifecycle`** for entry maturity, read **`entry_completeness`** for
> coverage, and judge quality from **benchmark values** per `<task, metric>`.
> All three facets are emitted per-entry in `dist/search-index.json`.

---

## 1. The three axes

| Axis | Answers | Shape | Emitted in |
|---|---|---|---|
| **`deployability`** | *Can I obtain / run / license it here?* | per-facet, **no score** | `dist/search-index.json` (per entry) |
| **`lifecycle`** | *How mature/trusted is the catalog ENTRY?* | ordinal `stage` | `dist/search-index.json`, `dist/leaderboard.json` |
| **`entry_completeness`** | *How complete is the ENTRY's metadata?* | coverage % (not quality) | `dist/search-index.json`, `dist/leaderboard.json` |
| *(quality)* **`benchmarks`** | *Is it actually good at task X?* | measured **values** per `<task,metric>` | `benchmarks.jsonl` → `dist/benchmarks.json`, per-entry `benchmarks[]` in `search-index.json` |

The catalog deliberately does **not** collapse these into one displayed number —
they don't share a unit, and collapsing them imposes a false total order on a
genuine partial order (see §5).

---

## 2. Field reference

All three are derived at export time by `coreai_catalog/catalog.py`
(`deployability_facets()`, `lifecycle_of()`, `entry_completeness()`) and declared
as optional objects in `schema/model.schema.json`. They may also be **authored**
on a source entry in `catalog.yaml` (e.g. an explicit `lifecycle`); an authored
value takes precedence over the derivation.

### 2.1 `deployability`

```jsonc
"deployability": {
  "obtainable": "available",          // available | unavailable | unknown  (from artifact.availability)
  "runtime": "patched",               // stock | patched | unknown
  "device_fit": { "mac": true, "iphone": true, "ipad": "unknown" },
  "license": { "name": "Apache-2.0", "commercial_use": "likely" },
  "measured": true                    // ≥1 benchmark VALUE exists (presence, NOT a quality claim)
}
```

- **`runtime`** collapses the four **collinear** source flags
  (`stock_runtime`, `custom_kernel`, `patch_required`, `aot_required`) into one
  axis: `stock` when `stock_runtime is True`, `patched` when `False`, else
  `unknown`. (In the old score those four flags handed out ~25 points for a single
  underlying property — see §5.)
- **`device_fit`** mirrors `device_support` (`mac`/`iphone`/`ipad`), preserving
  `"unknown"` verbatim — an unknown device fit is *not* a `false`.
- **`measured`** is benchmark **presence**, not score. A model with terrible
  measured accuracy is still `measured: true`.

### 2.2 `lifecycle`

```jsonc
"lifecycle": {
  "stage": "verified",                // ordinal, see below
  "verification": "confirmed",        // confirmed | needs_review | deprecated | unknown  (= status)
  "curator_confidence": "high",       // high | medium | low | needs_review  (= confidence)
  "last_verified": "2026-06-24"
}
```

**`stage`** is an ordinal maturity ladder for the *entry* (MLTRL / MLflow-tags
style), derived by `lifecycle_of()` in this order (first match wins):

| Stage | Rule |
|---|---|
| `deprecated` | `status == "deprecated"` |
| `official` | `source_group == "official"` **and** `status == "confirmed"` (Apple-hosted, verified) |
| `community` | `source_group == "fabric"` **or** `status == "needs_review"` (community-converted or not-yet-verified provenance) |
| `verified` | `status == "confirmed"` **and** `maturity ∈ {stable, active}` |
| `experimental` | otherwise (e.g. confirmed but `maturity == experimental/research`) |

Note the deliberate split: **experimental *maturity* ≠ community *provenance*.** A
confirmed zoo model with cutting-edge (`experimental`) maturity is `experimental`,
not `community`. `community` is reserved for community/fabric provenance or
unverified entries. An authored `lifecycle.stage` on the entry overrides this.

### 2.3 `entry_completeness`

```jsonc
"entry_completeness": {
  "pct": 0.833,                       // present / of  (0..1)
  "present": 5,
  "of": 6,
  "fields": {
    "artifact_availability_known": true,
    "device_support_known": true,
    "runtime_profile_known": true,
    "license_triaged": true,
    "benchmarked": true,
    "io_contract_present": false
  }
}
```

This measures **coverage of the catalog entry's metadata** (Kaggle-Usability
style), *not* model quality. Key property: an **`unknown`/absent facet lowers
coverage, never a hidden quality score**. This is what un-does the old score's
structural bias — a fabric-converted model with `device_support: unknown` reports
lower *coverage* (which is true: its entry is less complete) without being
penalized as lower *quality*.

### 2.4 Quality lives in benchmark values

Model quality is **not** a facet. It is the set of measured benchmark **values**
in `benchmarks.jsonl` (schema: `schema/benchmark.schema.json`), keyed by
`model_id`, with `metric`/`value`/`unit`/`device_class`/`os_major`/`confidence`.
Per-entry, `search-index.json` attaches the model's `benchmarks[]` array; the
catalog-wide view is `dist/benchmarks.json` / `dist/benchmarks-aggregate.json`.
"Best model for task X" is a **per-task leaderboard over benchmark values**, never
the `readiness_score` composite.

---

## 3. `readiness_score` — deprecated as a headline

`readiness_score` (`catalog.py:readiness_score()`, weights in
`SCORING_WEIGHTS`) is a 0–100 sum of 13 hand-weighted yes/no checks, surfaced with
an A–F grade in the CLI. **It is retained** for internal ranking
(`search`/`recommend_models`/`task_pages`/`transform_graph`) and back-compat
(still emitted on `search-index.json`, `leaderboard.json`, `readiness-scores.json`,
and declared in `openapi.yaml`), but it is **deprecated as a headline / quality
signal**. Do not lead with it.

Why it was demoted (from the SotA red-team, `docs/superpowers/specs/*redteam*`):

1. **Wrong construct.** Model accuracy never enters — only benchmark *presence*
   (`has_benchmark: +10`), never the value. In the live catalog the score
   *inversely* tracks capability: tiny perception models (depth-anything, rf-detr,
   yolox-s) hit 93/A because they fit an iPhone and run stock; capable large LLMs
   sink to 45–53/D–F with the same curation flags.
2. **~25-point double-count.** `stock_runtime`(+10), `no_custom_kernel`(+5),
   `no_patch_required`(+5), `no_aot_required`(+5) are near-perfectly collinear —
   one underlying fact ("runs on the vanilla runner") paid four times.
3. **False precision.** Presented as continuous 0–100 but actually ~16 discrete
   integer sums; a "78" vs "73" is one boolean flip, not a finer measurement.
4. **Structural bias.** Strict `is True` checks mean `device_support: "unknown"`
   silently scores 0, capping fabric-converted / under-curated entries regardless
   of true quality; `confidence: low` charges the curator's uncertainty about the
   *entry* against the *model*.
5. **No derivation/validation.** The weights are hand-assigned round numbers with
   no stated calibration.

The 13-factor formula remains documented in `AGENTS.md` and `llms-full.txt` for
the internal-ranking use only.

---

## 4. How to use the facets

### Agents / MCP / recommendation
- **Filter (hard gate)** on `deployability`: `obtainable == "available"`, and the
  target device in `device_fit` not explicitly `false`. Keep `"unknown"` (don't
  penalize under-curated entries).
- **Sort** survivors by a **user-relevant** axis — size (`size.artifact_size` /
  `size.parameters`), latency (a benchmark value), or `lifecycle.stage` — never by
  the composite.
- **Quality** questions → compare **benchmark values** for the task; if none
  exist (`measured: false`), say so.
- **Trust/maturity** → `lifecycle.stage`; **entry gaps** → `entry_completeness`.

### Reference consumer
`ComfyUI-CoreAI`'s model-picker (`comfyui_coreai/catalog.py:model_dropdown`) is the
canonical example: it hard-gates on obtainable + mac-fit (keeping `unknown`) and
sorts smallest-first — it does **not** read `readiness_score`.

---

## 5. Why this is state-of-the-art

No first-party model hub collapses model quality+readiness into one displayed
scalar; the field surfaces pickability through orthogonal facets and lets the
consumer collapse:

- **Popularity/usage facets** — Hugging Face downloads / likes / trending
  (<https://huggingface.co/docs/hub/models-download-stats>), Ollama pulls/tags
  (<https://ollama.com/library>), Replicate `run_count` + hardware.
- **Benchmark facets** — per-`<task,dataset,metric>` eval rows (HF `model-index`,
  Papers with Code leaderboards, Open LLM Leaderboard's task-scoped average).
- **Lifecycle stages** — MLflow **deprecated** its fixed `None/Staging/Production/
  Archived` ladder in favour of free-form tags + aliases; MLTRL (Nature
  Communications, 2022) defines a 9-level ordinal maturity scale.
- **Curation/usability scalars, honestly scoped** — Kaggle's 0–10 Usability Rating
  rates documentation/completeness, **explicitly not accuracy**; Endor Labs keeps
  four *orthogonal* category scores (Security/Popularity/Quality/Activity) rather
  than one blend.

Our mapping: `entry_completeness` ≈ Kaggle Usability; `lifecycle` ≈ MLflow-tags /
MLTRL; `deployability` ≈ decomposed Endor-style facets; quality = benchmark values
≈ leaderboards. A single composite was *behind* SotA; the decomposition is *at* it.

---

## 6. Implementation & rollout

**Done** (commit `fa3b505`, PR #10):
- `schema/model.schema.json` — `deployability`/`lifecycle`/`entry_completeness`
  (optional).
- `coreai_catalog/catalog.py` — the three derivation functions;
  `readiness_score()` kept + deprecated docstring.
- `coreai_catalog/exports.py` — facets attached per-entry to `search-index.json`
  and `leaderboard.json`.
- `coreai_catalog/cli.py` — `scores` prints a deprecation banner.
- `tests/test_suitability_facets.py` — unit coverage; `scripts/validate.py` +
  `scripts/audit.py` clean; full suite green.
- `dist/catalog.json` (the pure YAML mirror) is **unchanged** — facets live in the
  enriched `search-index.json`, not the mirror.

**Not needed:** `coreai-fabric` — the derivation already maps
`source_group == "fabric"` → `lifecycle: community`, and `device_support: unknown`
now lowers coverage honestly instead of capping a quality score.

**Open follow-ups (not in this PR):**
- Migrate internal ranking (`search`/`recommend_models`/`task_pages`/
  `transform_graph`/`cli list`) off the composite onto the facets — a behavioural
  change deserving its own PR.
- `api.py` / `mcp_server/server.py` do not yet attach the facets the way
  `exports.py` does — a parity opportunity.
- The public site (`site/index.html`, `site/app.js`) still headlines
  `readiness_score` (sort dropdown, leaderboard, score-explainer) — a product/UI
  change, tracked separately from this documentation.
