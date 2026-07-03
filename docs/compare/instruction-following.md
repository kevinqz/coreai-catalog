# Comparison: instruction-following

Side-by-side comparison of all 3 model(s) with the `instruction-following` capability.

| Model | Family | Parameters | Precision | Devices | License | Runtime | Benchmark | Source |
|---|---|---|---|---|---|---|---|---|
| Gemma 3 12B IT | Gemma | 12B | int4 | Mac | Gemma Terms | stock-runner | 55.0 tokens_per_second (M4 Max) | 🍎 Apple recipe |
| Gemma 3 4B IT | Gemma | 4B | int4 | Mac | Gemma Terms | stock-runner | 141.5 tokens_per_second (M4 Max) | 🍎 Apple recipe |
| LFM2.5-1.2B-Instruct | LFM | 1.2B | int8 | iPhone/Mac | LFM Open License v1.0 | CoreAIRunner | 276.5 tokens_per_second (M4 Max) | 🐼 Zoo |

> Generated automatically by `scripts/generate.py` from `catalog.yaml` + `benchmarks.jsonl`.

