# Provenance Architecture v2 — Round 2 Red-Team: Buildability & Feasibility

> **Verdict:** v2 fixes the right structural problems (YAML→JSONL, Issue→PR intake). But it introduces **three subsystems that are not buildable or maintainable by one person**: a Cloudflare Worker doing Apple API crypto, an auto-merge pipeline with unsolved race conditions, and a migration whose own pseudocode produces schema-invalid output. Two of six attack vectors are real blockers; three are solvable with scope cuts; one reveals that the v1 and v2 schemas are incompatible in ways the design doesn't acknowledge.

---

## Attack Vector 1: Cloudflare Worker Complexity

### Severity: 🔴 BLOCKER (as designed) → 🟡 SOLVABLE (with scope cut)

**The design asks one CF Worker to do five jobs:**
1. Verify a DeviceCheck JWT against Apple's `api.developer.apple.com` API
2. Verify SHA256 against a model-hash registry
3. Coarsen device data
4. Implement random delay logic (1–24h)
5. Open a PR via the GitHub API

Each of these is a distinct failure domain. Together they form a server-side application with multiple external dependencies, none of which have corresponding test infrastructure in the repo.

**The Apple DeviceCheck credential problem is fatal as specified.**

DeviceCheck's `validate_token` endpoint requires a JWT signed with an ES256 private key from a paid Apple Developer account ($99/year). The design says "verified by the Worker, then stripped" but never addresses:

- **Where does the key live?** CF Workers support secrets (`wrangler secret put`), but the private key + Team ID + Key ID must be provisioned and rotated manually. This is not documented in the design.
- **Who owns the Apple Developer account?** If the maintainer leaves the project, the credential dies with their account. There's no organizational account structure proposed.
- **The JWT signing itself.** CF Workers run a V8 isolate — they have `crypto.subtle` (WebCrypto) for ECDSA P-256 signing, which *can* produce ES256 JWTs. But this is non-trivial code that must be correct on the first try (incorrect JWT → all submissions silently rejected). No test for this exists.
- **Apple API rate limits.** The design doesn't cite them. Apple's DeviceCheck API has undocumented but real rate limits. At "100 PRs/day" the Worker makes 100 Apple API calls/day — likely fine, but unverified. More critically, each call adds 200–500ms latency *before* the Worker can respond to the device, which must be accounted for in the app's timeout logic.

**The random delay (1–24h) is architecturally incoherent in a serverless function.**

CF Workers have a wall-clock execution limit (30s on free plan, up to 5min on paid). You cannot `setTimeout` for 24 hours. The design's Step 5 ("Random delay 1–24h to break temporal correlation") requires either:
- CF Queues + Durable Objects (additional infrastructure, more complexity)
- Storing the submission in KV/D1 with a scheduled Cron Trigger to flush it later (stateful, defeats "stores nothing" promise)
- Or dropping the delay feature entirely

**This is not a solvable-with-effort problem. It's a fundamental mismatch between the design's privacy requirement and the runtime model.** The delay either needs to be client-side (the app waits 1–24h before submitting — but then the app must be running) or must be dropped.

**The model-hash verification requires the Worker to fetch `dist/model-hashes.json` on every request.** That file doesn't exist yet (no `scripts/` generates it, no schema defines it). The Worker would need to cache it (CF Cache API or KV), introducing cache-invalidation bugs.

### Practical Recommendation

**Cut the Worker to a thin forwarder.** Do DeviceCheck verification and hash checking *in the GitHub Action* (which runs in a trusted environment and can hold secrets), not in the Worker. The Worker's only job becomes: coarsen device data + strip PII + forward to a GitHub Issue/Dispatch endpoint. This eliminates the Apple API integration, the JWT signing, the hash fetch, and the delay problem from the Worker entirely.

Alternatively, **drop DeviceCheck for v2 launch.** The design already has a `community_submission` extraction method with `confidence: low`. Launch with that as the only intake path. Add DeviceCheck in v3 when there's a second maintainer or organizational backing.

---

## Attack Vector 2: GitHub Bot Authentication

### Severity: 🟡 SOLVABLE

**PAT vs GitHub App analysis:**

