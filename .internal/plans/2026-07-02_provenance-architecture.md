# Provenance-First Data Architecture for coreai-catalog

> **Status:** Design proposal for review — not yet implemented.
> **Principle:** Every claim has a traceable provenance chain. Quality is verifiable by construction.

---

## 1. The Problem

Today's data model has provenance at the **entity level** ("this model came from the Model Zoo") but not at the **field level** ("this 145.4 tok/s came from README commit abc123, extracted manually, never reproduced"). 

Key gaps:
- **44/66 benchmarks (67%)** were manually extracted from README tables — no methodology metadata
- **0 benchmarks** record prompt length, warmup count, iteration count, or statistical measure
- **0 models** have per-field provenance — confidence is a single global value
- **34/79 models (43%)** have zero benchmarks at all
- **78/79 models** have `ipad = "unknown"` in device_support

## 2. The Design: Provenance Per-Claim

### 2.1 Schema evolution (backward-compatible)

All provenance data lives in an optional `_provenance` block on each entity. Existing data works unchanged — provenance is additive.

#### Model-level provenance

```yaml
- id: official-qwen3-4b
  # ... all existing fields unchanged ...
  
  # NEW: optional per-field provenance
  _provenance:
    size.parameters:
      source_ref: "coreai-model-zoo-readme"          # references sources.yaml
      extraction_method: "upstream_readme_manual"     # enum
      source_url: "https://github.com/.../qwen3.md#L42"
      verified_at: "2026-06-24"
      confidence: "high"
    
    size.precision:
      source_ref: "hf:mlboydaisuke/qwen3-4b-CoreAI-official"
      extraction_method: "hf_metadata_api"
      verified_at: "2026-06-24"
      confidence: "high"
    
    device_support.iphone:
      source_ref: "crowdsourced:5-samples"
      extraction_method: "app_benchmark_protocol"
      verified_at: "2026-07-15"
      confidence: "high"
```

#### Benchmark provenance (the critical one)

```yaml
- id: bm-official-qwen3-4b-iphone17pro-gpu-crowd-001
  model_id: "official-qwen3-4b"
  metric: "decode_throughput"
  value: 145.4
  unit: "tokens_per_second"
  device: "iPhone17,1"
  compute_unit: "GPU"
  precision: "int4"
  environment: "iOS 27.0, coreai-pipelined"
  observed: "2026-07-15"
  higher_is_better: true
  
  # NEW: methodology (makes the benchmark reproducible)
  methodology:
    protocol_version: "1.0"
    prompt_tokens: 128
    generation_tokens: 256
    warmup_runs: 3
    measured_runs: 10
    statistic: "median"
    stddev: 2.1
    p50: 145.0
    p95: 152.0
    
  # NEW: device fingerprint (anonymized)
  device_info:
    chip: "A18 Pro"
    ram_gb: 8
    os_version: "27.0"
    
  # NEW: runtime config (exact configuration)
  runtime_config:
    engine: "coreai-pipelined"
    batch_size: 1
    context_length: 2048
    
  # NEW: reproducibility
  model_hash: "sha256:abc123def456..."
  
  # NEW: provenance chain
  provenance:
    source: "crowdsourced"                            # crowdsourced | manual | upstream
    extraction_method: "app_benchmark_protocol"        # enum
    submission_channel: "ditto-ios-0.1.0"              # app identifier
    device_attestation: true                           # Apple DeviceCheck
    submitted_at: "2026-07-15T12:00:00Z"
    verification_status: "accepted"                    # pending | accepted | quarantined | rejected
    
  source: "crowdsourced-pool-a"
  confidence: "high"
  notes: "Median of 10 runs, 3 warmup. Stable results."
```

### 2.2 Extraction method taxonomy

Every data point carries an `extraction_method` that tells you exactly how it was obtained:

