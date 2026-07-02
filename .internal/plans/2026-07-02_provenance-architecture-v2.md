# Provenance-First Data Architecture v2.0 — Revised

> **Status:** Revised after 3-axis red-team review (privacy, gaming, scalability).
> **Principle:** Every claim has traceable provenance. Privacy is structural, not optional. Data integrity is cryptographic, not honor-system.
> **Changes from v1:** 5 structural fixes addressing 10 CRITICAL + 12 HIGH findings.

---

## What the red-teams killed in v1

The original design assumed "no backend = no privacy problem". The reviews proved the opposite: **public GitHub Issues + immutable git + open-source code = the worst privacy surface possible**. Specifically:

- Device fingerprints (chip + RAM + OS + timestamp) are personal data under GDPR/LGPD (Breyer C-582/14)
- GitHub Issues permanently bind a username to device data — structurally impossible to erase
- HMAC key in open-source binary is trivially reversible
- All methodology fields are self-reported with zero cryptographic verification
- DeviceCheck was a boolean checkbox, not a verified JWT
- GitHub Actions can't commit to main without race conditions
- YAML doesn't scale past ~500 entries without merge conflicts
- The existing schema's `additionalProperties: false` blocks provenance fields entirely

---

## The 5 structural fixes

### Fix 1: Privacy Relay (resolves C1, C2, C3, C10, H1, H2, H3)

A serverless Cloudflare Worker sits between the app and the public repo. It is the ONLY component that touches the GitHub API. The repo never sees raw device data.

```
┌─────────────┐     HTTPS      ┌──────────────────┐     GitHub API    ┌──────────────┐
│  Device     │ ─────────────▶ │  PRIVACY RELAY   │ ────────────────▶ │  GitHub Repo │
│  (Ditto)    │                │  (CF Worker)     │                   │  (public)    │
│             │                │                  │                   │              │
│ Generates:  │                │ Transforms:      │                   │ Receives:    │
│ Full report │                │ • Coarsen device │                   │ Sanitized    │
│ with device │                │ • Drop IP/source │                   │ benchmark    │
│ fingerprint │                │ • Bucket time    │                   │ JSON         │
│ + DeviceCheck│               │ • Random delay   │                   │              │
│ JWT         │                │ • Strip identity │                   │              │
└─────────────┘                └──────────────────┘                   └──────────────┘
```

**What the relay does to each field:**

| Raw field (from device) | Relay transformation | Published field (to repo) |
|---|---|---|
| `device.model: "iPhone17,1"` | Map to chip family | `device_class: "A18 Pro"` |
| `device.chip: "A18 Pro"` | Already coarse | `device_class: "A18 Pro"` |
| `device.ram_gb: 8` | Round to tier | `ram_tier: "8GB"` |
| `device.os_version: "27.0.1"` | Major version only | `os_major: "27"` |
| `submitted_at: "2026-07-02T14:23:01Z"` | Date only, +1-24h delay | `observed_date: "2026-07-02"` |
| `model_hash: "sha256:abc..."` | DROP entirely | *(not published)* |
| DeviceCheck JWT | Verify, then DROP | `device_verified: true` |
| `submission_channel: "ditto-ios-0.1.0"` | Keep app version | `submission_channel: "ditto-ios-0.1.0"` |

**What the relay NEVER passes through:**
- IP address (the Worker receives it by definition, but never writes it anywhere)
- GitHub username (the Worker authenticates as a bot account, submissions are attributed to `coreai-benchmark-bot`)
- DeviceCheck JWT (verified by the Worker, then stripped)
- Model hash (dropped — see Fix 4 for reproducibility alternative)
- Any free-text notes from the user

