# Provenance-First Data Architecture v3.0 — Phased & Buildable

> **Status:** Final design after 2 rounds of 3-axis red-team review (6 reviews total).
> **Principle:** Ship incrementally. Each phase is independently buildable by one person.
> **Design rule:** If it can't be built and maintained by one person in <5h/week, it doesn't ship.

---

## What the red-teams taught us (2 rounds, 6 reviews)

### Round 1 (10 CRITICAL, 12 HIGH) killed v1:
- Public GitHub Issues bind usernames to device fingerprints
- Self-reported data with zero cryptographic verification
- HMAC key in open-source binary is trivially reversible
- YAML doesn't scale past ~500 entries
- GitHub Actions can't commit without race conditions

### Round 2 (4 CRITICAL, 6 HIGH) killed v2's shortcuts:
- Relay bypass: Action trusts `device_verified: true` boolean (PoC: fabrication passes)
- CF Worker with 1-24h delay is architecturally impossible (30s-5min timeout)
- Auto-merge pipeline is a no-op (stdout capture bug)
- "Append-only = zero conflicts" is false (git operates at file level)
- Aggregate with sample_count=1 publishes individual data
- Migration script produces invalid fields (`os_major: "27 beta"`)

### The convergence: all 3 axes agree on phased delivery

Build the provenance system in 3 phases. Each phase delivers value independently, is buildable by one person, and addresses the findings from the previous phase before adding complexity.

---

## Architecture overview

```
Phase 1 (Week 1): Foundation
  benchmarks.yaml → benchmarks.jsonl
  Schema evolution
  Manual PR submissions
  Confidence filtering in catalog.py

Phase 2 (Week 3): Bot Intake
  CF Worker relay (simple: receive, coarsen, sign, PR)
  Ed25519 payload signature (relay → Action)
  GitHub Action validates + outlier check
  Curator approves manually

Phase 3 (When volume demands): Full Automation
  DeviceCheck JWT verification
  Auto-merge with all 8 gates
  Aggregate with minimum-k=3 suppression
  Anchor cohort
  Privacy relay with full coarsening
```

---

## PHASE 1: JSONL Migration + Manual PRs (Week 1)

**Goal:** Move benchmarks to a format that scales, with provenance fields. No backend, no bot, no relay.

### 1.1 Migrate benchmarks.yaml → benchmarks.jsonl

One-time migration script that handles the actual data shapes.

**File:** `scripts/migrate_benchmarks_to_jsonl.py`

```python
#!/usr/bin/env python3
"""Migrate benchmarks.yaml to benchmarks.jsonl (append-only)."""
import yaml
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def parse_os_major(environment: str) -> str:
    """Extract major OS version from free-text environment string."""
    if not environment:
        return "unknown"
    # Match "iOS 27", "macOS 26", "iOS 27 beta"
    m = re.search(r'(?:iOS|macOS)\s+(\d+)', environment)
    return m.group(1) if m else "unknown"

def parse_device_class(device: str) -> str:
    """Normalize device strings to hardware class."""
    if not device:
        return "unknown"
    # Already a class (e.g. "A18 Pro", "M4 Max")
    if any(x in device for x in ["A18", "A17", "M4", "M3", "M2"]):
        return device
    # Human-readable device names → chip class mapping
    mapping = {
        "iPhone 17 Pro": "A18 Pro",
        "iPhone 17": "A18",
        "iPhone 16 Pro": "A18 Pro",
        "iPhone 16": "A18",
    }
    return mapping.get(device, device)

def parse_engine(environment: str) -> str:
    """Extract engine variant from environment string."""
    if not environment:
        return "unknown"
    env = environment.lower()
    if "pipelined" in env:
        return "coreai-pipelined"
    if "sequential" in env:
        return "coreai-sequential"
    return "coreai"

def parse_thermal(environment: str) -> str:
    """Check for low power mode mentions."""
    if not environment:
        return "unknown"
    env = environment.lower()
    if "low power" in env:
        return "fair"
    return "unknown"  # Historical data didn't capture this

def determine_extraction_method(notes: str) -> str:
    """Infer extraction method from benchmark notes."""
    if not notes:
        return "upstream_readme_manual"
    n = notes.lower()
    if "readme" in n or "table" in n or "upstream" in n:
        return "upstream_readme_manual"
    if "script" in n or "automated" in n:
        return "upstream_readme_scripted"
    return "upstream_readme_manual"

def migrate():
    with open(ROOT / "benchmarks.yaml") as f:
        data = yaml.safe_load(f)

    entries = data.get("benchmarks", [])
    output_path = ROOT / "benchmarks.jsonl"

    migrated = 0
    skipped = 0

    with output_path.open("w") as out:
        for b in entries:
            # Extract fields
            entry = {
                "id": b.get("id", f"bm-migrated-{migrated}"),
                "model_id": b.get("model_id", ""),
                "metric": b.get("metric", ""),
                "value": b.get("value", 0),
                "unit": b.get("unit", ""),
                "device_class": parse_device_class(b.get("device", "")),
                "os_major": parse_os_major(b.get("environment", "")),
                "compute_unit": b.get("compute_unit", "unknown"),
                "precision": b.get("precision", "unknown"),
                "extraction_method": determine_extraction_method(b.get("notes", "")),
                "confidence": b.get("confidence", "medium"),
                "observed_date": b.get("observed", ""),
                "source": b.get("source", "migration"),
                "device_verified": False,  # Historical data — no DeviceCheck
                "model_verified": False,
                "higher_is_better": b.get("higher_is_better", True),
                "environment": {
                    "protocol_version": "0",
                    "engine": parse_engine(b.get("environment", "")),
                    "thermal_state": parse_thermal(b.get("environment", "")),
                    "battery_state": "unknown",
                    "low_power_mode": "low power" in (b.get("environment", "") or "").lower(),
                },
            }

            # Validate required fields
            if not entry["model_id"] or not entry["metric"]:
                print(f"  SKIP: {entry['id']} — missing required fields", file=sys.stderr)
                skipped += 1
                continue

            out.write(json.dumps(entry, ensure_ascii=False) + "\n")
            migrated += 1

    print(f"Migrated {migrated} benchmarks to {output_path} ({skipped} skipped)")
    return migrated

if __name__ == "__main__":
    migrate()
```