| Method | Description | Default confidence |
|---|---|---|
| `upstream_readme_manual` | Human copied from README/table in source repo | `medium` |
| `upstream_readme_scripted` | Script parsed the README programmatically | `medium` |
| `upstream_release_notes` | From a GitHub release or changelog | `medium` |
| `hf_metadata_api` | Automated pull from Hugging Face model card API | `high` |
| `hf_file_listing` | Computed from actual file sizes in HF repo | `high` |
| `app_benchmark_protocol` | App ran controlled benchmark on real device | `high` |
| `app_benchmark_user` | User manually triggered a benchmark in the app | `high` |
| `community_submission` | User reported a number without protocol | `needs_review` |
| `derived_calculated` | Computed from other catalog fields | `medium` |
| `apple_documentation` | Official Apple docs/WWDC session | `high` |

### 2.3 Confidence scoring (replaces single global field)

With per-field provenance, confidence becomes computed:

```python
def compute_confidence(provenance_entry):
    method_scores = {
        "hf_metadata_api": 90,
        "app_benchmark_protocol": 95,
        "apple_documentation": 95,
        "upstream_readme_manual": 60,
        "community_submission": 30,
        "derived_calculated": 50,
    }
    base = method_scores.get(provenance_entry.extraction_method, 40)
    
    # Boost if verified recently
    if days_since(provenance_entry.verified_at) < 7:
        base += 5
    
    # Boost if cross-validated (multiple sources agree)
    if provenance_entry.cross_validated:
        base += 10
    
    return min(100, base)
```

### 2.4 Crowdsourced benchmark lifecycle

```
                    ┌─────────────────────┐
                    │   APP (Ditto)       │
                    │   Runs benchmark    │
                    │   with protocol     │
                    └────────┬────────────┘
                             │
                             ▼
            ┌────────────────────────────────┐
            │  GITHUB ISSUE (template)       │
            │  Auto-generated benchmark      │
            │  submission as structured JSON │
            │  (or: PR to benchmarks/ dir)   │
            └────────┬───────────────────────┘
                     │
                     ▼
            ┌────────────────────────────────┐
            │  GITHUB ACTION:                │
            │  benchmark-ingest.yml          │
            │                                │
            │  1. Parse submission JSON      │
            │  2. Validate against schema    │
            │  3. Check model_id exists      │
            │  4. Compute confidence score   │
            │  5. Outlier check (MAD)        │
            │  6. Write to                   │
            │     benchmarks/pending/        │
            │  7. Comment on issue with      │
            │     validation results         │
            └────────┬───────────────────────┘
                     │
                     ▼
            ┌────────────────────────────────┐
            │  CURATOR REVIEW                │
            │                                │
            │  - Reviews pending benchmarks  │
            │  - Approves → moves to         │
            │    benchmarks.yaml             │
            │  - Rejects → comments why      │
            │  - Regenerates dist/           │
            └────────┬───────────────────────┘
                     │
                     ▼
            ┌────────────────────────────────┐
            │  PUBLISHED                      │
            │  - benchmarks.yaml updated      │
            │  - dist/benchmarks.json regen   │
            │  - CLI shows new data           │
            │  - dist/transforms-graph.json   │
            │    pipeline speed estimates     │
            │    updated with new data        │
            └────────────────────────────────┘
```

### 2.5 The benchmark protocol (what the app runs)

For this to produce trustworthy data, the app's benchmark protocol must be **deterministic and documented**:

```
PROTOCOL v1.0 — Decode Throughput Benchmark

1. LOAD model bundle from local path
2. TOKENIZE standard prompt (128 tokens, fixed text)
3. WARMUP: generate 128 tokens × 3 iterations (discard results)
4. MEASURE: generate 256 tokens × 10 iterations
   - Record: time per iteration, token count
   - Record: peak memory (mach_task_basic_info)
5. COMPUTE: median, stddev, P50, P95 of throughputs
6. CAPTURE: device model, chip, OS version, engine variant
7. HASH: SHA256 of .aimodel bundle
8. PACKAGE: BenchmarkReport JSON (all fields above)
9. SUBMIT: GitHub Issue with structured template (or API)
```