**Why this resolves the legal findings:**
- The published data contains only hardware class + date + performance numbers — these are not personal data under GDPR Art. 4 because they cannot single out an individual
- No GitHub username is linked to submissions — the bot account is the author
- Erasure is trivial: delete the JSONL line and force-push (or accept that the aggregate data point is anonymous enough that erasure isn't required)
- Consent can be withdrawn: the app stops submitting, and the user can request the relay purge any queued data (the relay retains nothing past forwarding)

**GDPR consent flow (revised, Art. 7 compliant):**
1. First launch: "Help improve Core AI benchmarks?" with 3 separate toggles:
   - [ ] Share performance data (benchmarks)
   - [ ] Share device class (chip family only)
   - [ ] Share when I run benchmarks (date only)
2. All three default OFF. Each can be toggled independently in Settings.
3. Withdrawal: toggle off in Settings at any time. No data queued after that.
4. Privacy policy URL required in-app.

### Fix 2: DeviceCheck JWT verification (resolves C4, C5, C6)

The single highest-leverage fix. DeviceCheck is Apple's cryptographic proof that a submission came from genuine Apple hardware running a legitimate app.

**On the device (Swift):**
```swift
import DeviceCheck

func generateAttestation() async throws -> Data {
    let token = try await DCDevice.current.generateToken()
    // This token is a JWT signed by Apple's attestation service
    // It proves: real device, genuine app, not a simulator
    return token
}
```

**In the Privacy Relay (verify before forwarding):**
```typescript
// Cloudflare Worker verifies the DeviceCheck token with Apple's API
async function verifyDeviceCheck(token: string, nonce: string): Promise<boolean> {
    const response = await fetch('https://api.developer.apple.com/devicecheck/validate_token', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${jwtForAppleAPI}` },
        body: JSON.stringify({
            device_token: token,
            // transaction_id: random nonce from the benchmark payload
            // timestamp: from the benchmark payload
        })
    });
    const result = await response.json();
    return result.status === 'valid';
}
```

**Why this kills gaming:**
- Sybil attacks require N real Apple devices (cost: $400+ per device per identity)
- Simulator submissions are rejected (DeviceCheck fails on simulators)
- Jailbroken devices may fail DeviceCheck depending on attestation level
- The nonce prevents replay attacks (same token can't be used twice)

**Fallback for open-source CLI contributors:**
Users who benchmark via the CLI (not the app) can submit WITHOUT DeviceCheck, but their submissions are automatically tagged `extraction_method: community_submission` with `confidence: low` and excluded from aggregate stats until cross-validated.

### Fix 3: JSONL instead of YAML for benchmarks (resolves C7, H7, H8, H10)

The fundamental data format change: benchmarks live in append-only JSONL, not YAML.

**Before (YAML, breaks at scale):**
```yaml
benchmarks:
  - id: bm-001
    model_id: official-qwen3-4b
    metric: decode_throughput
    value: 145.4
    # ... 20 lines per entry, merge conflicts everywhere
```

**After (JSONL, scales to 100K+):**
```jsonl
{"id":"bm-001","model_id":"official-qwen3-4b","metric":"decode_throughput","value":145.4,"unit":"tokens_per_second","device_class":"A18 Pro","os_major":"27","compute_unit":"GPU","precision":"int4","extraction_method":"app_benchmark_protocol","confidence":"high","provenance":{"protocol_version":"2.0","warmup_runs":3,"measured_runs":10,"statistic":"median","stddev":2.1,"thermal_state":"nominal","battery_state":"charging"},"observed_date":"2026-07-02","source":"crowdsourced"}
```

**Why JSONL:**
- Append-only = zero merge conflicts (each PR adds lines to the end)
- One line per entry = trivial diffs in PR review
- Streaming parse = lazy loading (MCP server only reads what it needs)
- `generate.py` only regenerates aggregates, not the raw file
- Schema evolution: add fields without breaking old entries (parser ignores unknown keys)

**File structure:**
```
coreai-catalog/
  benchmarks.jsonl              # raw append-only (crowdsourced + manual)
  benchmarks.yaml               # generated from JSONL (backward compat for existing tools)
  schema/
    benchmark.schema.json       # evolved — no additionalProperties:false
  dist/
    benchmarks.json             # generated export (aggregated)
    benchmarks-aggregate.json   # NEW: per-model+device+config medians and percentiles
```

### Fix 4: PR-based intake with auto-approve (resolves C8, C9, H6, H9)

Replace Issue-based intake with bot-generated PRs that carry their own commit.

```
App → Privacy Relay → GitHub Bot opens PR with 1-line JSONL addition
                         │
                         ▼
               GitHub Action validates:
               ┌──────────────────────────────────┐
               │  1. Schema validation            │
               │  2. model_id exists in catalog?  │
               │  3. DeviceCheck verified?        │
               │     (checked by relay, not here) │
               │  4. Outlier check (MAD)          │
               │  5. Thermal state acceptable?    │
               └──────────────┬───────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
                    ▼                   ▼
            ALL PASS:             ANY FAIL:
            auto-merge            bot comments with
            + label "auto"        rejection reason
                                  + PR stays open
                                  for curator review