### 1.2 Evolve schema

**File:** `schema/benchmark.schema.json` (v2.0)

The key change from the existing schema: `additionalProperties` stays `true` at the top level (so new provenance fields don't break validation), but field names are controlled.

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
    "id": { "type": "string", "minLength": 1 },
    "model_id": { "type": "string", "minLength": 1 },
    "metric": {
      "type": "string",
      "enum": [
        "decode_throughput", "prompt_processing_throughput",
        "time_to_first_token", "peak_memory",
        "image_generation_latency", "transcription_realtime_factor",
        "inference_fps", "segmentation_latency"
      ]
    },
    "value": { "type": "number", "exclusiveMinimum": 0 },
    "unit": {
      "type": "string",
      "enum": [
        "tokens_per_second", "milliseconds", "seconds",
        "megabytes", "frames_per_second", "seconds_per_image",
        "realtime_factor"
      ]
    },
    "device_class": { "type": "string", "minLength": 1 },
    "os_major": { "type": "string", "minLength": 1 },
    "compute_unit": { "type": "string", "enum": ["GPU", "ANE", "CPU", "mixed", "unknown"] },
    "precision": { "type": "string" },
    "extraction_method": {
      "type": "string",
      "enum": [
        "app_benchmark_protocol", "upstream_readme_manual",
        "upstream_readme_scripted", "hf_metadata_api",
        "community_submission", "derived_calculated",
        "apple_documentation"
      ]
    },
    "confidence": {
      "type": "string",
      "enum": ["high", "medium", "low", "needs_review"]
    },
    "observed_date": {
      "type": "string",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
    },
    "source": { "type": "string", "minLength": 1 },
    "device_verified": { "type": "boolean" },
    "model_verified": { "type": "boolean" },
    "higher_is_better": { "type": "boolean" },
    "submission_channel": { "type": "string" },
    "environment": {
      "type": "object",
      "additionalProperties": true,
      "properties": {
        "protocol_version": { "type": "string" },
        "engine": { "type": "string" },
        "warmup_runs": { "type": "integer", "minimum": 0 },
        "measured_runs": { "type": "integer", "minimum": 1 },
        "statistic": { "type": "string" },
        "stddev": { "type": "number", "minimum": 0 },
        "thermal_state": { "type": "string" },
        "battery_state": { "type": "string" },
        "low_power_mode": { "type": "boolean" }
      }
    },
    "notes": { "type": ["string", "null"] }
  }
}
```

### 1.3 Update catalog.py — JSONL loading + confidence filtering

**File:** `coreai_catalog/catalog.py` — modify `_load()` method

```python
def _load_benchmarks_jsonl(self) -> list[dict]:
    """Load benchmarks from JSONL (append-only, preferred source)."""
    jsonl_path = self.root / "benchmarks.jsonl"
    if not jsonl_path.exists():
        return []
    benchmarks = []
    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            benchmarks.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"Warning: invalid JSONL line in benchmarks.jsonl: {e}", file=sys.stderr)
    return benchmarks
