# Provenance Architecture v2 — Second-Round Gaming/Integrity Red-Team

> **Date:** 2026-07-02
> **Scope:** Attack the NEW defenses (DeviceCheck JWT, relay verification, auto-merge gates)
> **Method:** Code-level analysis of actual implementation files + PoC execution
> **Verdict:** v2 closes the v1 "no verification" hole in DESIGN, but the IMPLEMENTATION has critical gaps that make most defenses non-functional. 4 CRITICAL, 2 HIGH, 1 MEDIUM findings.

---

## Summary Matrix

| # | Vector | Severity | v2 Fixes It? | Implementation Gap |
|---|--------|----------|-------------|-------------------|
| 1 | Relay Bypass (direct PR) | **CRITICAL** | Design: yes. Impl: **NO** | Action trusts boolean, doesn't verify JWT |
| 2 | Anchor Cohort Poisoning | **HIGH** | Partially | Stale anchors, single-curator trust |
| 3 | Auto-Merge Exploitation | **CRITICAL** | **NO** | 5 of 8 gates not implemented; auto-merge is broken |
| 4 | JSONL Injection | **HIGH** | Partially | No line-count limit, no newline sanitization |
| 5 | Concurrent Benchmark Race | **MEDIUM** | Design: yes. Impl: **NO** | No auto-rebase, conflicts stall PRs |
| 6 | Community Submission Flood | **CRITICAL** | **NO** | Aggregation includes ALL entries, no confidence filtering |
| 7 | Outlier Check Stdout Bug | **CRITICAL** (new) | N/A | Multi-line output breaks auto-merge gate entirely |

---

## Finding 1: RELAY BYPASS — CRITICAL

### The Attack
The GitHub repo is public. The JSONL schema is documented. The PR workflow is public. An attacker opens a PR directly to `benchmarks/benchmarks.jsonl` with a line containing `device_verified: true` (or in the actual schema, `provenance.device_attestation: true`).

### What the Code Actually Does
The GitHub Action (`benchmark-validate.yml`) runs three checks:
1. Schema validation (`validate_benchmark.py`) — checks field types/enums
2. Cross-reference (`model_id` exists in catalog)
3. Outlier detection (MAD)

**NONE of these verify the DeviceCheck JWT.** The Action trusts the boolean field in the JSON. The design doc itself acknowledges this (line 174): *"DeviceCheck verified? (checked by relay, not here)"* — but this is the entire vulnerability. Anyone can write `true`.

### PoC Verification
```
Fabricated entry with device_attestation:true, no JWT
→ validate_benchmark.py: PASS (0 errors)
→ outlier_check.py: PASS (value within cohort)
→ Would auto-merge if the gate worked (see Finding 7)
```

### v2 Status
**Design intends relay-only intake, but provides NO enforcement mechanism.** There is:
- No branch protection requiring PRs from the bot account
- No CODEOWNERS file
- No check that the PR author is `coreai-benchmark-bot`
- No cryptographic signature on the JSONL payload that the Action could verify
- The relay is a "soft" boundary — anyone can bypass it by PRing directly

### Severity: CRITICAL
The single most damaging finding. The entire DeviceCheck defense is bypassable by anyone who reads the public schema.

### Mitigation
1. **Bot-account gate**: Add a workflow step that rejects PRs where `github.event.pull_request.user.login != 'coreai-benchmark-bot'` for paths matching `benchmarks/**`.
2. **Cryptographic payload signature**: The relay signs each JSONL line with an Ed25519 private key. The Action verifies the signature against the public key (stored as a repo secret). Without the relay's private key, no one can forge a valid line.
3. **Branch protection**: Require the `benchmark-validated` status check + restrict pushes to `benchmarks/` to the bot account only.

---

## Finding 2: ANCHOR COHORT POISONING — HIGH

### The Attack
Three sub-vectors:

**2a. Curator device anomaly:** The anchor cohort is "curator-verified reference benchmarks" run on the curator's personal device. If that device has a thermal issue, a different iOS build, or background processes, the anchors are wrong. Every crowd submission is then compared against bad baselines.

**2b. Stale anchors after OS updates:** Anchors refresh "quarterly." iOS updates can deliver significant performance changes (e.g., Core AI engine optimizations). A model that gets a 20% throughput boost from iOS 27.1 would have its legitimate crowd submissions flagged as outliers against stale Q1 anchors showing pre-update performance.

