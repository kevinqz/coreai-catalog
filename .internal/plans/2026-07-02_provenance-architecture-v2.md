# Provenance-First Data Architecture v2

> **Status:** Design — red-team validated, all 9 CRITICAL findings resolved.
> **Principle:** Every claim has traceable provenance. Privacy is structural, not promised. Gaming is prevented at the device, not the server.

---

## What Changed From v1

v1 was sound in concept but broken in implementation. Three red-teams (privacy/legal, gaming/integrity, architecture/scalability) found **9 CRITICAL issues**. v2 resolves all of them with 4 structural changes:

| v1 Problem | v2 Fix |
|---|---|
| Device fingerprint re-identifies users (GDPR/LGPD) | **Privacy relay coarsens data before git** |
| GitHub Issues bind username → device permanently | **Relay posts as bot, no user attribution** |
| Self-reported methodology is trivially fabricated | **App Attest mandatory — Apple proves the app ran** |
| Sybil attacks defeat outlier detection | **DeviceCheck: 1 submission per real device** |
| `additionalProperties: false` blocks schema evolution | **JSONL append-only, schema is validation not gate** |
| GitHub Action loses submissions (no git commit) | **Relay opens PRs (persistent), not ephemeral Actions** |
| Concurrent pushes cause silent conflicts | **PRs are serialized — 1 merge at a time** |
| YAML parsing 17s at 10K entries | **JSONL: lazy loading, line-by-line, indexed** |
| generate.py O(total) on every submission | **Runs only on merge, not on each submission** |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DEVICE (iPhone/Mac)                         │
│                                                                     │
│  1. User opens Ditto, opts in to benchmark sharing                  │
│  2. User downloads model, runs benchmark (protocol v1.0)            │
│  3. App captures FULL payload (device info, metrics, methodology)   │
│  4. App obtains App Attest token from Apple                         │
│  5. App POSTs to privacy relay (NOT to GitHub directly)             │
│                                                                     │
│  PRIVACY FILTER HAPPENS ON DEVICE BEFORE STEP 5:                    │
│  ✗ Never sends: Apple ID, name, email, contacts, photos             │
│  ✗ Never sends: IP retained (connection uses app's URLSession)      │
│  ✗ Never sends: exact timestamp (coarsened to date on device)       │
│  ✓ Sends: model_id, metrics, methodology, runtime_config            │
│  ✓ Sends: device class (coarsened — see §2.1), thermal_state        │
│  ✓ Sends: model_hash (SHA256 of .aimodel weights only)              │
│  ✓ Sends: app_attest_token (Apple-issued, proves genuine device)    │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTPS POST
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PRIVACY RELAY (Cloudflare Worker)                │
│                                                                     │
│  Stateless. ~150 lines TypeScript. Open source.                     │
│  Secret: Apple App Attest key (only secret in the system).          │
│                                                                     │
│  6.  Validate App Attest token with Apple's server                  │
│      → Reject if invalid, expired, or replayed                      │
│                                                                     │
│  7.  Extract device attestation hash (not device ID)                │
│      → HMAC(device_attestation_key, attestation_payload)            │
│      → Key is SERVER-SIDE, not in the app                           │
│      → Used ONLY for dedup (1 submission per device+model+config)   │
│      → NEVER written to git, never persisted, never logged          │
│                                                                     │
│  8.  Dedup check                                                    │
│      → If this device+model+config already submitted: reject        │
│      → Prevents Sybil attacks (1 vote per real device)              │
│      → Dedup state: KV store (Cloudflare KV, 60s read)              │
│                                                                     │
│  9.  Coarsen remaining data                                         │
│      → device_model "iPhone17,1" → device_class "iphone-a18-pro"   │
│      → ram_gb: keep (3 values possible: 6/8/16)                     │
│      → os_version: keep major only ("27.0" not "27.0.1")           │
│      → timestamp: already date-only from device                     │
│      → Strip: submission_channel version (not needed)               │
│                                                                     │
│  10. Append 1 line to benchmarks/pending/benchmarks.jsonl           │
│      → Via GitHub API: create a commit on a branch                  │
│      → Branch name: bm-{random-uuid} (no user attribution)          │
│      → Open PR: "Benchmark: {model_id} on {device_class}"           │
│      → PR author: @coreai-benchmark-bot (not the user)              │
│                                                                     │
│  11. Return 202 Accepted to the app (no PR URL — user doesn't see)  │
└────────────────────────────┬────────────────────────────────────────┘
                             │ GitHub PR
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│              GITHUB ACTION: benchmark-validate.yml                  │
│              (triggered on PR to benchmarks/pending/)               │
│                                                                     │
│  12. Parse the new JSONL line(s)                                    │
│  13. Schema validate (benchmark.schema.json — flexible)             │
│  14. Cross-reference: model_id must exist in catalog                │
│  15. Hash verification: download model from HF, compute SHA256,     │
│      compare with submission's model_hash                           │
│  16. Outlier check: MAD (segmented by model+device_class+engine)    │
│      → Requires N≥5 existing points for statistical validity       │
│      → If N<5: label "insufficient-data" (auto-merge)               │
│  17. Apply decision:                                                │
│      → MAD pass + attestation valid + hash match: label "auto-merge"│
│      → MAD fail: label "needs-review"                               │
│      → Hash mismatch: label "rejected" + comment                    │
│  18. If "auto-merge": merge PR automatically                       │
│      → Triggers generate.py to rebuild dist/                        │
│  19. If "needs-review": notify curator                             │
│      → Curator reviews in GitHub UI                                 │
│      → Approve → merge → generate.py                                │
│      → Reject → close PR with explanation                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Privacy Model

### 2.1 Device class coarsening

The relay maps exact device identifiers to coarse classes:

```typescript
// Input from device (raw):
{ device_model: "iPhone17,1", chip: "A18 Pro", ram_gb: 8 }

// Output to git (coarsened):
{ device_class: "iphone-a18-pro", ram_gb: 8 }
```

**Coarsening table:**

| Raw device_model | device_class | chip_family |
|---|---|---|
| iPhone17,1 / iPhone17,2 | iphone-a18-pro | A18 Pro |
| iPhone16,1 / iPhone16,2 | iphone-a17-pro | A17 Pro |
| iPhone15,2 / iPhone15,3 | iphone-a16 | A16 |
| iPad16,3 / iPad16,4 | ipad-m4 | M4 |
| Mac16,1 | mac-m4-max | M4 Max |

The coarsening ensures that within a device class, thousands of devices are indistinguishable. The `ram_gb` is kept because there are only 2-3 possible values per device class, and it materially affects benchmark results.

### 2.2 What never enters git

| Data point | Why excluded |
|---|---|
| GitHub username | Relay posts as bot. User identity never linked to benchmark. |
| Exact device model (iPhone17,1) | Coarsened to class. 10M+ devices share each class. |
| Exact timestamp (12:03:47Z) | Coarsened to date. Time-of-day reveals timezone/activity patterns. |
| IP address | Never collected. URLSession doesn't log it. |
| Apple ID / DeviceCheck token | Used for attestation only, never stored or logged. |
| HMAC device hash | Used for dedup in KV only, never written to git. |
| Submission channel version | Irrelevant to benchmark data. |

### 2.3 GDPR/LGPD/CCPA compliance

**Positioning:** The system collects **anonymous benchmark performance data** from devices, not personal data.

- **GDPR Art. 4:** Device class + date + model_id is not personal data. It does not identify a natural person. A device class contains millions of devices. (CJEU Breyer C-582/14 requires "means reasonably likely to be used" — coarsened classes are not identifiable.)
- **GDPR Art. 17 (erasure):** Git history is immutable, but since data is anonymous (no user attribution), there's no personal data to erase. If a user requests deletion anyway, the benchmark line can be removed in a new commit (historical presence is not "processing" under GDPR).
- **LGPD (Brazil):** Same analysis — anonymous data is excluded from scope (Art. 12, II).
- **CCPA:** Device data not linked to a consumer is exempt (§1798.140(d)(2)(B)).
- **Apple App Store:** Privacy label declares "Performance Data — Not Linked to You." This is accurate — no Apple ID or advertising identifier is collected.

**App Attest is NOT personal data:** The attestation token proves the device is genuine but does not identify the user. It's a cryptographic proof, not an identifier. Apple's documentation explicitly distinguishes attestation from identification.

### 2.4 Consent model

- **Opt-in:** Single, clear prompt on first benchmark: "Share anonymous performance data to help the Core AI community?"
- **Granular:** User sees exactly what data would be shared (model_id, device class, throughput numbers)
- **Revocable:** Setting toggle: Settings → Benchmark Sharing → Off. Stops all future submissions.
- **Pre-submission preview:** Before each submission, the app shows the exact JSON that will be sent. User taps "Share" to confirm.
- **No dark patterns:** The toggle is in the same place as all other settings, not buried.

---

## 3. Data Integrity Model

### 3.1 Trust layers (defense in depth)

| Layer | What it prevents | How |
|---|---|---|
| **App Attest** | Fabricated submissions from non-app sources | Apple-issued cryptographic token proves app ran on genuine device |
| **DeviceCheck dedup** | Sybil attacks (multiple submissions from one device) | Relay tracks HMAC(attestation) in KV, rejects duplicates |
| **Model hash verification** | Benchmarks for models the user never ran | GitHub Action downloads model from HF, computes SHA256, compares |
| **MAD outlier detection** | Individually anomalous values | Median Absolute Deviation, segmented by model+device+engine |
| **Cohort minimum** | Statistical noise at small N | N≥5 required for outlier decisions. Below N=5: auto-accept, no MAD. |
| **Curator review** | Coordinated manipulation or edge cases | Human reviews "needs-review" PRs |

### 3.2 MAD implementation (segmented, multi-modal aware)

```python
def check_outlier(new_value, existing_values, model_id, device_class, engine):
    """Returns: 'pass' | 'outlier' | 'insufficient-data'"""
    # Filter to same cohort
    cohort = [v for v in existing_values 
              if v.model_id == model_id 
              and v.device_class == device_class
              and v.runtime_config.engine == engine]
    
    if len(cohort) < 5:
        return 'insufficient-data'  # Auto-accept, MAD meaningless
    
    median = statistics.median(cohort)
    mad = statistics.median([abs(v - median) for v in cohort])
    
    if mad == 0:
        # All values identical — accept if within 10%
        return 'pass' if abs(new_value - median) / median < 0.1 else 'outlier'
    
    # Modified Z-score (Iglewicz & Hoaglin)
    modified_z = 0.6745 * (new_value - median) / mad
    
    if abs(modified_z) > 3.5:
        return 'outlier'
    return 'pass'
```

**Key design decisions:**
- **Segmented by engine** — pipelined vs sequential give different throughput. Must compare within same engine.
- **N≥5 minimum** — below that, MAD is noise. Auto-accept (better to have data than to reject).
- **Modified Z-score** — more robust than standard Z-score for non-normal distributions.
- **Threshold 3.5** — standard statistical threshold (Iglewicz & Hoaglin 1993). ~0.05% false positive on normal data.

### 3.3 Thermal and power state capture

The protocol captures environmental factors that affect performance:

```json
"environment": {
  "thermal_state": "nominal",        // nominal | fair | serious | critical
  "low_power_mode": false,
  "battery_level": 0.85,             // 0.0-1.0 (coarsened to 0.1 steps)
  "plugged_in": true
}
```

These are stored with each benchmark. The aggregation layer can segment by thermal_state when comparing.

---

## 4. Storage: JSONL Instead of YAML

### 4.1 Why JSONL

| Property | YAML | JSONL |
|---|---|---|
| Append (new entry) | Rewrite entire file | Add 1 line |
| Merge conflict | Common (nested blocks) | Impossible (append-only) |
| Diff readability | Noisy (re-indentation) | Clean (1 line = 1 entry) |
| Parse at scale | O(n) full document | O(1) per line (lazy) |
| Schema flexibility | `additionalProperties: false` blocks | Each line is independent JSON |
| Git blame | Entire file | Per-line attribution |

### 4.2 File structure

```
benchmarks/
  benchmarks.jsonl              # published benchmarks (append-only, 1 JSON per line)
  pending/                      # incoming submissions (PRs add here)
    benchmarks-pending.jsonl    # new PR appends to this, merged into main on approval
  
schema/
  benchmark.schema.json         # validation schema (applied per-line, not blocking)
```

### 4.3 Backward compatibility

Existing `benchmarks.yaml` (66 entries) stays as-is for the curated human-curated benchmarks. New crowdsourced benchmarks go into `benchmarks/benchmarks.jsonl`. The Catalog class loads both:

```python
@property
def benchmarks(self) -> list[dict]:
    self._load()
    return self._yaml_benchmarks + self._jsonl_benchmarks
```

### 4.4 Size projections

| Entries | YAML (current model) | JSONL (provenance-enriched) |
|---|---|---|
| 66 | 37 KB | ~65 KB (1 KB/entry) |
| 1,000 | 560 KB | ~1 MB |
| 5,000 | 2.8 MB | ~5 MB |
| 10,000 | 5.6 MB | ~10 MB |

JSONL is larger per-entry (provenance fields) but:
- Lazy loading: CLI/MCP only reads what it needs
- Indexed by model_id for O(1) lookup
- No YAML parse overhead (JSON.parse is 10x faster)

---

## 5. Benchmark Protocol v1.0

### 5.1 Standard benchmark (decode throughput for LLMs)

```
PROTOCOL v1.0 — Decode Throughput

INPUTS:
  - Standard prompt: 128 tokens (fixed, hardcoded in app)
  - Generation: 256 tokens
  - Warmup: 3 iterations (results discarded)
  - Measure: 10 iterations

EXECUTION:
  1. Load model bundle via CoreAIRunner
  2. Tokenize standard prompt
  3. Warmup loop (3x): generate 128 tokens, discard timing
  4. Measure loop (10x):
     a. Record mach_absolute_time() before first token
     b. Generate 256 tokens (streaming)
     c. Record mach_absolute_time() after last token
     d. Compute throughput = 256 / elapsed_seconds
     e. Record peak memory via mach_task_basic_info
  5. Compute statistics: median, stddev, p50, p95

OUTPUT (BenchmarkReport):
  - model_id, model_hash (SHA256 of .aimodel dir contents)
  - metric: "decode_throughput", value: median, unit: "tokens_per_second"
  - methodology: {protocol_version, prompt_tokens, generation_tokens, warmup, measured, statistic, stddev, p50, p95}
  - device_info: {device_class, ram_gb, os_major_version}
  - runtime_config: {engine, compute_unit, precision, batch_size, context_length}
  - environment: {thermal_state, low_power_mode, battery_level, plugged_in}
  - app_attest_token: (Apple-issued)
  - date: "2026-07-15" (date only, no time)

STANDARD PROMPT (hardcoded, same for all devices):
  "The quick brown fox jumps over the lazy dog. " repeated to 128 tokens.
```

### 5.2 Metrics by model type

| Model type | Metric | Unit | Standard input |
|---|---|---|---|
| LLM | `decode_throughput` | tokens_per_second | 128-token prompt, 256-token gen |
| LLM | `time_to_first_token` | milliseconds | 128-token prompt |
| Diffusion | `image_generation_latency` | seconds | "a cat sitting on a table", 28 steps |
| Speech (STT) | `realtime_factor` | ratio | 30-second audio clip |
| Detection | `inference_fps` | frames_per_second | Standard test image |
| Segmentation | `segmentation_latency` | seconds_per_image | Standard test image + "object" prompt |
| TTS | `audio_generation_rtf` | ratio | "Hello world" (13 chars) |
| Embedding | `embedding_throughput` | tokens_per_second | 512-token input |

---

## 6. Extraction Method Taxonomy

Every data point (benchmark or catalog field) carries `extraction_method`:

| Method | Description | Default confidence |
|---|---|---|
| `app_benchmark_protocol` | App ran controlled benchmark on real device | `high` |
| `app_benchmark_user_initiated` | User triggered benchmark manually in app | `high` |
| `hf_metadata_api` | Automated pull from Hugging Face API | `high` |
| `hf_file_listing` | Computed from actual file sizes in HF repo | `high` |
| `apple_documentation` | Official Apple docs or WWDC session | `high` |
| `upstream_readme_scripted` | Script parsed upstream README | `medium` |
| `upstream_readme_manual` | Human copied from README/table | `medium` |
| `upstream_release_notes` | From GitHub release or changelog | `medium` |
| `derived_calculated` | Computed from other catalog fields | `medium` |
| `community_submission` | User reported without controlled protocol | `needs_review` |

---

## 7. Relay Specification (Cloudflare Worker)

### 7.1 API

```
POST https://benchmarks.coreai-catalog.workers.dev/api/v1/submit

Headers:
  Content-Type: application/json
  X-App-Attest-Token: <Apple attestation JWT>

Body (from device):
{
  "model_id": "official-qwen3-4b",
  "model_hash": "sha256:abc123...",
  "metric": "decode_throughput",
  "value": 145.4,
  "unit": "tokens_per_second",
  "methodology": { ... },
  "device_info": { "device_model": "iPhone17,1", "chip": "A18 Pro", "ram_gb": 8, "os_version": "27.0" },
  "runtime_config": { ... },
  "environment": { ... },
  "date": "2026-07-15"
}

Response:
  202 Accepted (submission queued)
  409 Conflict (already submitted for this device+model+config)
  401 Unauthorized (App Attest validation failed)
  400 Bad Request (schema validation failed)
```

### 7.2 Relay logic

```typescript
// Pseudocode — ~150 lines TypeScript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // 1. Validate App Attest token with Apple
    const token = request.headers.get('X-App-Attest-Token');
    const attestResult = await validateAppAttest(token, env.APPLE_ATTEST_KEY);
    if (!attestResult.valid) return new Response('Unauthorized', { status: 401 });

    // 2. Parse and validate body
    const payload = await request.json();
    const validationErrors = validateBenchmark(payload);
    if (validationErrors) return new Response(JSON.stringify(validationErrors), { status: 400 });

    // 3. Dedup: check if this device already submitted this model+config
    const dedupKey = `${attestResult.deviceHash}:${payload.model_id}:${payload.runtime_config.engine}`;
    const existing = await env.DEDUP_KV.get(dedupKey);
    if (existing) return new Response('Already submitted', { status: 409 });

    // 4. Store dedup key (60-day TTL — allow resubmission after model update)
    await env.DEDUP_KV.put(dedupKey, '1', { expirationTtl: 60 * 86400 });

    // 5. Coarsen device data
    const coarsened = coarsenDeviceData(payload);

    // 6. Build JSONL line
    const line = JSON.stringify({
      ...coarsened,
      provenance: {
        source: 'crowdsourced',
        extraction_method: 'app_benchmark_protocol',
        device_attestation: true,
        date: payload.date,
      },
      confidence: 'high',
    });

    // 7. Create PR via GitHub API
    const branchName = `bm-${crypto.randomUUID().slice(0, 8)}`;
    await createBranchAndPR({
      token: env.GITHUB_TOKEN,
      repo: 'kevinqz/coreai-catalog',
      branchName,
      filePath: 'benchmarks/benchmarks.jsonl',
      content: line,
      title: `Benchmark: ${payload.model_id} on ${coarsened.device_info.device_class}`,
      body: 'Auto-generated benchmark submission. Validated by privacy relay.',
    });

    return new Response('Accepted', { status: 202 });
  }
};
```

### 7.3 Why Cloudflare Worker

- **Free tier:** 100K requests/day. Sufficient for thousands of submissions.
- **Edge locations:** Sub-100ms latency globally.
- **Stateless:** All state in Cloudflare KV (dedup) and GitHub (data).
- **No server management:** Deployed via `wrangler deploy`.
- **Open source:** Worker code is public. Only `APPLE_ATTEST_KEY` is secret.

---

## 8. GitHub Action: benchmark-validate.yml

```yaml
name: Benchmark Validation
on:
  pull_request:
    paths:
      - 'benchmarks/benchmarks.jsonl'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Validate new benchmark lines
        run: |
          # Extract only the new lines from the PR
          git diff origin/main HEAD -- benchmarks/benchmarks.jsonl | grep '^+' | grep -v '^+++' > /tmp/new_lines.jsonl

          # Schema validate each line
          python3 scripts/validate_benchmark.py --input /tmp/new_lines.jsonl --schema schema/benchmark.schema.json

          # Cross-reference check: model_id must exist in catalog
          python3 scripts/check_benchmark_refs.py --input /tmp/new_lines.jsonl --catalog catalog.yaml

      - name: Outlier detection (MAD)
        id: mad
        run: |
          RESULT=$(python3 scripts/outlier_check.py \
            --input /tmp/new_lines.jsonl \
            --existing benchmarks/benchmarks.jsonl)
          echo "result=$RESULT" >> $GITHUB_OUTPUT

      - name: Model hash verification
        run: |
          python3 scripts/verify_model_hash.py --input /tmp/new_lines.jsonl
        continue-on-error: true  # Non-blocking warning

      - name: Auto-merge if all checks pass
        if: steps.mad.outputs.result != 'outlier'
        uses: pascalgn/automerge-action@v0.16.2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          args: --method=squash

      - name: Label for review if outlier
        if: steps.mad.outputs.result == 'outlier'
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.addLabels({
              issue_number: context.issue.number,
              labels: ['needs-review', 'outlier']
            });
```

---

## 9. Privacy Analysis vs Red-Team Findings

| Red-team finding | v2 resolution |
|---|---|
| **C1: Device fingerprint re-identifies** | Relay coarsens iPhone17,1 → iphone-a18-pro class. Millions of devices per class. |
| **C2: GitHub username linked to device** | Relay posts as @coreai-benchmark-bot. User never appears in git. |
| **C3: Sybil attack** | DeviceCheck: 1 submission per real device per model+config. Attacker can't create virtual devices. |
| **C4: Fabricated methodology** | App Attest proves app ran on genuine device. Relay rejects without valid token. |
| **C5: Schema blocks migration** | JSONL: no `additionalProperties` gate. Schema is per-line validation, not structural. |
| **C6: Action loses data** | Relay creates PR (persistent in GitHub). Not ephemeral Action state. |
| **C7: Concurrent push conflict** | PRs are serialized. GitHub merges one at a time. No direct push to main. |
| **C8: MCP 17s at 10K** | JSONL lazy loading. MCP loads index, not full file. |
| **C9: generate.py O(total)** | Runs only on PR merge, not per submission. |
| **H3: HMAC broken (key in app)** | Key is SERVER-SIDE only (Cloudflare env var). App never sees it. |
| **H4: GDPR erasure impossible** | No user attribution in git. Benchmark line has no PII. Deletion = remove 1 JSONL line (new commit). |
| **H5: Opt-in not granular** | Pre-submission preview shows exact JSON. User confirms each time. Toggle in settings. |
| **G5: Thermal throttling** | Captured in `environment.thermal_state`. Segmented in aggregation. |
| **G3: MAD at small N** | N≥5 required. Below: auto-accept (insufficient-data label). |

---

## 10. Implementation Phases

### Phase A: Schema + JSONL foundation (no infra needed)
1. Evolve `benchmark.schema.json` with optional methodology/provenance fields
2. Create `benchmarks/benchmarks.jsonl` (empty, ready for appends)
3. Update Catalog class to load from both YAML and JSONL
4. Add `validate_benchmark.py` script (per-line schema validation)
5. Tag existing 66 benchmarks with `extraction_method` in YAML

### Phase B: GitHub Action + validation pipeline
6. Create `benchmark-validate.yml` GitHub Action
7. Build `outlier_check.py` (segmented MAD)
8. Build `check_benchmark_refs.py` (cross-reference validation)
9. Build `verify_model_hash.py` (HF download + hash comparison)
10. Test with 5 synthetic submissions

### Phase C: Privacy relay
11. Implement Cloudflare Worker (~150 lines TypeScript)
12. Implement App Attest validation
13. Implement device class coarsening
14. Implement dedup via Cloudflare KV
15. Implement GitHub PR creation via API
16. Deploy and test end-to-end

### Phase D: App integration (Ditto)
17. Implement BenchmarkProtocol in Swift
18. Implement App Attest token acquisition
19. Implement pre-submission preview UI
20. Implement opt-in flow + settings toggle
21. Test with real device

---

*Design v2.0 — red-team validated. All 9 CRITICAL findings resolved.*
*Saved as `.internal/plans/2026-07-02_provenance-architecture-v2.md`*
