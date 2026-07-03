# Benchmark Protocol v1.0

> Defines how the app measures performance to ensure reproducibility.

## Reference runner (`bench/CoreAIBenchRunner`)

The protocol is now executable: `bench/CoreAIBenchRunner` is a SwiftPM
package implementing the LLM metrics below (`decode_throughput`,
`time_to_first_token`) on top of the real `apple/coreai-models` API
(engine creation and trial timing mirror Apple's own `llm-benchmark`
tool). It **requires macOS 27+** — the upstream runtime declares
`platforms: [.macOS("27.0")]`.

```sh
cd bench/CoreAIBenchRunner && swift build -c release   # macOS 27 only
python3 -m coreai_catalog.bench <model-id>             # orchestrated run
```

The Python orchestrator (`coreai_catalog/bench.py`) resolves the installed
artifact, passes provenance (HF revision, digest root, freshness nonce =
catalog HEAD commit) into the runner, re-computes the medians from the raw
trials, and assembles a schema-valid `benchmarks.jsonl` candidate line with
`extraction_method: app_benchmark_protocol` and `verification_tier:
unverified`. Nothing is auto-appended; submission remains a reviewed step.

Runner outputs (in `--out-dir`):

- `trials.jsonl` — raw per-trial records (TTFT, decode seconds/tokens,
  peak memory via `mach_task_basic_info`, per-trial thermal state).
- `run-manifest.json` — the signing payload: `runner_version`,
  `protocol_version`, `model_id`, `artifact_revision`,
  `artifact_sha256_root`, `seed`, `freshness_nonce`, thermal states
  before/after, and self-check flags (`prompt_token_count_exact`,
  `greedy_sampling`, `sampling_seed_applied`, `thermal_pressure_detected`,
  `all_trials_completed_requested_tokens`, `device_class_coarsened`).

**Determinism note:** the upstream `SamplingConfiguration` API has no seed
parameter, so the runner uses greedy sampling (`temperature: 0`) — the only
deterministic path the API offers. The `--seed` value is recorded in the
manifest with `sampling_seed_applied: false`.

**Decode window definition:** `decode_throughput` is measured from the
*first streamed token* to the last (`decode_tokens = generated − 1`),
matching Apple's `llm-benchmark`. Prefill cost is never folded into decode
throughput; it is reported separately as `time_to_first_token`.

## Artifact digest root

A benchmark must name the bytes it measured (append-only provenance).
`artifact_sha256_root` is computed from the artifact's
`huggingface.files` list in `artifacts.yaml`:

1. take every `{path, sha256}` pair,
2. sort by `path`,
3. join lines `"<sha256>  <path>"` with `\n`,
4. sha256 the UTF-8 bytes of the joined string.

`artifact_revision` is the pinned Hugging Face commit the installer
downloaded. Both fields are optional in the schema and appear only when the
catalog actually records digests — unknown stays absent.

## Verification tiers

`verification_tier` (optional field; absent = `unverified`):

| Tier | Meaning |
|---|---|
| `unverified` | Single self-reported protocol run (n=1). |
| `community_verified` | Independently reproduced by a second identity within tolerance. |
| `hardware_attested` | Submitted via an App Attest companion app. |
| `maintainer_verified` | Re-run or audited by a maintainer. |
| `disputed` | Under an open flag/challenge. |

### CI gate outcome vs. verification tier

`benchmark-validate.yml` auto-merges a signed submission when all its gates
pass (`scripts/physics_check.py` → `TIER_GATES`/`evaluate_tier`:
schema-valid, model id exists, signature valid, signer identity == PR
author, physics-plausible, not an outlier, not a duplicate). That merge
outcome is labeled **`signed_plausible`** — a *CI gate outcome*, not a
`verification_tier` value, and it never claims `community_verified`: a
single n=1 run has, by definition, not been reproduced by a second
identity. The merged row keeps `verification_tier: unverified`, which is
accurate for n=1 (CI could not rewrite it anyway — every field except
`_signature` is covered by the submitter's signature, so stamping a tier
would invalidate it).