The standard prompt is part of the protocol — every device runs the same prompt:
```
"The quick brown fox jumps over the lazy dog. " * 16  # exactly 128 tokens
```

### 2.6 Storage in the repo

```
coreai-catalog/
  benchmarks.yaml              # curated, published benchmarks (existing, evolved)
  benchmarks/                  # NEW: submission directory
    pending/                   # GitHub Action writes validated submissions here
      bm-001.json              # one JSON per submission
      bm-002.json
    rejected/                  # rejected submissions (kept for audit)
    templates/                 # submission templates
      benchmark-submission.yml # GitHub Issue template
      
  .github/
    workflows/
      benchmark-ingest.yml     # NEW: Action that validates submissions
      benchmark-validate.yml   # NEW: Action that runs schema + outlier checks
      
  schema/
    benchmark.schema.json      # EVOLVED: adds methodology + provenance fields
    provenance.schema.json     # NEW: defines provenance block structure
```

### 2.7 The GitHub Action (benchmark-ingest.yml)

```yaml
name: Benchmark Ingestion
on:
  issues:
    types: [opened]

jobs:
  ingest:
    if: contains(github.event.issue.labels.*.name, 'benchmark-submission')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Parse submission
        id: parse
        run: |
          # Extract JSON from issue body (between ```json fences)
          python3 scripts/parse_benchmark_submission.py \
            --issue-body "${{ github.event.issue.body }}" \
            --output benchmarks/pending/${{ github.event.issue.number }}.json
      
      - name: Validate schema
        run: |
          python3 scripts/validate_benchmark.py \
            benchmarks/pending/${{ github.event.issue.number }}.json
      
      - name: Outlier check
        run: |
          python3 scripts/outlier_check.py \
            --input benchmarks/pending/${{ github.event.issue.number }}.json \
            --catalog benchmarks.yaml
      
      - name: Comment with results
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              body: readFileSync('benchmarks/pending/${{ github.event.issue.number }}.md')
            })
```

### 2.8 Why this is SotA

1. **Git-native**: Every benchmark is version-controlled, diffable, attributable
2. **Fully transparent**: Anyone can audit the raw submissions, the validation, the curation decisions
3. **Reproducible by construction**: Every benchmark carries its full methodology
4. **No backend**: Zero infrastructure cost, zero maintenance burden
5. **Scalable**: GitHub handles the intake (Issues), Actions handle the pipeline, git handles the storage
6. **Auditable trust**: The extraction_method enum tells you exactly how trustworthy each number is
7. **Crowd-sourceable**: The app can auto-generate Issue submissions from device-side benchmarks
8. **Backward compatible**: Existing benchmarks.yaml works unchanged; provenance is additive

---

## 3. Migration plan (incremental, non-breaking)

### Phase A: Enrich existing data (no schema changes needed)

1. Add `extraction_method` to existing benchmark `notes` parsing
2. Tag all 44 README-derived benchmarks as `upstream_readme_manual` confidence `medium`
3. Tag all 22 test-run benchmarks as `upstream_script_automated` confidence `high`
4. This is a data-only change — no code changes

### Phase B: Evolve the schema

5. Add optional `methodology` block to benchmark.schema.json
6. Add optional `provenance` block to benchmark.schema.json
7. Add optional `_provenance` block to model.schema.json
8. Update validate.py to check new fields if present
9. Add provenance.schema.json

### Phase C: Build the intake pipeline

10. Create benchmark submission GitHub Issue template
11. Build parse_benchmark_submission.py
12. Build validate_benchmark.py (schema + cross-ref)
13. Build outlier_check.py (MAD against existing benchmarks)
14. Create benchmark-ingest.yml GitHub Action
15. Test with 3 synthetic submissions

### Phase D: App integration

16. Implement BenchmarkProtocol in Ditto (Swift)
17. Generate submission JSON from device-side benchmark
18. Submit as GitHub Issue from the app (via GitHub API)

---

*Design document — saved as `.internal/plans/2026-07-02_provenance-architecture.md`*
