# Multi-host provenance

How the catalog handles the case where **one upstream model has several
independent Core AI conversions**, each published by a different converter. As
the ecosystem grows this becomes the norm, not the exception — exactly as one
Hugging Face base model accumulates dozens of community quantizations.

## The problem, concretely

`microsoft/VibeVoice-1.5B` already has two independent `.aimodel` conversions:

| Host | Precision | Size | Integrity | Notes |
|---|---|---|---|---|
| `gafiatulin/vibevoice-1.5b-coreai` | int8 | ~5.36 GB | revision + per-file sha256 | indexed; MIT; `base_model` declared |
| `bryanbblewis11/VibeVoice-1.5B-CoreAI` | fp16 | ~13.9 GB | (not yet indexed) | newer; no license/base_model declared |

Same model, **different bytes** (different quantization → different size, sha256).
The schema was one-artifact-per-model (`artifact_ref` → one `artifacts.yaml`
entry), so only one host could be recorded.

## Two kinds of "other host" — do not conflate them

| Concept | Meaning | Schema | Bytes |
|---|---|---|---|
| **`artifact.mirrors`** *(already in schema)* | byte-identical failover copies of the **same** conversion (CDN/mirror) | `artifacts.yaml` → `mirrors[]` (owner/repo/url/revision, **no own sha256** — verified by the primary's) | **same** |
| **`model.alternate_artifacts`** *(new)* | **independent** re-conversions of the same upstream (different quantization/bytes, **own** sha256) | `catalog.yaml` model → `alternate_artifacts[]` of full artifact ids | **different** |

VibeVoice is the second kind. `mirrors` cannot represent it (different bytes need
their own sha256/size).

## The design: two layers

The single most important decision — and it mirrors the [suitability-facets
reshape](suitability-facets.md): **separate the stable, verifiable, authoritative
layer from the volatile popularity layer.**

### 1. Authoritative layer — source-grounded, deterministic (what you trust)
Lives in `catalog.yaml` + `artifacts.yaml`, built offline & deterministically:
- **Integrity:** each artifact pins a git `revision` + per-file `sha256` + `size_bytes`. This is the content-addressed "exactly which bytes, verifiably" primitive — the same one `.aimodel` install verification already uses.
- **Verification:** parity status against the upstream (from coreai-fabric, when available).
- **Officiality / trust:** `apple_hosted_artifact` vs `community_packaged`; the source's `trust` tier.
- **On-device fit:** precision/quantization + total size — for an Apple on-device catalog, smaller/int8 is usually preferable.

### 2. Volatile layer — refreshable snapshot (a tiebreaker, never truth)
Lives in `dist/signals.json` (produced by `scripts/refresh_signals.py`, **not** by
the deterministic `scripts/generate.py`):
- Per-artifact Hugging Face **`downloads`, `likes`, `last_modified`, `gated`**, keyed by artifact id, stamped with `as_of`.
- These are volatile and **gameable** (downloads can be botted, likes manipulated), so they never enter the authoritative catalog and never break its offline determinism. They are refreshed on a schedule and used only to break ties.

## Host-selection policy

`coreai_catalog.catalog.select_primary_artifact(model, artifacts_by_id, signals)`
picks the default host by a **transparent, deterministic** key
(`artifact_host_key`, lower = better) — not a single opaque score, consistent
with the suitability-facets philosophy:

1. **Integrity** — has pinned `revision` + per-file `sha256` (a verifiable download).
2. **Verification** — parity-verified against upstream.
3. **Officiality** — Apple-hosted > community.
4. **On-device fit** — smaller total size wins.
5. **Popularity** *(from `signals.json`)* — higher downloads, **tiebreaker only**.
6. Artifact id — stable final tiebreak.

Applied to VibeVoice: `gafiatulin` (integrity-pinned, int8, ~5.4 GB) is the
primary over `bryanbblewis11` (~13.9 GB fp16) — integrity and on-device fit
decide it, and no download count could override integrity. Unit tests:
`tests/test_multi_host.py`.

## Answers to the questions this raised

- **Can we always add a host?** Yes — a new converter's `.aimodel` becomes an
  entry in `alternate_artifacts[]` under the *existing* model. No duplicate model
  entry, no dedup pain.
- **Do we need HF dates / likes / downloads?** Yes, but only in the *volatile*
  layer (`signals.json`, `as_of`-stamped) and only as a **tiebreaker**. Never
  baked into the authoritative entry.
- **Do we need git?** Yes — the git `revision` + `sha256` **is** the
  authoritative layer: it is what you trust and verify. Already captured per
  artifact.

## State of the art

No first-party hub collapses "which host is best" into one opaque score. They
separate **provenance/integrity** (stable) from **popularity** (volatile):
Hugging Face shows downloads/likes/trending as live counters distinct from a
model's identity; MLflow moved from fixed stages to tags + aliases
(`@champion`/`@challenger`); Endor Labs keeps four orthogonal category scores.
This design follows suit — stable, verifiable provenance decides; volatile
popularity only breaks ties.

## Migration (incremental, back-compatible)

1. `artifact_ref` stays the primary → zero breakage. **(done: schema `alternate_artifacts` added, optional)**
2. `select_primary_artifact()` + `artifact_host_key()` policy. **(done, unit-tested)**
3. `scripts/refresh_signals.py` → `dist/signals.json`, off the deterministic build. **(done)**
4. Populate `alternate_artifacts` for real multi-host models (e.g. add
   `bryanbblewis11` as an alternate for `vibevoice-1-5b`) — a data change, curator lane.
5. Surface it: extend the `deployability` facet with a `hosts` count / primary
   host, and show alternates in the CLI / MCP `get_model`.