| Factor | PAT (Fine-grained) | GitHub App |
|---|---|---|
| Setup complexity | Low (generate token, store as CF secret) | Medium (create app, generate key, implement JWT auth flow) |
| Scope control | Per-repo, per-permission | Per-repo, per-permission, per-installation |
| Expiration | Max 1 year (fine-grained) | Key doesn't expire; installation persists |
| Revocation | Delete token (instant) | Uninstall app (instant) |
| Rate limits | 5,000 req/hour (shared with user) | 5,000 req/hour *per installation* (better) |
| Audit trail | Actions attributed to bot user | Actions attributed to app (clearer provenance) |

**A fine-grained PAT scoped to a single repo with `contents: write` + `pull-requests: write` is sufficient and dramatically simpler.** The credential lives in CF Worker secrets (encrypted at rest, injected at runtime, never in source). If it leaks, the blast radius is: someone can open PRs in this one repo. Since all PRs go through the validation Action, a malicious PR would be caught by schema validation and outlier checks.

**The real risk is not the credential — it's the `secrets.GITHUB_TOKEN` in `benchmark-validate.yml` line 88.** That token is automatically scoped to the repo and is the correct approach for auto-merge. But `automerge-action@v0.16.2` (a third-party Action) runs with that token. Supply-chain compromise of that Action = write access to main. This is a real concern that the design doesn't address.

### Practical Recommendation

- Use a **fine-grained PAT** for the CF Worker (stored as CF secret), scoped to `coreai-catalog` repo only, `contents:write` + `pull-requests:write`, 1-year expiry with calendar reminder.
- Pin `automerge-action` to a commit SHA, not a version tag. Better: replace it with `gh pr merge` in a script step — eliminates the third-party dependency entirely.
- Document the PAT rotation procedure in the repo's `CONTRIBUTING.md` or `RUNBOOK.md`.

---

## Attack Vector 3: Auto-Merge Race Conditions

### Severity: 🔴 BLOCKER at scale → 🟡 SOLVABLE with retry logic

**The race condition is real and the design's mitigation is insufficient.**

The design says "each PR is independent, squash-merged" — but they're NOT independent. They all append to the same `benchmarks/benchmarks.jsonl` file. When PR #1 squash-merges, the file on `main` changes. PR #2 (opened against the old `main`) now has a merge conflict on `benchmarks.jsonl`.

**Current auto-merge (line 82–90 of `benchmark-validate.yml`):**
```yaml
uses: pascalgn/automerge-action@v0.16.2
env:
  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

This action does NOT rebase or retry on conflict. If the merge fails, the PR stays open with no automatic resolution. The `pascalgn/automerge-action` README confirms: it tries once and gives up.

**At the design's projected scale (100 PRs/day), this is a continuous failure source.** Even at 10 PRs/day, two PRs opened within the same Action execution window (~2–3 min) will conflict.

**The "append-only = zero merge conflicts" claim (line 143) is technically false.** JSONL is append-only at the *data model* level, but git operates at the *file* level. Two branches that both append a line to the same file produce a text conflict that git cannot auto-resolve, because git doesn't understand JSONL semantics.

### Practical Recommendation

**Replace auto-merge with a queue-based approach:**

1. **GitHub Dispatch + single-merger Action.** Instead of each PR auto-merging independently, use a single GitHub Action triggered on a schedule (every 2 min) that:
   - Finds all PRs labeled `auto-ok`
   - Rebases each one against `main` (one at a time, sequentially)
   - Merges sequentially
   - Since each merge updates `main`, the next rebase picks up the new line

2. **Or: don't use PRs at all for auto-approved submissions.** If the Worker has a PAT with `contents:write`, it can commit directly to a `benchmarks/pending/` directory (one file per submission), and a scheduled Action batches them into `benchmarks.jsonl` atomically. This eliminates the race entirely — there's one writer, not N concurrent writers.

Option 2 is simpler and more robust. The "PR for every submission" pattern is optimization for *human review transparency*, but the design says 90% are auto-merged with no review. For those 90%, a direct commit + batch squash is strictly better.

---

## Attack Vector 4: JSONL Validation in Practice

### Severity: 🟡 SOLVABLE (but current implementation has bugs)

**The diff-extraction approach in the workflow (lines 31–42) is fragile but functional:**
```bash
git diff origin/main HEAD -- benchmarks/benchmarks.jsonl \
  | grep '^+' \
  | grep -v '^+++' \
  > /tmp/work/new_lines.jsonl
