# Runtime Matrix

| Runtime field | Meaning |
|---|---|
| `runtime_name: apple-core-ai` | Model artifact targets Apple Core AI |
| `format: aimodel` | Artifact is an Apple Core AI `.aimodel` |
| `source_group: zoo` | Community-port model card from `zoo/` |
| `source_group: official` | Official-recipe conversion from `official/` |
| `stock_runtime: true` | Runs on stock runtime |
| `stock_runtime: false` | Requires non-stock/community path |
| `custom_kernel: true` | Uses custom Metal kernel |
| `patch_required: true` | Requires patch or non-standard workaround |
| `tokenizer_required: true` | Text tokenizer required |
| `processor_required: true` | Image/audio/document processor required |
| `aot_required: true` | AOT compilation required or expected for iOS bundles |

## High-risk runtime flags

| Model family | Flag | Notes |
|---|---|---|
| Qwen3.6-35B-A3B | `custom_kernel: true` | Uses `gather_qmm` Metal kernel |
| GLM-4.7-Flash | `custom_kernel: true` | MoE + MLA; uses `gather_qmm` |
| Gemma 4 12B / 31B | `custom_kernel: true` | Uses flash-decode kernel |
| LFM2.5-8B-A1B | `custom_kernel: true` | MoE path with `gather_qmm` |
| official models | `stock_runtime: true` | Official recipe conversions from `official/` |
