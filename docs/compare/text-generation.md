# Comparison: text-generation

Side-by-side comparison of all 27 model(s) with the `text-generation` capability.

| Model | Family | Parameters | Precision | Devices | License | Runtime | Benchmark | Source |
|---|---|---|---|---|---|---|---|---|
| BitCPM-8B | BitCPM | 8B / ternary {-1,0,+1} | 1.58-bit ternary | iPhone/Mac | Apache-2.0 | CoreAIRunner (custom-kernel, patch, AOT) | 62.7 tokens_per_second (M4 Max) | 🐼 Zoo |
| FastContext-1.0-4B | FastContext | 4B | int4 | iPhone/Mac | MIT | CoreAIRunner (AOT) | 20.4 tokens_per_second (iPhone 17 Pro) | 🐼 Zoo |
| GLM-4.7-Flash | GLM | 30B / ~3B active | int8 | Mac | MIT | CoreAIRunner (custom-kernel, patch) | 52.4 tokens_per_second (M4 Max) | 🐼 Zoo |
| Gemma 3 12B IT | Gemma | 12B | int4 | Mac | Gemma Terms | stock-runner (stock, AOT) | 55.0 tokens_per_second (M4 Max) | 🍎 Apple recipe |
| Gemma 3 4B IT | Gemma | 4B | int4 | Mac | Gemma Terms | stock-runner (stock, AOT) | 141.5 tokens_per_second (M4 Max) | 🍎 Apple recipe |
| Gemma 4 12B | Gemma | 12B | int4 | Mac | Gemma Terms | CoreAIRunner (custom-kernel, patch) | 33 tokens_per_second (M4 Max) | 🐼 Zoo |
| Gemma 4 12B IT Multimodal (warshanks) | Gemma | 12B | int4 | Mac | Apache-2.0 | CoreAIRunner (patch) | — | 🔗 Independent |
| Gemma 4 31B | Gemma | 31B | int4 | Mac | Gemma Terms | CoreAIRunner (custom-kernel, patch) | 17.2 tokens_per_second (M4 Max) | 🐼 Zoo |
| Gemma 4 E2B | Gemma | E2B | int4 | iPhone/Mac | Gemma Terms | CoreAIRunner (patch, AOT) | 78.9 tokens_per_second (M4 Max) | 🐼 Zoo |
| Gemma 4 E4B | Gemma | E4B | int4 | iPhone/Mac | Gemma Terms | CoreAIRunner (patch, AOT) | 55.8 tokens_per_second (M4 Max) | 🐼 Zoo |
| Granite 4.0-H 1B | Granite | 1B | int8 | iPhone/Mac | Apache-2.0 | CoreAIRunner (patch) | 136.5 tokens_per_second (M4 Max) | 🐼 Zoo |
| Granite 4.0-H 350M | Granite | 350M | fp16 | iPhone/Mac | Apache-2.0 | CoreAIRunner (patch) | — | 🐼 Zoo |
| LFM2.5-1.2B-Instruct | LFM | 1.2B | int8 | iPhone/Mac | LFM Open License v1.0 | CoreAIRunner (patch) | 276.5 tokens_per_second (M4 Max) | 🐼 Zoo |
| LFM2.5-8B-A1B | LFM | 8B / ~1B active | int8 | iPhone/Mac | LFM Open License v1.0 | CoreAIRunner (custom-kernel, patch) | — | 🐼 Zoo |
| LLaDA-8B dLLM | LLaDA | 8B | int4 | Mac | MIT | CoreAIRunner | — | 🐼 Zoo |
| MiniCPM5-1B | MiniCPM | 1.08B | int8 | iPhone/Mac | Apache-2.0 | CoreAIRunner | 66.8 tokens_per_second (iPhone 17 Pro) | 🐼 Zoo |
| Mistral 7B v0.3 | Mistral | 7B | int4 | Mac | Apache-2.0 | stock-runner (stock, AOT) | 101.7 tokens_per_second (M4 Max) | 🍎 Apple recipe |
| Nanbeige4.1-3B | Nanbeige | 3.93B | int8 | iPhone/Mac | Apache-2.0 | CoreAIRunner (patch) | 114.5 tokens_per_second (M4 Max) | 🐼 Zoo |
| Qwen3 0.6B | Qwen | 0.6B | int4 | iPhone/Mac | Apache-2.0 | stock-runner (stock, AOT) | 1121 tokens_per_second (M4 Max) | 🍎 Apple recipe |
| Qwen3 1.7B | Qwen | 1.7B | int4 | iPhone/Mac | Apache-2.0 | stock-runner (stock, AOT) | — | 🍎 Apple recipe |
| Qwen3 4B | Qwen | 4B | int4 | iPhone/Mac | Apache-2.0 | stock-runner (stock, AOT) | 145.4 tokens_per_second (M4 Max) | 🍎 Apple recipe |
| Qwen3 8B | Qwen | 8B | int4 | Mac | Apache-2.0 | stock-runner (stock, AOT) | 94.1 tokens_per_second (M4 Max) | 🍎 Apple recipe |
| Qwen3.5-0.8B | Qwen | 0.8B | int8 | iPhone/Mac | Apache-2.0 | CoreAIRunner (patch) | 210 tokens_per_second (M4 Max) | 🐼 Zoo |
| Qwen3.5-2B | Qwen | 2B | int8 | iPhone/Mac | Apache-2.0 | CoreAIRunner (patch) | 161 tokens_per_second (M4 Max) | 🐼 Zoo |
| Qwen3.6-27B | Qwen | 27B | int8 | Mac | Apache-2.0 | CoreAIRunner (custom-kernel, patch) | 15.9 tokens_per_second (M4 Max) | 🐼 Zoo |
| Qwen3.6-35B-A3B | Qwen | 35B / ~3B active | int8 | Mac | Apache-2.0 | CoreAIRunner (custom-kernel, patch) | 64.9 tokens_per_second (M4 Max) | 🐼 Zoo |
| gpt-oss-20B | gpt-oss | 20B / ~13GB | MXFP4 | Mac | Apache-2.0 | stock-runner (stock) | 78.1 tokens_per_second (M4 Max) | 🍎 Apple recipe |

> Generated automatically by `scripts/generate_compare.py` from `catalog.yaml` + `benchmarks.yaml`.