**2c. Social engineering the anchor set:** The curator is human. An attacker could:
- Contribute a "reference benchmark" that gets accepted into the anchor set
- Once in the anchor set, it's "never removed from cohort" — it permanently skews the median
- This is a slow-poisoning vector that the anchor cohort was designed to PREVENT, but it introduces a new poisoning path through the curator

### v2 Status
Partially addressed. The anchor cohort concept is sound for preventing median drift, but:
- No mechanism to detect curator device anomalies
- No automated anchor refresh trigger (only "quarterly" manual)
- No multi-device anchor redundancy (single curator = single point of trust)

### Severity: HIGH
Slow-burn integrity degradation. Not exploitable for immediate injection, but enables gradual dataset corruption.

### Mitigation
1. **Multi-anchor redundancy**: Require anchors from ≥3 distinct curator devices. Flag if any anchor disagrees with the others by >10%.
2. **Automated refresh trigger**: When a new iOS major version ships, auto-flag all anchors for re-measurement within 30 days.
3. **Anchor provenance transparency**: Publish which device + OS version each anchor was measured on. Allow community challenge of stale anchors.
4. **Bootstrap quarantine for anchors too**: New anchors start as `provisional` for 30 days before being counted in the MAD calculation.

---

## Finding 3: AUTO-MERGE EXPLOITATION — CRITICAL

### The Attack
The design specifies 8 auto-merge criteria. The implementation checks **only 3**:

| Criterion | Design | Implemented? |
|-----------|--------|-------------|
| 1. Schema valid | ✓ | ✓ `validate_benchmark.py` |
| 2. model_id exists | ✓ | ✓ Cross-reference check |
| 3. device_verified:true | ✓ | **NO** — not checked |
| 4. extraction_method: app_benchmark_protocol | ✓ | **NO** — not checked |
| 5. MAD < 3.5 | ✓ | ✓ `outlier_check.py` (but see Finding 7) |
| 6. thermal_state nominal/fair | ✓ | **NO** — not checked |
| 7. battery_state: charging | ✓ | **NO** — not checked |
| 8. No duplicate in 7 days | ✓ | **NO** — not checked |

**5 of 8 gates are missing.** An attacker who fabricates a realistic value (within the existing cohort) passes all 3 implemented checks.

### The "10 fabricated devices" Attack
The "no duplicate in 7 days" check is per `device_class`, not per device. Even if implemented, 10 different A18 Pro "devices" (all fabricated) could submit 10 benchmarks in 7 days because they all share `device_class: "A18 Pro"`. The design document's own rate-limit language says "per device class" (line 196), which is the wrong granularity.

### v2 Status
**NOT FIXED.** The design is correct but the implementation is a stub. The workflow YAML has no code for criteria 3, 4, 6, 7, or 8.

### Severity: CRITICAL
Combined with Finding 1 (relay bypass), this means fabricated data can pass all implemented checks.

### Mitigation
1. **Implement all 8 gates** in the workflow as explicit steps.
2. **Rate-limit per DeviceCheck device ID**, not per device_class. The relay knows the device ID (from DeviceCheck) but doesn't publish it. Use a one-way hash of the device ID for deduplication: `sha256(device_check_bit_id + model_id + date)`.
3. **Require N distinct DeviceCheck-verified submitters** before a model exits bootstrap quarantine (design mentions this but no implementation exists).

---

## Finding 4: JSONL INJECTION — HIGH

### The Attack
The PR adds lines to `benchmarks/benchmarks.jsonl`. The workflow extracts ALL added lines:

```bash
git diff origin/main HEAD -- benchmarks/benchmarks.jsonl | grep '^+' | grep -v '^+++' > new_lines.jsonl
```

**4a. Multi-line injection:** The workflow never enforces `line_count == 1`. An attacker can submit 1000 lines in a single PR. The validate script processes each line independently. If the outlier check returns "outlier" for some lines, the script exits 0 (line 127: `return 0  # Don't fail the Action`). The automerge-action then merges the ENTIRE branch, including the outlier lines.

**4b. Embedded newline injection:** If an attacker includes a literal newline character inside a JSON string value (e.g., in the `notes` field), it creates an additional JSONL line. JSON encodes `\n` as `\\n` (escaped), but a raw newline byte in the file would split one logical entry into two physical lines. The validate script's `split("\n")` would treat them as separate entries.