```

This works for the happy path (one line added). But:

**Attack: 100 lines in one PR.** The current workflow doesn't check line count. An attacker (or the bot itself, if buggy) could submit 100 lines. The schema validation would pass each line individually. The outlier check would run on all 100. They'd all merge. The design's auto-merge criteria (line 188–197) says "1-line JSONL addition" but **this constraint is not enforced anywhere in the code.**

**Fix:** Add after extraction:
```bash
if [ "$LINE_COUNT" -gt 1 ]; then
  echo "ERROR: Expected 1 new line, got $LINE_COUNT"
  exit 1
fi
```

**The `validate_benchmark.py` script doesn't actually use JSON Schema validation.** It reimplements field checks manually (lines 20–78), checking `required` fields and `enum` values by hand. This means:
- `additionalProperties: false` is NOT enforced (the script doesn't reject unknown fields)
- Nested object validation (`environment`, `provenance`) is incomplete — only `extraction_method` is checked
- Any schema change requires corresponding code changes in two places

**Fix:** Use the `jsonschema` library (already in `pip install` on line 28 of the workflow):
```python
from jsonschema import validate
validate(instance=entry, schema=schema)
```

**The git diff parsing breaks if the PR modifies existing lines** (e.g., reformats JSONL). A `+` line that's part of a modification, not an addition, would be picked up. Unlikely for bot-generated PRs, but possible for manual PRs.

### Practical Recommendation

- Add line-count enforcement (reject PRs with >1 new line for bot submissions).
- Replace `validate_benchmark.py`'s manual checks with actual `jsonschema.validate()`.
- Use `git diff --diff-filter=A` (added lines only) instead of `grep '^+'` to exclude modifications.
- The schema and the validation code are currently in the repo but **out of sync with each other** — the schema has `additionalProperties` at the top level (line 6 of v1 schema has no such key; the v2 design's schema has it at line 373), while `validate_benchmark.py` doesn't check for it at all.

---

## Attack Vector 5: Migration Soundness

### Severity: 🔴 BLOCKER — the migration script as written produces invalid data

**The migration pseudocode (lines 542–567) is broken in three concrete ways:**

### 5a. The `environment` field parsing produces garbage

```python
b['os_major'] = b.get('environment', '').split(',')[0].replace('iOS ', '').replace('macOS ', '').strip()
```

Current `environment` values in the data (20 distinct strings):
```
"iOS 27 beta, coreai-pipelined engine"
"iOS 27 beta, Release, AOT h18p encoder"
"iOS 27 beta, pipelined engine, AOT h18p, provider mode"
"macOS 27 beta, Core AI, draft model step"
"stock CoreAI runtime, M4 Max"
```

After the migration's `split(',')[0].replace(...)`:
- `"iOS 27 beta, coreai-pipelined engine"` → `os_major: "27 beta"` ← **invalid** (schema wants `"27"`)
- `"stock CoreAI runtime, M4 Max"` → `os_major: ""` ← **invalid** (empty string, fails `minLength: 1`)

The v2 schema requires `os_major` to match no pattern but have `minLength: 1`. The migration produces `"27 beta"` (has "beta" suffix) or empty strings. **This fails the v2 schema.**

### 5b. The `device` → `device_class` mapping is lossy but acceptable

Current devices: `"iPhone 17 Pro"` and `"M4 Max"` — only 2 distinct values.

The migration does `b['device_class'] = b.pop('device', 'unknown')`, which produces `device_class: "iPhone 17 Pro"` and `device_class: "M4 Max"`.

The v2 schema's `device_class` field has no enum — just `minLength: 1`. So `"iPhone 17 Pro"` is technically valid. But the design's relay transformation table (line 48) says the relay maps `iPhone17,1` → `"A18 Pro"`. The migrated data says `"iPhone 17 Pro"`. **These are different coarsening schemes.** Historical data and new crowdsourced data will use different device_class values for the same hardware, making cohort comparison impossible.

### 5c. The v1 schema and v2 schema are structurally incompatible

**Critical incompatibility: `observed` vs `observed_date`.**

- v1 schema (current, line 11–12): required field is `observed`
- v2 schema (design, line 378): required field is `observed_date`
- The migration renames `observed` → `observed_date` (line 564)

But the v1 schema also has `additionalProperties` absent (it's not set, meaning additional properties are allowed by default). The v2 design schema has `"additionalProperties": false` (line 373). This means:

**The migrated data will fail v2 validation because it carries v1 fields that aren't in the v2 schema.** Specifically:
- `model_hash` — v1 allows it (line 160–163), v2 drops it entirely (not in properties list)
- `superseded_by` — v1 allows it (line 87), v2 doesn't list it
- `methodology` block (v1, lines 90–108) — v2 replaces with `environment` block (different structure)
- `device_info` block (v1, lines 110–126) — v2 replaces with flat `device_class` field
- `runtime_config` block (v1, lines 128–140) — v2 doesn't include it

The migration script doesn't strip these fields. `jsonschema.validate()` with `additionalProperties: false` will reject every migrated line.

**The outlier_check.py script (already in the repo) has a dual-path compatibility hack** (lines 44, 98) that checks both `device_info.device_class` and `device`, and both `runtime_config.engine` and environment-string parsing. This confirms the codebase already knows about the format split — but it papers over it rather than resolving it.

### Practical Recommendation

The migration needs a complete rewrite, not the 25-line pseudocode in the design. Specifically:

1. **Write a real migration script** that:
   - Strips v1-only fields (`model_hash`, `superseded_by`, `methodology.*`, `device_info.*`, `runtime_config.*`)
   - Maps `methodology` → `environment` (field-by-field)
   - Maps `device_info` → flat `device_class` with a normalization table (`"iPhone 17 Pro"` → `"A18 Pro"`)
   - Parses `environment` strings into `os_major` using regex, not naive `split(',')[0]`
   - Generates `id` for entries that lack one (current data has IDs, but verify)

2. **Decide on schema compatibility.** Either:
   - Make the v2 schema permissive (`additionalProperties: true` or omitted) and validate only the fields you care about, OR
   - Write a proper migration that produces only v2-valid fields

3. **The migration must be tested.** Run it, validate every line against the v2 schema, fix until 0 errors. This is a 2-hour task, not a design afterthought.

---

## Attack Vector 6: Operational Reality for One Person

### Severity: 🔴 The design is not maintainable by one person as specified

**Component inventory and maintenance burden:**

| Component | Build effort | Weekly maintenance | Failure mode if abandoned |
|---|---|---|---|
| CF Worker (DeviceCheck + relay) | 2–3 weeks | 1–2h (monitoring, Apple API changes) | All submissions silently fail; no new benchmarks |
| GitHub Bot (PAT management) | 2 days | 5 min/month (PAT rotation) | Bot stops opening PRs; submissions queue indefinitely |
| GitHub Actions (validate + auto-merge) | 3–5 days | 1h (workflow debugging) | PRs pile up unvalidated; or auto-merge breaks |
| JSON Schema (v2) | 1 day | 30 min/month (schema evolution) | Validation drift; bad data sneaks in |
| catalog.yaml + other YAML | Ongoing | 2–4h (model additions, upstream sync) | Catalog goes stale; existing data still works |
| CLI + MCP server | Ongoing | 1–2h (bug fixes, feature requests) | Users can't query the catalog |
| Web UI | 1–2 weeks | 1–2h (if it exists; not in repo) | Static site goes stale |
| Privacy policy + GDPR compliance | 1 week (legal review) | 30 min/month (policy updates) | Legal liability; no erasure capability |
| Apple Developer cert rotation | N/A (annual) | 1h/year + $99 | DeviceCheck stops working |

**Realistic weekly burden: 8–15 hours/week** — essentially a part-time job — and that assumes nothing breaks.

**What breaks first if the maintainer is unavailable for 2 weeks:**

1. **Benchmark submission queue.** If auto-merge breaks (race condition from Vector 3), PRs pile up. After 2 weeks at even 10/day, that's 140 unreviewed PRs. The outlier-check cohort data is now stale (new benchmarks aren't in `benchmarks.jsonl`), so MAD calculations are increasingly wrong.

2. **Apple Developer cert / DeviceCheck.** If the cert expires or Apple changes the API, ALL submissions fail silently. The CF Worker returns errors but there's no alerting infrastructure. The maintainer comes back to 2 weeks of failed submissions and angry users.

3. **PAT expiration.** Fine-grained PATs max out at 1 year. If it expires while the maintainer is away, the bot can't open PRs. Same silent-failure mode.

4. **Upstream drift.** New models get released. The weekly sync report (validate.yml line 116–166) creates issues, but nobody processes them. The catalog becomes increasingly incomplete.

### Practical Recommendation

**The design needs an explicit "bus factor" section.** Specifically:

1. **Add health monitoring.** A simple Action that pings the CF Worker daily and opens an issue if it's down. Without this, failures are silent.

2. **Make the CF Worker optional, not load-bearing.** If the Worker is down, the app should fall back to `community_submission` mode (lower confidence, no DeviceCheck). The current design has no fallback path.

3. **Cut scope ruthlessly for v2 launch.** Ship in this order:
   - **Phase 1 (1 week):** JSONL migration + schema + validation Action. No Worker, no bot, no DeviceCheck. Manual PR intake. This alone resolves C7, H7, H8, H10.
   - **Phase 2 (2 weeks):** Bot PR intake from a simple form/endpoint (no DeviceCheck, no relay). Submissions tagged `community_submission`. This resolves C8, C9.
   - **Phase 3 (3+ weeks):** CF Worker relay with DeviceCheck. Only if Phase 2 proves the intake pipeline works.

4. **Document a "if I get hit by a bus" runbook.** PAT location, Apple Developer account credentials transfer, CF Worker ownership, domain/DNS. Without this, the project dies with the maintainer.

---

## Cross-Cutting Finding: The Design Document vs The Codebase Are Out of Sync

The v2 design describes infrastructure that partially exists and partially doesn't:

| Design element | Exists in repo? | Status |
|---|---|---|
| `benchmarks/benchmarks.jsonl` | ❌ No | Doesn't exist; data still in `benchmarks.yaml` |
| `benchmark-validate.yml` workflow | ✅ Yes | Exists but references non-existent paths (`benchmarks/benchmarks.jsonl`) |
| `scripts/validate_benchmark.py` | ✅ Yes | Exists but doesn't use `jsonschema` library; manual checks only |
| `scripts/outlier_check.py` | ✅ Yes | Exists, works, but has dual-format compatibility hacks |
| `dist/model-hashes.json` | ❌ No | Referenced by design but not generated anywhere |
| `scripts/migrate_benchmarks.py` | ❌ No | Only pseudocode in the design doc |
| CF Worker code | ❌ No | Only TypeScript snippets in the design doc |
| v2 schema (`additionalProperties: false`) | ❌ No | Current schema is v1; doesn't match v2 design |

**The workflow file (`benchmark-validate.yml`) is already committed but will fail on every run** because it references `benchmarks/benchmarks.jsonl` which doesn't exist, and `benchmarks/pending/**` which doesn't exist. This suggests the v2 work was started (workflow written) but the data migration was never done.

---

## Summary Scorecard

| Attack Vector | Severity | Verdict |
|---|---|---|
| 1. CF Worker complexity | 🔴 BLOCKER | DeviceCheck JWT signing + 24h delay in serverless = not buildable as designed. Cut to thin forwarder or defer. |
| 2. GitHub Bot auth | 🟡 SOLVABLE | Fine-grained PAT is fine. Pin automerge-action to SHA or replace with `gh pr merge`. |
| 3. Auto-merge race conditions | 🔴 BLOCKER at scale | Append-only ≠ conflict-free in git. Need single-writer queue or scheduled batch merge. |
| 4. JSONL validation | 🟡 SOLVABLE | Current script is incomplete; add line-count limit + use real jsonschema. 2-day fix. |
| 5. Migration soundness | 🔴 BLOCKER | Pseudocode produces schema-invalid output. `os_major` parsing broken. v1↔v2 field incompatibility unresolved. |
| 6. One-person operations | 🔴 Not feasible as designed | 8–15h/week burden. No fallback, no alerting, no bus-factor plan. Needs phased delivery. |

**Bottom line:** The architecture is directionally correct — JSONL, PR-based intake, and privacy relay are the right patterns. But the design treats "Cloudflare Worker with Apple crypto" and "auto-merge at scale" as implementation details when they're actually the hardest parts of the system. Ship Phase 1 (JSONL + manual PRs) now. Earn the right to build Phase 3 (Worker + DeviceCheck) by proving the pipeline works without them first.
