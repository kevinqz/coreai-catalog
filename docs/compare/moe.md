# Comparison: moe

Side-by-side comparison of all 4 model(s) with the `moe` capability.

| Model | Family | Parameters | Precision | Devices | License | Runtime | Benchmark | Source |
|---|---|---|---|---|---|---|---|---|
| GLM-4.7-Flash | GLM | 30B / ~3B active | int8 | Mac | MIT | CoreAIRunner | 52.4 tokens_per_second (M4 Max) | 🐼 Zoo |
| LFM2.5-8B-A1B | LFM | 8B / ~1B active | int8 | iPhone/Mac | LFM Open License v1.0 | CoreAIRunner | — | 🐼 Zoo |
| Qwen3.6-35B-A3B | Qwen | 35B / ~3B active | int8 | Mac | Apache-2.0 | CoreAIRunner | 64.9 tokens_per_second (M4 Max) | 🐼 Zoo |
| gpt-oss-20B | gpt-oss | 20B / ~13GB | MXFP4 | Mac | Apache-2.0 | stock-runner | 78.1 tokens_per_second (M4 Max) | 🍎 Apple recipe |

> Generated automatically by `scripts/generate.py` from `catalog.yaml` + `benchmarks.jsonl`.