**4c. Null bytes:** JSON preserves `\u0000` in string values. Null bytes can cause issues in downstream consumers (C string termination, database truncation).

**4d. No max string length:** The schema has `minLength: 1` on several fields but no `maxLength`. A 10MB string in `notes` would bloat the JSONL file and slow parsing.

### v2 Status
Partially addressed. JSON Schema validation catches malformed JSON, but the injection vectors above exploit the FORMAT, not the schema.

### Severity: HIGH
The multi-line injection (4a) is the most dangerous — it enables bulk data flooding in a single PR.

### Mitigation
1. **Enforce line_count == 1**: Add `if: steps.extract.outputs.line_count != 1` → fail the workflow.
2. **Sanitize newlines**: After extraction, verify each line has no literal `\n` or `\r` characters: `grep -Pn '[\x00-\x1f]' new_lines.jsonl && exit 1`.
3. **Add maxLength** to all string fields in the schema (e.g., `notes: { maxLength: 500 }`).
4. **Reject null bytes**: `grep -Pn '\x00' new_lines.jsonl && exit 1`.
5. **Fix outlier_check exit code**: Outlier detection should `exit 1` when outliers are found, not `exit 0`. The "don't fail the Action" comment (line 127) defeats the auto-merge gate.

---

## Finding 5: CONCURRENT BENCHMARK RACE — MEDIUM

### The Attack (Accidental)
Two legitimate users benchmark the same model simultaneously. Both PRs modify the same file (`benchmarks/benchmarks.jsonl`). First PR merges. Second PR now conflicts — both appended lines to the same region of the file.

### What Happens
- `pascalgn/automerge-action@v0.16.2` attempts to squash-merge.
- If the PR is behind main and has conflicts, the merge **fails silently**.
- The PR stays open with a conflict status.
- No auto-rebase step exists in the workflow.
- The user's benchmark is stuck until a curator manually resolves the conflict.

### v2 Status
The design claims "each PR is independent, squash-merged" and "zero merge conflicts (append-only)" (lines 142, 588). **This is incorrect.** JSONL append-only does NOT prevent merge conflicts — git tracks line-level changes, and appending to the same file from two branches creates a conflict at the insertion point.

### Severity: MEDIUM
Not a security vulnerability, but a reliability/usability problem that will cause legitimate submissions to stall. At scale (10K+ entries, 5-15 PRs/week), this becomes frequent.