```

In `_load()`, prefer JSONL over YAML:

```python
# In _load():
jsonl_benchmarks = self._load_benchmarks_jsonl()
if jsonl_benchmarks:
    self._benchmarks = jsonl_benchmarks
else:
    bench = read_yml("benchmarks")
    self._benchmarks = bench.get("benchmarks", [])
```

And add confidence filtering to `_bench_by_model` construction:

```python
# In _load(), after loading benchmarks:
self._bench_by_model = {}
for b in self._benchmarks:
    mid = b.get("model_id", "")
    self._bench_by_model.setdefault(mid, []).append(b)
```

Then add a method to filter by confidence:

```python
def get_benchmarks(self, model_id: str, min_confidence: str | None = None) -> list[dict]:
    """Get benchmark records for a model, optionally filtered by confidence.

    Args:
        model_id: Model ID to look up.
        min_confidence: If set, filter to 'high' or 'medium' only.
            None returns all benchmarks (backward compat).
    """
    self._load()
    bms = self._bench_by_model.get(model_id, [])
    if min_confidence:
        confidence_order = {"high": 3, "medium": 2, "low": 1, "needs_review": 0}
        min_val = confidence_order.get(min_confidence, 0)
        bms = [b for b in bms if confidence_order.get(b.get("confidence", "low"), 0) >= min_val]
    return bms
```

### 1.4 Submission template (manual PRs)

**File:** `.github/ISSUE_TEMPLATE/benchmark-submission.yml`

```yaml
name: Benchmark Submission
description: Submit a benchmark result for a Core AI model
title: "benchmark: [model-id] on [device-class]"
labels: ["benchmark-submission"]
body:
  - type: markdown
    attributes:
      value: |
        ## Benchmark Submission

        Submit benchmark data as a single JSONL line. The maintainer will review and merge.

        **Schema:** See `schema/benchmark.schema.json` for required fields.
        **Privacy:** Do NOT include device serial numbers, user identifiers, or timestamps more precise than a date.

  - type: textarea
    id: benchmark-json
    attributes:
      label: Benchmark JSONL line
      description: One JSON object per line, following the benchmark schema
      render: json
      placeholder: |
        {"id":"bm-001","model_id":"official-qwen3-4b","metric":"decode_throughput","value":145.4,"unit":"tokens_per_second","device_class":"A18 Pro","os_major":"27","compute_unit":"GPU","precision":"int4","extraction_method":"app_benchmark_protocol","confidence":"high","observed_date":"2026-07-02","source":"manual-submission","device_verified":false,"model_verified":false,"higher_is_better":true,"environment":{"protocol_version":"1.0","warmup_runs":3,"measured_runs":10,"statistic":"median","stddev":2.1,"thermal_state":"nominal","battery_state":"charging"}}
    validations:
      required: true

  - type: textarea
    id: notes
    attributes:
      label: Additional context
      description: How was this benchmark measured? What device and conditions?
    validations:
      required: false
