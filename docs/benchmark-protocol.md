# Benchmark Protocol v1.0

> Defines how the app measures performance to ensure reproducibility.

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

Raw device models are coarsened before any data enters git:

| Raw device_model | device_class | chip_family |
|---|---|---|
| iPhone17,1 / iPhone17,2 | iphone-a18-pro | A18 Pro |
| iPhone16,1 / iPhone16,2 | iphone-a17-pro | A17 Pro |
| iPhone15,2 / iPhone15,3 | iphone-a16 | A16 |
| iPad16,3 / iPad16,4 | ipad-m4 | M4 |
| iPad14,1 / iPad14,2 | ipad-m2 | M2 |
| Mac16,1 | mac-m4-max | M4 Max |
| Mac15,3 | mac-m3-max | M3 Max |
| Mac15,12 | mac-m3 | M3 |

Add new mappings as new hardware ships.

## Privacy Rules

- Date only — **never** send time-of-day. Use `"2026-07-15"`, not `"2026-07-15T12:03:47Z"`.
- Device class — **never** send raw `iPhone17,1`. Coarsen first.
- No user identifier of any kind.
- No IP logging.
- App Attest token is sent but used only for validation, never stored.
