# Governance

This file states the catalog's merge rules as **checkable rules an agent can
evaluate** and a human countersigns. Every rule names its evidence command —
if a rule can't be evaluated mechanically, it doesn't belong here.

## Roles

- **Maintainer / merge authority:** `@kevinqz` (enforced by
  [`.github/CODEOWNERS`](./.github/CODEOWNERS) on all catalog data files).
- **Agents:** may draft, validate, and open PRs through any lane below.
  Agents never merge, **with one carved-out exception** — the benchmark
  auto-merge below. Everywhere else, a PR that passes every rule is
  *mergeable*, not merged: the maintainer countersigns.

### Exception: benchmark auto-merge

The benchmark lane is the single place where automation merges without a
human countersign. `.github/workflows/benchmark-validate.yml` squash-merges
a benchmark PR **only** when *all* of the following gates pass
(`scripts/physics_check.py` → `TIER_GATES`/`evaluate_tier`, outcome
`signed_plausible`):

1. `schema_valid` — the line validates against `schema/benchmark.schema.json`;
2. `model_id_exists` — the `model_id` is in `catalog.yaml`;
3. `signature_valid` — sigstore bundle (or legacy relay Ed25519) verifies;
4. `identity_matches_author` — the certificate's GitHub login equals the PR
   author (relay lane: the relay key is the trusted identity);
5. `physics_pass` — bandwidth-ceiling / consistency / thermal checks
   (trusted tier) pass;
6. `outlier_pass` — not a statistical outlier (physics fallback for small
   cohorts);
7. `not_duplicate` — no other same-cohort row observed in the last 7 days
   (the submitted line itself is excluded);

plus the lane preconditions: exactly one added line in `benchmarks.jsonl`
and no other file changes. Anything short of all seven gates routes to
human review (`benchmark-needs-review` / `benchmark-curator-review`). The
merged row's `verification_tier` stays `unverified` (n=1); promotion to
`community_verified` is curator-driven (see
`docs/benchmark-protocol.md`, "CI gate outcome vs. verification tier").
All other lanes — including the unsigned benchmark curator lane — require
the maintainer's countersign.

## Contribution lanes

| Lane | Entry point | Automation |
|---|---|---|
| **Conversion** (no artifact yet) | [`coreai-fabric`](https://github.com/kevinqz/coreai-fabric) `register` | recipe → convert → verify → publish to own HF → opens a fabric-lane PR to this catalog; a cross-contract CI job proves the entries stay catalog-valid |
| Model (repo clone) | `coreai-catalog contribute model` | draft → validate → PR via `gh` (for an artifact that already exists) |
| Model (no clone) | [model-request issue form](./.github/ISSUE_TEMPLATE/model-request.yml) | `model-request-to-pr.yml` validates, comments, opens a **draft PR** when clean |
| Benchmark | one added line in `benchmarks.jsonl`, nothing else | `benchmark-validate.yml` — **auto-merges** signed, identity-bound, physics-clean submissions (see the exception above); curator lane for unsigned `upstream_readme_*` entries |
| Discovery | weekly `discover.yml` | upserts the single pinned **Porting candidates** issue |
| Source monitor | 3-hourly `source-monitor.yml` | upserts the single pinned **Source Monitor** issue + machine-readable candidate stubs |

The **conversion lane is the upstream half of the model lanes**: use it when the
`.aimodel` artifact does not exist yet (fabric produces it, hosted on the
contributor's own Hugging Face). The model lanes assume an artifact already exists.
`source_group: fabric` marks entries that came through it. The zoo is an indexed
reference upstream, not a required path.

Lane rule: **model PRs never touch `benchmarks.jsonl`; benchmark PRs touch
nothing else.** Mixed PRs fail CI by design.

Single-pinned-issue policy: automation must **upsert** its one labeled issue
(`porting-candidates`, `source-monitor`) — never file duplicates.

## Merge rules (all must hold)

A PR is **mergeable = M1 ∧ M2 ∧ M3 ∧ M4 ∧ M5.** Each rule below is stated
with the check an agent runs and the pass condition it asserts.

### M1 — CI green

All required workflows pass on the head commit.

```bash
gh pr checks <PR> --json name,state   # every state == SUCCESS (or SKIPPED)
```

Locally reproducible: `python3 scripts/validate.py && python3 scripts/audit.py`
both exit 0, and `python3 scripts/generate.py && git diff --exit-code docs/ dist/`
shows no drift.

### M2 — Sources resolve

Every `source_path` and artifact URL added or changed by the PR resolves
with HTTP status 200 (redirects followed).

```bash
# for each new/changed URL U in the diff:
curl -s -o /dev/null -L -w '%{http_code}' "$U"   # must print 200
```

A 404/410 on any added URL blocks the merge; `unknown` availability must be
declared in the entry instead of pointing at a dead link.

### M3 — Officiality consistent

The model's `source_group` and its artifact's `officiality` block agree:

- `source_group: official` ⇔ `officiality.apple_export_recipe: true`
- `source_group: zoo` ⇒ `officiality.apple_export_recipe: false`
- `officiality.apple_hosted_artifact: true` requires evidence that **Apple**
  hosts the bytes (as of 2026-07 this is true for zero entries — treat any
  claim as suspect).

```bash
python3 scripts/audit.py   # officiality consistency is audit-enforced; exit 0
```

### M4 — License compatible

The model's declared `license.name` must be consistent with its upstream's
actual terms, and restrictive upstreams force triage:

- Derivatives of `review_required` upstream licenses (Gemma Terms, Meta SAM
  License, LFM Open License, OpenRAIL-style) must carry
  `commercial_use: check_license`, never `likely`.
- A permissive claim (`Apache-2.0` + `likely`) over a restrictive upstream is
  license laundering and blocks the merge.

```bash
# evidence: the upstream license record must exist and match
grep -A4 "id: <license-source-id>" upstreams.yaml
python3 scripts/deep_audit.py   # license join, where wired
```

When the upstream license cannot be verified, the entry states
`check_license` — reviewers reject "likely" claims without a cited source.

### M5 — Provenance linked

Every new entry links verifiable provenance the *submitter* can be tied to:

- the artifact has a `huggingface` and/or `github` block whose repo exists
  (M2 checks resolution) and whose owner is credited in `CREDITS.md` /
  `sources.yaml`;
- every id in the model's `sources` list resolves to a `sources.yaml` /
  `upstreams.yaml` record that **predates the PR or is independently
  verifiable** — a PR adding its own source record must point at a real,
  resolvable external host, not at itself;
- when known, `upstream_repo` names the ORIGINAL upstream (`org/name`) so
  discovery dedup and lineage checks work.

```bash
python3 scripts/validate.py   # cross-reference layer; exit 0
```

## Verdict format

Agents evaluating a PR report one line per rule:

```
M1 CI green:              PASS|FAIL (<evidence>)
M2 sources resolve:       PASS|FAIL (<url — status>)
M3 officiality:           PASS|FAIL
M4 license:               PASS|FAIL (<license — upstream terms>)
M5 provenance:            PASS|FAIL
mergeable:                yes|no
```

`mergeable: yes` is a recommendation. The maintainer merges — except in the
benchmark auto-merge lane (the sole exception defined under Roles above),
where `benchmark-validate.yml` merges mechanically once every gate passes.