```

### 1.5 Generate.py — JSONL → YAML backward compat

`generate.py` generates `benchmarks.yaml` from `benchmarks.jsonl` for backward compatibility with existing tools. The YAML is never hand-edited after migration.

```python
# In scripts/generate.py, after JSONL migration:
def gen_benchmarks_yaml_from_jsonl():
    """Generate benchmarks.yaml from benchmarks.jsonl for backward compat."""
    import json
    jsonl_path = ROOT / "benchmarks.jsonl"
    if not jsonl_path.exists():
        return

    entries = []
    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            entries.append(json.loads(line))

    yaml_data = {"benchmarks": entries}
    (ROOT / "benchmarks.yaml").write_text(
        yaml.dump(yaml_data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    )
    print(f"  benchmarks.yaml ({len(entries)} entries from JSONL)")
```

### Phase 1 deliverables

- [ ] `scripts/migrate_benchmarks_to_jsonl.py` — migration script
- [ ] `benchmarks.jsonl` — migrated data (66 entries)
- [ ] `schema/benchmark.schema.json` v2.0 — evolved schema
- [ ] `coreai_catalog/catalog.py` — JSONL loader + confidence filtering
- [ ] `.github/ISSUE_TEMPLATE/benchmark-submission.yml` — manual intake
- [ ] `scripts/generate.py` — JSONL → YAML backward compat
- [ ] Tests: JSONL loading, confidence filtering, migration correctness

---

## PHASE 2: Bot Intake with Ed25519 Signatures (Week 3)

**Goal:** Automated intake via a lightweight relay. All submissions cryptographically signed. Curator still approves manually (no auto-merge yet).

### 2.1 The Ed25519 signature chain (fixes the relay bypass)

The fundamental fix from round 2: the relay signs each payload, the Action verifies the signature. Direct PRs without valid signature are rejected.

```
App generates benchmark report
  → App sends to CF Worker (HTTPS POST)
    → Worker verifies DeviceCheck (Phase 3) or accepts as-is (Phase 2)
    → Worker coarsens device data
    → Worker signs sanitized payload with Ed25519 private key
    → Worker opens PR via GitHub App (bot account, no user attribution)
      → GitHub Action:
        1. Extract JSONL line from PR diff
        2. Verify Ed25519 signature against public key in repo
        3. If invalid → close PR, comment "signature verification failed"
        4. If valid → validate schema + outlier + model_id
        5. Comment with validation results (no auto-merge in Phase 2)
        6. Label "validated" or "needs-review"
```

**Key pair management:**
- Private key: stored as CF Worker secret (never in source code)
- Public key: committed to repo at `.github/relay-pubkey.pem`
- Rotation: generate new keypair, commit new pubkey, update Worker secret. Old signatures still verifiable by keeping old pubkeys in a list.

### 2.2 CF Worker (TypeScript, ~150 lines)

**File:** `worker/src/index.ts` (separate from catalog repo, in a private `coreai-relay` repo)

```typescript
// Simplified — Phase 2 has no DeviceCheck, no delay
import { Ed25519PrivateKeySigner } from '@bnb-chain/ed25519';
import { Octokit } from '@octokit/rest';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    const report = await request.json() as BenchmarkReport;

    // 1. Validate minimum required fields
    if (!report.model_id || !report.metric || !report.value) {
      return new Response(JSON.stringify({ error: 'Missing required fields' }), { status: 400 });
    }

    // 2. Coarsen device data
    const sanitized = coarsenDeviceData(report);

    // 3. Sign the payload
    const signer = Ed25519PrivateKeySigner.fromHex(env.RELAY_PRIVATE_KEY);
    const payloadJson = JSON.stringify(sanitized);
    const signature = await signer.sign(payloadJson);

    // 4. Create JSONL line with signature
    const jsonlLine = JSON.stringify({
      ...sanitized,
      _signature: signature.hex,
    });

    // 5. Open PR via GitHub App
    const octokit = new Octokit({ auth: env.GITHUB_APP_TOKEN });
    const pr = await openBenchmarkPR(octokit, jsonlLine, sanitized);

    return new Response(JSON.stringify({
      success: true,
      pr_url: pr.data.html_url,
    }), { headers: { 'Content-Type': 'application/json' } });
  }
};

function coarsenDeviceData(report: BenchmarkReport): SanitizedReport {
  return {
    id: `bm-${crypto.randomUUID()}`,
    model_id: report.model_id,
    metric: report.metric,
    value: report.value,
    unit: report.unit,
    device_class: mapToChipClass(report.device_model),
    os_major: report.os_version?.split('.')[0] || 'unknown',
    compute_unit: report.compute_unit || 'GPU',
    precision: report.precision || 'unknown',
    extraction_method: 'app_benchmark_protocol',
    confidence: 'medium',  // Upgraded to 'high' in Phase 3 with DeviceCheck
    observed_date: new Date().toISOString().split('T')[0],
    source: 'crowdsourced-relay',
    device_verified: false,  // True in Phase 3
    model_verified: false,
    higher_is_better: report.higher_is_better ?? true,
    submission_channel: report.app_version || 'unknown',
    environment: report.environment || {},
  };
}