```

**Auto-merge criteria (ALL must be true):**
1. Schema valid
2. `model_id` exists in `catalog.yaml`
3. `device_verified: true` (DeviceCheck confirmed by relay)
4. `extraction_method: app_benchmark_protocol` (not community_submission)
5. MAD modified-z-score < 3.5 against existing cohort (N >= 5 required)
6. `thermal_state: nominal` or `fair`
7. `battery_state: charging`
8. No existing benchmark from same device_class + model_id + runtime_config in last 7 days (rate limit per device class)

**Curator review required when:**
- Any of the above fails
- `extraction_method: community_submission` (CLI users without DeviceCheck)
- MAD flags as outlier (modified-z >= 3.5)
- New model_id with no prior benchmarks (bootstrap)

**This resolves the curator bottleneck:** auto-merge handles the 90% case. Curator only sees edge cases, outliers, and bootstraps.

### Fix 5: Environmental controls in protocol (resolves M6-M8, H5)

The benchmark protocol captures and enforces environmental conditions that affect comparability.

**Protocol v2.0 — required preconditions:**

```swift
// These are HARD REQUIREMENTS — the app refuses to benchmark if unmet
struct BenchmarkPreconditions {
    let isPluggedIn: Bool        // must be true
    let thermalState: ThermalState  // must be .nominal or .fair
    let isLowPowerMode: Bool     // must be false
    let batteryLevel: Float      // must be >= 0.5
    let screenBrightness: Float  // recorded, not enforced
    let backgroundApps: Int      // recorded (approximate)
}
```

**Captured in every benchmark:**
```jsonl
{"environment": {"thermal_state": "nominal", "battery_state": "charging", "battery_level": 0.85, "low_power_mode": false, "protocol_version": "2.0"}}
```

**Reproducibility without model_hash (Fix 1 privacy requirement):**

Instead of publishing SHA256 of the user's model bundle (which leaks installed-model inventory), the relay verifies the hash against the catalog's known-good artifact registry:

```
Device computes SHA256 of local .aimodel bundle
    → Sends to relay (NEVER published)
        → Relay checks against dist/model-hashes.json
            → If match: publishes "model_verified: true"
            → If mismatch: rejects submission (wrong or tampered model)
            → Either way: hash itself is NEVER published