**How a row earns `community_verified`:** a second identity submitting the
same model_id + device_class + metric within 7 days trips the CI
`not_duplicate` gate *by design* — the reproduction routes to curator
review (label `benchmark-needs-review`) instead of auto-merging. The
curator checks that the two runs agree within tolerance, merges the
reproduction, and promotes the cohort to `community_verified` in a
maintainer-lane PR.

Related optional fields: `runner_version` (which runner build produced the
row), `raw_trials_url` (where the raw per-trial JSONL lives so medians can
be recomputed), and `superseded_by` (append-only store: superseded rows are
retained and marked, never overwritten).

## Decode Throughput (LLMs)

### Standard prompt
```
The quick brown fox jumps over the lazy dog.
```
Repeated until exactly **128 tokens** when tokenized by the model under test.

### Execution
1. Load model via `CoreAIRunner`
2. Tokenize standard prompt
3. **Warmup:** generate 128 tokens × 3 iterations (discard timing)
4. **Measure:** generate 256 tokens × 10 iterations
   - Record `mach_absolute_time()` before first token
   - Record `mach_absolute_time()` after last token
   - Compute `throughput = 256 / elapsed_seconds`
   - Record peak memory via `mach_task_basic_info`
5. **Statistics:** median, stddev, P50, P95

### What to capture
- `metric: "decode_throughput"`, `value: median`, `unit: "tokens_per_second"`
- `methodology: { protocol_version: "1.0", prompt_tokens: 128, generation_tokens: 256, warmup_runs: 3, measured_runs: 10, statistic: "median", stddev, p50, p95 }`
- `runtime_config: { engine, compute_unit, precision, batch_size, context_length }`
- `environment_state: { thermal_state, low_power_mode, battery_level, plugged_in }`
- `model_hash: SHA256(.aimodel dir contents)`

## Device Coarsening Table

Raw device models are coarsened before any data enters git. The single
source of truth is `benchmarks/protocol-config.json` →
`device_coarsening.mapping` (exact-identifier match, one `source`
citation per row). Representative rows:

| Raw device_model | device_class | chip_family |
|---|---|---|
| iPhone17,1 / iPhone17,2 | iphone-a18-pro | A18 Pro |
| iPhone17,3 / iPhone17,4 / iPhone17,5 | iphone-a18 | A18 |
| iPhone16,1 / iPhone16,2 | iphone-a17-pro | A17 Pro |
| iPhone15,2 / iPhone15,3 / iPhone15,4 / iPhone15,5 | iphone-a16 | A16 |
| iPad16,3 / iPad16,4 / iPad16,5 / iPad16,6 | ipad-m4 | M4 |
| iPad16,1 / iPad16,2 | ipad-a17-pro | A17 Pro |
| iPad14,1 / iPad14,2 | ipad-a15 | A15 |
| iPad14,3 – iPad14,11 | ipad-m2 | M2 |
| Mac16,1 (MacBook Pro 14", 2024) | mac-m4 | M4 |
| Mac16,7 / Mac16,8 / Mac16,11 | mac-m4-pro | M4 Pro |
| Mac16,5 / Mac16,6 / Mac16,9 | mac-m4-max | M4 Max |
| Mac15,3 (MacBook Pro 14", Nov 2023) | mac-m3 | M3 |
| Mac15,6 / Mac15,7 | mac-m3-pro | M3 Pro |
| Mac15,8 – Mac15,11 | mac-m3-max | M3 Max |
| Mac15,12 / Mac15,13 (MacBook Air M3) | mac-m3 | M3 |

Note the two historical traps this table fixes (redteam finding B5):
`Mac16,1` is the **base-M4** MacBook Pro (120 GB/s), *not* M4 Max
(546 GB/s), and `Mac15,3` is the **base-M3** MacBook Pro, not M3 Max.
Identifiers verified against Apple's identify-your-model pages
(support.apple.com/en-us/108052, 102869, 102852, 108054, 102231).
Unknown identifiers coarsen to `unknown` — add new mappings (with a
source citation) as new hardware ships.

## Privacy Rules

- Date only — **never** send time-of-day. Use `"2026-07-15"`, not `"2026-07-15T12:03:47Z"`.
- Device class — **never** send raw `iPhone17,1`. Coarsen first.
- No user identifier of any kind.
- No IP logging.
- App Attest token is sent but used only for validation, never stored.