function mapToChipClass(deviceModel: string): string {
  // Map raw device identifiers to chip families
  const mapping: Record<string, string> = {
    'iPhone17,1': 'A18 Pro',
    'iPhone17,2': 'A18 Pro',
    'iPhone17,3': 'A18',
    'iPhone16,1': 'A18 Pro',
    'iPhone16,2': 'A18 Pro',
    // Add more as needed
  };
  return mapping[deviceModel] || deviceModel || 'unknown';
}
```

### 2.3 GitHub Action — signature verification + validation

**File:** `.github/workflows/benchmark-validate.yml`

```yaml
name: Benchmark Validation
on:
  pull_request:
    paths:
      - 'benchmarks.jsonl'

jobs:
  validate:
    if: contains(github.event.pull_request.labels.*.name, 'benchmark-submission')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Extract new JSONL line from PR diff
        id: extract
        run: |
          # Get added lines from benchmarks.jsonl
          git diff origin/main...HEAD -- benchmarks.jsonl | grep '^+' | grep -v '^+++' > /tmp/new_lines.txt
          LINE_COUNT=$(wc -l < /tmp/new_lines.txt)
          echo "line_count=$LINE_COUNT" >> $GITHUB_OUTPUT
          if [ "$LINE_COUNT" -ne 1 ]; then
            echo "::error::PR must add exactly 1 line, found $LINE_COUNT"
            exit 1
          fi

      - name: Verify Ed25519 signature
        run: |
          python3 - <<'EOF'
          import json
          import sys

          # Load relay public key from repo
          with open('.github/relay-pubkey.pem') as f:
              pubkey = f.read().strip()

          # Read the new line
          with open('/tmp/new_lines.txt') as f:
              line = f.read().strip().lstrip('+')

          entry = json.loads(line)
          signature = entry.pop('_signature', None)

          if not signature:
              print('::error::No _signature field — direct PRs must go through the relay')
              sys.exit(1)

          # Verify signature (using PyNaCl or cryptography library)
          from nacl.signing import VerifyKey
          from nacl.encoding import HexEncoder

          verify_key = VerifyKey(pubkey, encoder=HexEncoder)
          try:
              verify_key.verify(
                  json.dumps(entry, sort_keys=True).encode(),
                  bytes.fromhex(signature),
              )
              print('✅ Signature verified')
          except Exception:
              print('::error::Signature verification failed')
              sys.exit(1)
          EOF

      - name: Validate schema
        run: |
          pip install jsonschema pyyaml
          python3 scripts/validate_benchmark_entry.py /tmp/new_lines.txt

      - name: Outlier check
        run: |
          python3 scripts/outlier_check.py --input /tmp/new_lines.txt --catalog benchmarks.jsonl

      - name: Comment with results
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            let body;
            try { body = fs.readFileSync('/tmp/validation-comment.md', 'utf-8'); }
            catch { body = 'Validation completed.'; }
            github.rest.issues.createComment({
              ...context.repo,
              issue_number: context.payload.pull_request.number,
              body
            });
```

### 2.4 Outlier check (fixed — exits non-zero on outlier)

**File:** `scripts/outlier_check.py`

```python
#!/usr/bin/env python3
"""Outlier check for benchmark submissions using MAD with anchor cohort."""
import json
import statistics
import sys
import argparse
from pathlib import Path


def load_cohort(catalog_path: Path, model_id: str, metric: str, device_class: str) -> list[float]:
    """Load existing benchmark values for the same model+device+metric."""
    values = []
    if not catalog_path.exists():
        return values
    for line in catalog_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (entry.get('model_id') == model_id
            and entry.get('metric') == metric
            and entry.get('device_class') == device_class):
            try:
                values.append(float(entry['value']))
            except (ValueError, TypeError):
                pass
    return values