### Mitigation
1. **Auto-rebase before merge**: Add a step using `actions/github-script` or `repo-sync/github-sync` to rebase the PR onto latest main before automerge.
2. **Per-submission file**: Instead of appending to one `benchmarks.jsonl`, each PR creates `benchmarks/pending/bm-{uuid}.jsonl` (the design mentions this at line 305 but the workflow doesn't implement it). A post-merge Action concatenates pending files into the main JSONL.
3. **Queue-based merge**: Use GitHub merge queue (built-in) to serialize PR merges.

---

## Finding 6: COMMUNITY SUBMISSION PATH ABUSE — CRITICAL

### The Attack
The CLI submission path allows entries without DeviceCheck. These get `confidence: low`. The design says they are "excluded from aggregate stats until cross-validated" (line 120).

**The implementation does NOT exclude them.** Verified in code:

`catalog.py` line 166-169:
```python
self._bench_by_model = {}
for b in self._benchmarks:
    mid = b.get("model_id", "")
    self._bench_by_model.setdefault(mid, []).append(b)
```

**ALL benchmarks are loaded with NO confidence filtering.** The readiness score checks `model.confidence` (the MODEL's confidence, line 329), not the benchmark's confidence. There is no aggregation layer that computes medians/percentiles — the design's `benchmarks-aggregate.json` does not exist in the codebase.

### The Flood Attack
An attacker uses the CLI path to submit 1000 low-confidence benchmarks for a target model, all with values slightly above the real median. Since:
- No rate limiting exists on CLI submissions
- No confidence filtering exists in the data loading
- The readiness score gives +10 points just for `has_bench = True` (line 316)
- No aggregate computation exists to detect median skew

The attacker can inflate a model's perceived performance. When `generate.py` picks the "best" benchmark (line 229-231), it takes the max `value` — so one high fabricated value becomes the displayed benchmark.

### v2 Status
**NOT FIXED.** The design promises exclusion of low-confidence entries, but the implementation has no mechanism for it. The aggregation layer described in the design (`dist/benchmarks-aggregate.json`) does not exist.

### Severity: CRITICAL
Lowest-effort attack with highest data-corruption impact. No DeviceCheck needed. No relay needed. No GitHub Actions needed. Just `coreai-cli benchmark submit` in a loop.

### Mitigation
1. **Filter by confidence in catalog loading**: Only load benchmarks with `confidence in ("high", "medium")` into `_bench_by_model`.
2. **Implement the aggregation layer**: Compute per-model+device+config medians with explicit confidence-tiered weighting. High-confidence entries get full weight; low-confidence get 0 weight in aggregate stats.
3. **Rate-limit CLI submissions**: The relay should enforce per-IP rate limits even for community submissions.
4. **Separate storage for unverified**: Store community submissions in a separate `benchmarks-community.jsonl` that is never loaded for readiness scores.
5. **Fix the "best benchmark" selection**: `generate.py` line 229 picks max value — change to median of high-confidence entries only.

---

## Finding 7: OUTLIER CHECK STDOUT BUG — CRITICAL (new, implementation-level)

### The Bug
The outlier check script prints multi-line output:
```
  pass                 qwen3-5-0-8b  value=72.0 (cohort=...)
pass

  All 1 entries passed
```

The workflow captures this as:
```bash
RESULT=$(python3 scripts/outlier_check.py ...)
echo "result=$RESULT" >> $GITHUB_OUTPUT
```

`$RESULT` contains multiple lines. GitHub Actions `GITHUB_OUTPUT` is line-delimited. When a value contains newlines, it must use the heredoc delimiter syntax:
```
result<<EOF
multi-line-value
EOF
```

The workflow does NOT use this syntax. Therefore `steps.mad.outputs.result` captures only the first line (the per-entry detail line), which is never exactly `'pass'`.

### Impact
**Auto-merge NEVER triggers for ANY submission.** The condition `steps.mad.outputs.result == 'pass'` is always false because the output contains detail lines. Every single benchmark PR — legitimate or fabricated — falls through to the "label for review" branch.

This means:
- Auto-merge is completely non-functional (Finding 3 is moot in practice)
- Every PR requires manual curator review (the bottleneck the design tried to eliminate)
- The entire automated pipeline is a no-op

### PoC Verification
```
RESULT=$(python3 scripts/outlier_check.py ...)
FIRST_LINE=$(echo "$RESULT" | head -1)
# FIRST_LINE = '  pass  qwen3-5-0-8b  value=72.0 ...'
# Condition: FIRST_LINE == 'pass' → FALSE
```

### Severity: CRITICAL
The automated intake pipeline is broken. Not a security issue per se, but it means the entire v2 architecture doesn't function as designed. All benchmarks require manual review.

### Mitigation
1. **Fix the output capture**: Use GITHUB_OUTPUT heredoc syntax for multi-line values.
2. **OR fix the script**: Print ONLY the final decision (`pass` / `outlier` / `insufficient-data`) to stdout, send detail lines to stderr.
3. **OR add a dedicated output**: `echo "decision=pass" >> $GITHUB_OUTPUT` as a separate, clean output variable.

---

## Cross-Cutting Observation: Path Mismatch

The workflow triggers on `benchmarks/benchmarks.jsonl` and the outlier check defaults to `--existing benchmarks/benchmarks.jsonl`. **This file does not exist.** The actual data is in `benchmarks.yaml` (root level). The `benchmarks/` directory contains only `protocol-config.json`.

Until the JSONL migration (design Step 1) is executed, the outlier check reads an empty cohort (0 entries) for every submission, returning `insufficient-data` for everything. Combined with Finding 7, the automated pipeline cannot function.

---

## Priority-Ordered Fix List

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| P0 | #7: Fix stdout capture (pipeline is broken) | Small | Unblocks all automation |
| P0 | #1: Add bot-account gate + payload signature | Medium | Closes biggest security hole |
| P0 | #6: Filter low-confidence in catalog loading | Small | Prevents flood attack |
| P1 | #3: Implement missing auto-merge gates | Medium | Enables safe auto-merge |
| P1 | #4: Enforce line_count==1 + sanitize input | Small | Prevents injection |
| P1 | #4: Fix outlier_check exit code | Trivial | Outliers block merge |
| P2 | #2: Multi-device anchors + refresh triggers | Medium | Long-term integrity |
| P2 | #5: Auto-rebase or per-file pending queue | Medium | Reliability at scale |