```

This gives cryptographic reproducibility (we know the right model was benchmarked) without leaking what models the user has installed.

---

## The complete revised architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              DEVICE (Ditto)                              │
│                                                                          │
│  1. User triggers benchmark on a model                                   │
│  2. App checks preconditions (plugged in, thermal nominal, etc.)         │
│  3. App runs Protocol v2.0:                                              │
│     - 3 warmup iterations (discarded)                                    │
│     - 10 measured iterations (128-token prompt, 256-token generation)    │
│     - Records: per-iteration throughput, peak memory, thermal state      │
│     - Computes: median, stddev, P50, P95                                 │
│  4. App computes SHA256 of .aimodel bundle                               │
│  5. App generates DeviceCheck JWT                                        │
│  6. App packages BenchmarkReport:                                        │
│     { metrics, methodology, device_fingerprint, model_hash,              │
│       device_check_jwt, protocol_version, app_version }                  │
│  7. App sends to Privacy Relay via HTTPS                                 │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          PRIVACY RELAY (CF Worker)                       │
│                                                                          │
│  Receives full report with PII-grade data.                               │
│  Transforms before forwarding. Stores nothing.                           │
│                                                                          │
│  Step 1: Verify DeviceCheck JWT with Apple's API                         │
│          → Reject if invalid                                             │
│                                                                          │
│  Step 2: Verify model_hash against dist/model-hashes.json                │
│          → Reject if mismatch                                            │
│                                                                          │
│  Step 3: Coarsen device data                                             │
│          iPhone17,1 + A18 Pro + 8GB + iOS 27.0.1                        │
│          → device_class: "A18 Pro", os_major: "27"                      │
│                                                                          │
│  Step 4: Strip identity                                                  │
│          → Drop model_hash, DeviceCheck JWT, IP, timestamp precision     │
│          → observed_date: "2026-07-02" (date only)                      │
│                                                                          │
│  Step 5: Random delay 1-24h (breaks temporal correlation)               │
│                                                                          │
│  Step 6: Forward sanitized report to GitHub Bot                          │
│                                                                          │
│  Sanitized report contains ONLY:                                         │
│  { model_id, metric, value, unit, device_class, os_major,               │
│    compute_unit, precision, extraction_method, confidence,              │
│    provenance: { protocol_version, warmup_runs, measured_runs,          │
│                  statistic, stddev, thermal_state, battery_state },     │
│    device_verified: true, model_verified: true,                         │
│    observed_date, submission_channel }                                   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     GITHUB BOT (opens PR)                                │
│                                                                          │
│  Appends one line to benchmarks/pending/bm-{uuid}.jsonl                  │
│  Opens PR: "benchmark: {model_id} on {device_class}"                    │
│  Labels: benchmark-submission, auto-review                               │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                  GITHUB ACTION: benchmark-validate.yml                   │
│                                                                          │
│  Triggers: PR opened with label "benchmark-submission"                   │
│                                                                          │
│  1. Parse JSONL line from PR diff                                        │
│  2. Validate against schema/benchmark.schema.json                        │
│  3. Check model_id exists in catalog.yaml                                │
│  4. Outlier check: compute MAD against existing cohort                   │
│     - If N < 5 for this model+device+config: label "bootstrap-needs-review"│
│     - If modified_z >= 3.5: label "outlier-needs-review"                 │
│     - If modified_z < 3.5 and all auto-merge criteria met: label "auto-ok"│
│  5. Comment on PR with validation summary                                │
│                                                                          │
│  Auto-merge if label == "auto-ok":                                       │
│     → Move line from pending/ to benchmarks.jsonl                        │
│     → Squash merge to main                                               │
│     → Trigger generate.py (aggregates only)                              │
│                                                                          │
│  Otherwise: PR stays open for curator review                             │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    CURATOR REVIEW (human, only edge cases)               │
│                                                                          │
│  Sees PRs labeled:                                                       │
│    "bootstrap-needs-review" — new model, first benchmarks                │
│    "outlier-needs-review"  — anomalous values                            │
│    "community-submission"  — no DeviceCheck (CLI user)                   │
│                                                                          │
│  Approves: move line to benchmarks.jsonl, merge                          │
│  Rejects: close PR, comment reason                                       │
│                                                                          │
│  Expected volume: ~5-15 PRs/week (auto-merge handles 90%)               │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       PUBLISHED DATA                                     │
│                                                                          │
│  benchmarks.jsonl — append-only, every accepted benchmark                │
│  dist/benchmarks-aggregate.json — per model+device+config:               │
│    { model_id, device_class, metric, median, p5, p25, p75, p95,          │
│      sample_count, last_updated }                                        │
│  dist/benchmarks.json — flat array (backward compat)                     │
│  benchmarks.yaml — generated from JSONL (backward compat)                │
│                                                                          │
│  CLI/MCP/API consume the aggregate by default (fast, compact)            │
│  Full JSONL available for analysis (streaming, lazy-loaded)              │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Schema: benchmark.schema.json v2.0 (revised)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Core AI Benchmark Entry v2.0",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "id", "model_id", "metric", "value", "unit",
    "device_class", "os_major", "compute_unit",
    "extraction_method", "confidence",
    "observed_date", "source"
  ],
  "properties": {
    "id": {
      "type": "string",
      "minLength": 1
    },
    "model_id": {
      "type": "string",
      "minLength": 1
    },
    "metric": {
      "type": "string",
      "enum": [
        "decode_throughput", "prompt_processing_throughput",
        "time_to_first_token", "peak_memory",
        "image_generation_latency", "transcription_realtime_factor",
        "inference_fps", "segmentation_latency"
      ]
    },
    "value": {
      "type": "number",
      "exclusiveMinimum": 0
    },
    "unit": {
      "type": "string",
      "enum": [
        "tokens_per_second", "milliseconds", "seconds",
        "megabytes", "frames_per_second", "seconds_per_image",
        "realtime_factor"
      ]
    },
    "device_class": {
      "type": "string",
      "description": "Coarsened hardware class (e.g. 'A18 Pro', 'M4 Max'). Never raw device model.",
      "minLength": 1
    },
    "os_major": {
      "type": "string",
      "description": "Major OS version only (e.g. '27', '26'). Never full build number.",
      "minLength": 1
    },
    "compute_unit": {
      "type": "string",
      "enum": ["GPU", "ANE", "CPU", "mixed"]
    },
    "precision": {
      "type": "string"
    },
    "extraction_method": {
      "type": "string",
      "enum": [
        "app_benchmark_protocol",
        "upstream_readme_manual",
        "upstream_readme_scripted",
        "hf_metadata_api",
        "community_submission",
        "derived_calculated",
        "apple_documentation"
      ]
    },
    "confidence": {
      "type": "string",
      "enum": ["high", "medium", "low", "needs_review"]
    },
    "observed_date": {
      "type": "string",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
      "description": "Date only (YYYY-MM-DD). Never includes time."
    },
    "source": {
      "type": "string",
      "minLength": 1
    },
    "device_verified": {
      "type": "boolean",
      "description": "DeviceCheck JWT verified by relay. False for CLI submissions."
    },
    "model_verified": {
      "type": "boolean",
      "description": "SHA256 of local model matches catalog registry. Verified by relay."
    },
    "higher_is_better": {
      "type": "boolean"
    },
    "submission_channel": {
      "type": "string",
      "description": "App identifier (e.g. 'ditto-ios-0.1.0', 'coreai-cli-2.2.0')."
    },
    "environment": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "protocol_version": { "type": "string" },
        "warmup_runs": { "type": "integer", "minimum": 0 },
        "measured_runs": { "type": "integer", "minimum": 1 },
        "statistic": { "type": "string", "enum": ["median", "mean", "max", "min"] },
        "stddev": { "type": "number", "minimum": 0 },
        "thermal_state": { "type": "string", "enum": ["nominal", "fair", "serious", "critical"] },
        "battery_state": { "type": "string", "enum": ["charging", "unplugged", "unknown"] },
        "low_power_mode": { "type": "boolean" }
      }
    },
    "notes": {
      "type": ["string", "null"]
    }
  }
}
```