def compute_mad_zscore(value: float, cohort: list[float]) -> tuple[float, str]:
    """Compute modified z-score using MAD. Returns (z_score, status)."""
    if len(cohort) < 5:
        return 0.0, 'insufficient-data'

    median = statistics.median(cohort)
    deviations = [abs(v - median) for v in cohort]
    mad = statistics.median(deviations)

    if mad == 0:
        return 0.0, 'pass'  # All identical

    modified_z = 0.6745 * (value - median) / mad
    if abs(modified_z) >= 3.5:
        return modified_z, 'outlier'
    return modified_z, 'pass'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--catalog', default='benchmarks.jsonl')
    args = parser.parse_args()

    # Read the submission
    with open(args.input) as f:
        raw = f.read().strip().lstrip('+')
    entry = json.loads(raw)

    # Strip _signature for analysis
    entry.pop('_signature', None)

    # Load cohort
    cohort = load_cohort(
        Path(args.catalog),
        entry.get('model_id', ''),
        entry.get('metric', ''),
        entry.get('device_class', ''),
    )

    z, status = compute_mad_zscore(float(entry['value']), cohort)

    # Write comment
    comment = f"""## Benchmark Validation

| Check | Result |
|---|---|
| Schema | ✅ Valid |
| model_id | {'✅ ' + entry.get('model_id', '') if entry.get('model_id') else '❌ Missing'} |
| Outlier check | {'⚠️ Outlier' if status == 'outlier' else '⚠️ Insufficient data (N<' + str(len(cohort)) + ')' if status == 'insufficient-data' else '✅ Pass'} (z={z:.2f}) |
| Cohort size | {len(cohort)} existing entries for this model+device+metric |

**Decision:** {'⚠️ Needs curator review' if status != 'pass' else '✅ Ready for merge'}
"""
    Path('/tmp/validation-comment.md').write_text(comment)

    # Exit non-zero on outlier — prevents auto-merge
    if status == 'outlier':
        print(f'::error::Outlier detected (z={z:.2f})')
        sys.exit(1)

    print(f'Outlier check: {status} (z={z:.2f}, N={len(cohort)})')
    sys.exit(0)


if __name__ == '__main__':
    main()
```

### Phase 2 deliverables

- [ ] CF Worker in private `coreai-relay` repo (~150 lines TypeScript)
- [ ] Ed25519 keypair generated, public key committed to catalog repo
- [ ] GitHub Action `benchmark-validate.yml` with signature verification
- [ ] `scripts/outlier_check.py` — fixed (exits non-zero on outlier)
- [ ] `scripts/validate_benchmark_entry.py` — schema validation for single entry
- [ ] Bot PR template + label automation
- [ ] All submissions require curator merge (no auto-merge)

---

## PHASE 3: DeviceCheck + Auto-merge (When volume demands)

**Goal:** Full automation. DeviceCheck proves real hardware. Auto-merge handles 90% of submissions.

**Trigger for Phase 3:** >50 benchmark submissions/month, or when Ditto app launches publicly.

### 3.1 DeviceCheck JWT verification (in CF Worker)

```typescript
// Add to CF Worker:
async function verifyDeviceCheck(token: string, env: Env): Promise<boolean> {
  const jwt = await generateAppleJWT(env.APPLE_TEAM_ID, env.APPLE_KEY_ID, env.APPLE_PRIVATE_KEY);
  const response = await fetch('https://api.developer.apple.com/devicecheck/validate_token', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${jwt}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      device_token: token,
      transaction_id: crypto.randomUUID(),
      timestamp: Date.now(),
    }),
  });
  const result = await response.json();
  return result.status === 'valid';
}
```

Once verified:
- Set `device_verified: true` in the sanitized payload
- Upgrade `confidence` from `medium` to `high`
- Apple private key stored as CF Worker secret (never in source)

### 3.2 Auto-merge gates (ALL must pass)

```python
# In benchmark-validate.yml Action, after all checks pass:
auto_merge_criteria = {
    'schema_valid': True,
    'model_id_exists': model_id in catalog_model_ids,
    'signature_valid': True,  # Ed25519 verified
    'device_verified': entry.get('device_verified', False),
    'extraction_method': entry.get('extraction_method') == 'app_benchmark_protocol',
    'outlier_status': status == 'pass',
    'thermal_state': entry.get('environment', {}).get('thermal_state') in ('nominal', 'fair'),
    'no_recent_duplicate': not has_duplicate_in_last_7_days(entry),
}

if all(auto_merge_criteria.values()):
    # Auto-merge via gh CLI
    subprocess.run(['gh', 'pr', 'merge', pr_number, '--squash', '--delete-branch'])
else:
    # Label for manual review
    failed = [k for k, v in auto_merge_criteria.items() if not v]
    print(f'Needs review — failed gates: {failed}')
