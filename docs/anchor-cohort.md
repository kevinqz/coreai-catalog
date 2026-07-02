# Anchor Cohort — Outlier Detection Baseline

## Purpose

The anchor cohort is a small set of curator-verified reference benchmarks
that provides a stable baseline for the MAD (Median Absolute Deviation)
outlier detection. Without anchors, a determined attacker could slowly
shift the median through coordinated submissions ("slow poisoning").

## How anchors work

1. The curator benchmarks key models on their reference device(s)
2. Each anchor entry is tagged `"source": "anchor-reference-hardware"`
3. Anchors are always included in the cohort for MAD computation
4. Anchors are refreshed quarterly (or after major OS updates)
5. Anchors never expire or get superseded

## Anchor entry format

Anchor entries follow the standard benchmark schema with these constraints:

```jsonl
{"id":"anchor-001","model_id":"official-qwen3-4b","metric":"decode_throughput","value":145.4,"unit":"tokens_per_second","device_class":"A18 Pro","os_major":"27","compute_unit":"GPU","precision":"int4","extraction_method":"app_benchmark_protocol","confidence":"high","observed_date":"2026-07-01","source":"anchor-reference-hardware","device_verified":true,"model_verified":true,"higher_is_better":true,"environment":{"protocol_version":"2.0","engine":"coreai-pipelined","warmup_runs":3,"measured_runs":10,"statistic":"median","stddev":2.1,"thermal_state":"nominal","battery_state":"charging"}}
```

Key differences from crowd submissions:
- `source`: must be `"anchor-reference-hardware"`
- `confidence`: always `"high"` (curator-verified)
- `device_verified`: must be `true`
- `model_verified`: must be `true`
- `environment.protocol_version`: must be `"2.0"` (with full methodology)
- `environment.thermal_state`: must be `"nominal"`

## Adding anchors

1. Curator runs benchmarks on reference hardware following Protocol v2.0
2. Entries are appended to `benchmarks.jsonl` with `"source": "anchor-reference-hardware"`
3. Entries are signed by the relay (same Ed25519 process)
4. PR is labeled `anchor-cohort` (bypasses outlier check — these DEFINE the baseline)
5. Curator merges directly

## Refresh cycle

- **Quarterly**: Re-run all anchor benchmarks after each iOS/macOS major release
- **Ad-hoc**: When a model conversion changes (new precision, new engine variant)
- Old anchors are kept (tagged with their OS version) for historical comparison
- New anchors are added alongside, not replacing old ones

## Protection against anchor poisoning

- Anchors are curated by the repo maintainer only (not crowd-sourced)
- PR branch protection requires maintainer approval for `anchor-cohort` labeled PRs
- The CF Worker relay signs anchors with the same Ed25519 key
- Anchor values that wildly disagree with crowd data are investigated, not suppressed
