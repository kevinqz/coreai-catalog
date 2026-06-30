# Comparison: speech-to-text

Side-by-side comparison of all 8 model(s) with the `speech-to-text` capability.

| Model | Family | Parameters | Precision | Devices | License | Runtime | Benchmark | Source |
|---|---|---|---|---|---|---|---|---|
| Nemotron 3.5 ASR Streaming 0.6B | Nemotron | 0.6B | fp16 | iPhone/Mac | OpenMDW-1.1 | CoreAITranscribe (stock, AOT) | — | 🔗 Independent |
| Parakeet-TDT-0.6B | Parakeet | 0.6B | fp16 | iPhone/Mac | CC-BY-4.0 | CoreAIKit-GraphModel (stock, AOT) | 47.9 frames_per_second (iPhone 17 Pro) | 🐼 Zoo |
| Qwen3-ASR-1.7B | Qwen | 1.7B | int8 | iPhone/Mac | Apache-2.0 | CoreAIRunner | — | 🐼 Zoo |
| VibeVoice ASR | VibeVoice | 7B | fp16 | Mac | MIT | CoreAIRunner | 11.1 realtime_factor (M4 Max) | 🔗 Independent |
| Whisper large-v3-turbo | Whisper | 809M / ~1.5GB | fp16 | iPhone/Mac | Apache-2.0 | CoreAITranscribe (stock, AOT) | 0.18 seconds_per_token (M4 Max) | 🍎 Apple recipe |
| Whisper large-v3-turbo (CarstenL) | Whisper | 809M | fp16 | Mac | Apache-2.0 | CoreAITranscribe (stock) | — | 🔗 Independent |
| Whisper medium (Intiser) | Whisper | 769M | fp16 | Mac | MIT | CoreAITranscribe (stock) | — | 🔗 Independent |
| Whisper tiny.en (Intiser) | Whisper | 39M | fp16 | Mac | MIT | CoreAITranscribe (stock) | — | 🔗 Independent |

> Generated automatically by `scripts/generate_compare.py` from `catalog.yaml` + `benchmarks.yaml`.