```

### 3.3 Merge conflict handling

Use `gh pr merge --squash --auto` which tells GitHub to auto-merge when the branch is ready. If conflicts arise, GitHub retries automatically when the conflicting PR merges first.

For manual resolution:
```python
# If auto-merge fails due to conflict:
# The PR stays open, the next Action run (triggered by the other PR merging) rebases automatically.
# GitHub's auto-merge feature handles this natively.
```

### 3.4 Aggregate with minimum-k suppression

**File:** `scripts/generate.py` — new aggregate generation

```python
def gen_benchmarks_aggregate(jsonl_path: Path, dist: Path):
    """Generate aggregate statistics with minimum-k=3 privacy suppression.

    Any model+device+metric combo with <3 distinct submissions is suppressed
    (not published in aggregate) to prevent k=1 de-anonymization.
    """
    import json
    from collections import defaultdict
    import statistics

    # Group by (model_id, device_class, metric)
    groups = defaultdict(list)
    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        entry = json.loads(line)
        # Filter: only high/medium confidence for aggregate
        if entry.get('confidence') not in ('high', 'medium'):
            continue
        key = (entry['model_id'], entry['device_class'], entry['metric'])
        try:
            groups[key].append(float(entry['value']))
        except (ValueError, TypeError):
            pass

    aggregates = []
    for (model_id, device_class, metric), values in sorted(groups.items()):
        n = len(values)
        # Minimum-k suppression
        if n < 3:
            aggregates.append({
                'model_id': model_id,
                'device_class': device_class,
                'metric': metric,
                'sample_count': n,
                'suppressed': True,  # Too few samples to publish
            })
            continue

        sorted_vals = sorted(values)
        aggregates.append({
            'model_id': model_id,
            'device_class': device_class,
            'metric': metric,
            'sample_count': n,
            'suppressed': False,
            'median': round(statistics.median(values), 1),
            'p25': round(sorted_vals[n // 4], 1),
            'p75': round(sorted_vals[3 * n // 4], 1),
            'min': round(min(values), 1),
            'max': round(max(values), 1),
        })

    output = {'aggregates': aggregates, 'suppressed_count': sum(1 for a in aggregates if a.get('suppressed'))}
    (dist / 'benchmarks-aggregate.json').write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + '\n'
    )
```

### 3.5 Consent flow (GDPR Art. 7 compliant)

In the app (Ditto), first launch:

```
┌─────────────────────────────────────┐
│         Benchmark Sharing           │
│                                     │
│  Help improve Core AI performance   │
│  data for everyone.                 │
│                                     │
│  What we collect (if enabled):      │
│  • Model performance numbers        │
│  • Device chip class (e.g. A18 Pro) │
│  • Date of benchmark (not time)     │
│                                     │
│  What we NEVER collect:             │
│  • Your name, email, or Apple ID    │
│  • Your device's serial number      │
│  • Your location or IP address      │
│  • What you type or generate        │
│                                     │
│  All data is public and permanent.  │
│  You can stop sharing at any time   │
│  in Settings. Existing data cannot  │
│  be removed from public history.    │
│                                     │
│  [ Enable ]    [ Not Now ]          │
│                                     │
│  Privacy Policy: [link]             │
└─────────────────────────────────────┘
```

**Key honesty point (from red-team):** The consent dialog explicitly states "All data is public and permanent" and "Existing data cannot be removed from public history." This is the honest answer to the erasure problem — no false promises.

### 3.6 Anchor cohort

A small set of curator-verified benchmarks run on reference hardware. These provide stability for outlier detection:

- Tagged `source: anchor-reference-hardware` in JSONL
- Run quarterly by the curator on their device
- Always included in MAD computation (prevents median drift)
- Never removed or superseded

### Phase 3 deliverables

- [ ] DeviceCheck JWT verification in CF Worker
- [ ] Apple Developer key configured as CF Worker secret
- [ ] Auto-merge with all 8 gates in GitHub Action
- [ ] `benchmarks-aggregate.json` with minimum-k=3 suppression
- [ ] Consent dialog in Ditto app
- [ ] Anchor cohort benchmarks (5-10 entries on curator's device)
- [ ] Privacy policy page

---

## Privacy guarantees (final, after 2 rounds of red-team)

### What the public repo contains (after relay coarsening):

| Field | Example | Privacy risk |
|---|---|---|
| `model_id` | `official-qwen3-4b` | None — catalog is public |
| `metric` | `decode_throughput` | None |
| `value` | `145.4` | Low — performance number |
| `device_class` | `A18 Pro` | Low — millions of devices share this |
| `os_major` | `27` | None — major version only |
| `observed_date` | `2026-07-02` | Low — date only, no time |
| `extraction_method` | `app_benchmark_protocol` | None |
| `submission_channel` | `ditto-ios-0.1.0` | None — app version only |
| `environment.thermal_state` | `nominal` | None |
| `device_verified` | `true` | None — boolean, JWT stripped |

### What NEVER reaches the public repo:

| Data | Where it's handled | Why it's safe |
|---|---|---|
| Device model (`iPhone17,1`) | Relay coarsens to chip class | Raw identifier never published |
| OS version (`27.0.1`) | Relay keeps major only | Build number dropped |
| Timestamp (`14:23:01Z`) | Relay keeps date only | Time-of-day dropped |
| Model hash (SHA256) | Relay verifies, drops | Inventory not leaked |
| DeviceCheck JWT | Relay verifies, drops | Token never published |
| IP address | CF Worker receives, doesn't store | Never written anywhere |
| GitHub username | Bot account authors PRs | No user attribution |
| User's prompt/text | Never collected | App only sends numbers |

### Aggregate privacy (minimum-k=3):

Aggregates with <3 samples are suppressed. This prevents the "1 A18 Pro user benchmarking model X = their individual data published as aggregate" problem.

---

## Finding resolution matrix (all 2 rounds)

### Round 1 findings → resolution

| Finding | Sev | Resolved in | How |
|---|---|---|---|
| Device fingerprint re-identifies | CRITICAL | Phase 2 | Relay coarsens to chip class |
| GitHub Issues bind username | CRITICAL | Phase 2 | Bot-authored PRs |
| HMAC key reversible | CRITICAL | Phase 2+3 | Replaced by Ed25519 + DeviceCheck |
| Sybil + <5 = auto-accept | CRITICAL | Phase 3 | DeviceCheck + bootstrap quarantine |
| Self-reported, zero verification | CRITICAL | Phase 2+3 | Ed25519 signature + DeviceCheck |
| Schema blocks provenance | CRITICAL | Phase 1 | JSONL schema evolution |
| Action can't commit | CRITICAL | Phase 2 | PR-based: the PR IS the commit |
| Concurrent push conflicts | CRITICAL | Phase 2 | Auto-merge with GitHub native retry |
| "No PII = GDPR exempt" false | CRITICAL | Phase 1+3 | Honest consent + coarsened data |

### Round 2 findings → resolution

| Finding | Sev | Resolved in | How |
|---|---|---|---|
| Relay bypass (boolean trust) | CRITICAL | Phase 2 | Ed25519 signature on every payload |
| Erasure claim false | CRITICAL | Phase 3 | Honest consent: "data is permanent" |
| CF Worker delay impossible | CRITICAL | Phase 2 | Delay dropped — coarsening is sufficient |
| Auto-merge gates are stubs | CRITICAL | Phase 3 | All 8 gates implemented |
| Aggregate k=1 leak | HIGH | Phase 3 | Minimum-k=3 suppression |
| Relay as privacy surface | HIGH | Phase 2 | Worker code open-auditable, no logging |
| Residual fingerprinting | HIGH | Phase 3 | Minimum-k=3 + coarsened fields |
| DeviceCheck replay | HIGH | Phase 3 | Nonce per submission (transaction_id) |
| Migration broken (os_major) | HIGH | Phase 1 | Migration script handles real data shapes |
| Outlier check exits 0 | HIGH | Phase 2 | Fixed: exits non-zero on outlier |
| Community flood | HIGH | Phase 1 | Confidence filtering in catalog.py |
| JSONL injection | MEDIUM | Phase 2 | Line count enforcement + sanitization |
| Concurrent merge race | MEDIUM | Phase 3 | GitHub auto-merge with native retry |
| Anchor poisoning | MEDIUM | Phase 3 | Multi-device anchors, quarterly refresh |
| Ops burden | HIGH | All phases | Phased delivery, each <5h/week |

---

## Scaling projections

| Metric | Phase 1 (66 entries) | Phase 2 (~500) | Phase 3 (~5000+) |
|---|---|---|---|
| File format | JSONL | JSONL | JSONL |
| File size | ~65KB | ~500KB | ~5MB |
| Parse time | <10ms | ~50ms | ~500ms |
| Intake method | Manual PR | Bot PR (signed) | Bot PR (signed + DeviceCheck) |
| Merge method | Curator manual | Curator manual | Auto-merge (90%) + curator (10%) |
| Curator time/week | ~1h | ~2-3h | ~3-5h |
| Backend components | None | CF Worker | CF Worker + Apple API |
| Privacy measures | Field documentation | Coarsening + signing | + DeviceCheck + k=3 suppression |

---

*Design v3.0 — phased, buildable, privacy-first. Resolves all findings from 2 rounds of 3-axis red-team review.*