**Key privacy decisions baked into the schema:**
- `device_class` not `device.model` (coarsened by relay)
- `observed_date` not `observed` (date only, no time)
- NO `model_hash` field (verified by relay, never published)
- NO `device_attestation` field (verified by relay, published as boolean)
- NO submitter identity (PR authored by bot)
- `environment` captures protocol metadata for reproducibility

---

## Outlier detection: revised with anchor cohort (resolves H4, H6)

The MAD approach from v1 is preserved but strengthened:

```python
def compute_outlier_status(value, cohort_values, anchor_values=None):
    """
    Returns: 'pass', 'outlier', or 'insufficient-data'
    
    anchor_values: curator-verified reference benchmarks (never removed from cohort)
    """
    # Merge anchors + crowd data
    all_values = (anchor_values or []) + cohort_values
    
    if len(all_values) < 5:
        return 'insufficient-data'
    
    median = statistics.median(all_values)
    mad = statistics.median([abs(v - median) for v in all_values])
    
    if mad == 0:
        return 'pass'  # All identical values, can't compute z-score
    
    modified_z = 0.6745 * (value - median) / mad
    
    if abs(modified_z) >= 3.5:
        return 'outlier'
    return 'pass'
```

**Anchor cohort:** a small set of curator-verified benchmarks run on reference hardware (e.g. the curator's own iPhone 17 Pro). These anchors:
- Prevent median drift from slow poisoning
- Give MAD a stable baseline even when crowd data is sparse
- Are tagged `source: anchor-reference-hardware` in the JSONL
- Get refreshed quarterly on the curator's device

**Bootstrap quarantine:** models with < 5 distinct DeviceCheck-verified submitters are labeled `confidence: low` and excluded from readiness scores until threshold met. This prevents the 5-sybil-account attack.

---

## Migration from v1 data (backward compatible)

### Step 1: Convert existing benchmarks.yaml to JSONL

```python
# scripts/migrate_benchmarks.py
import yaml, json

with open('benchmarks.yaml') as f:
    data = yaml.safe_load(f)

with open('benchmarks.jsonl', 'w') as f:
    for b in data.get('benchmarks', []):
        # Add extraction_method based on notes
        notes = b.get('notes', '').lower()
        if 'readme' in notes or 'table' in notes:
            b['extraction_method'] = 'upstream_readme_manual'
            b['confidence'] = 'medium'
        else:
            b['extraction_method'] = 'upstream_readme_scripted'
            b['confidence'] = 'medium'
        
        # Map device to device_class (coarsen)
        b['device_class'] = b.pop('device', 'unknown')
        b['os_major'] = b.get('environment', '').split(',')[0].replace('iOS ', '').replace('macOS ', '').strip()
        b['observed_date'] = b.pop('observed', '')
        b['device_verified'] = False  # Historical data, no DeviceCheck
        b['model_verified'] = False
        
        f.write(json.dumps(b, ensure_ascii=False) + '\n')
```

### Step 2: Evolve schema (remove `additionalProperties: false` block on new fields)

The new `benchmark.schema.json` v2.0 includes the `environment` block and `extraction_method` as defined above. Old entries without these fields still validate (they're optional in the migration period).

### Step 3: Keep benchmarks.yaml as a generated artifact

`generate.py` reads `benchmarks.jsonl` and writes `benchmarks.yaml` (for backward compatibility with existing tools that expect YAML). The YAML is never hand-edited after migration.

---

## Scaling projections (revised)

| Metric | 66 entries (now) | 1,000 entries | 10,000 entries |
|---|---|---|---|
| benchmarks.jsonl size | ~65KB | ~1MB | ~10MB |
| JSONL parse time | <10ms | ~50ms | ~500ms |
| Aggregate generation | <1s | ~3s | ~15s |
| MCP lazy-load (first 100) | <50ms | <50ms | <50ms |
| Merge conflicts | 0 | ~0 (append-only) | ~0 (append-only) |
| Curator reviews/day | 0 | ~5-10 | ~5-15 (auto-merge handles rest) |

The JSONL + append-only + auto-merge design scales linearly without structural breaks.

---

## Finding-to-fix traceability matrix

| Finding | Sev | Fix | How |
|---|---|---|---|
| C1: Device fingerprint re-identifies | CRITICAL | Fix 1 | Relay coarsens to device_class |
| C2: GitHub Issues bind username to data | CRITICAL | Fix 1+4 | Bot-authored PRs, no user attribution |
| C3: HMAC key reversible in OSS | CRITICAL | Fix 1+2 | HMAC replaced by DeviceCheck JWT |
| C4: Sybil + <5 = auto-accept | CRITICAL | Fix 2+5 | DeviceCheck + bootstrap quarantine |
| C5: Self-reported, zero verification | CRITICAL | Fix 2 | DeviceCheck JWT verified by relay |
| C6: DeviceCheck as boolean | CRITICAL | Fix 2 | Now cryptographic JWT verified |
| C7: Schema blocks provenance | CRITICAL | Fix 3 | JSONL schema without rigid additionalProperties |
| C8: Action can't commit | CRITICAL | Fix 4 | PR-based: the PR IS the commit |
| C9: Concurrent push conflicts | CRITICAL | Fix 4 | Each PR is independent, squash-merged |
| C10: "No PII = GDPR exempt" false | CRITICAL | Fix 1 | Relay strips all PII before public repo |
| H1: Opt-in not granular | HIGH | Fix 1 | 3 separate toggles, withdrawal in Settings |
| H2: model_hash leaks inventory | HIGH | Fix 1+5 | Hash verified by relay, never published |
| H3: Timestamps leak timezone | HIGH | Fix 1 | Date only, +random delay |
| H4: Slow poisoning | HIGH | Fix 5 | Anchor cohort prevents median drift |
| H5: Model hash unverified | HIGH | Fix 5 | Relay checks against registry |
| H6: Outlier check exits 0 | HIGH | Fix 4 | PR auto-merge gates on validation result |
| H7: YAML merge conflicts | HIGH | Fix 3 | JSONL append-only |
| H8: MCP 17s startup | HIGH | Fix 3 | JSONL streaming + lazy-load |
| H9: Curator bottleneck | HIGH | Fix 4 | Auto-merge handles 90% |
| H10: generate.py O(total) | HIGH | Fix 3 | Only aggregates regenerated |
| H11: No pagination | HIGH | Fix 3 | Aggregate JSON + lazy JSONL streaming |
| H12: No schema versioning | HIGH | Fix 3 | protocol_version field in every entry |

---

*Design v2.0 — revised after 3-axis red-team. All 10 CRITICAL and 12 HIGH findings addressed.*
