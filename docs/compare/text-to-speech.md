# Comparison: text-to-speech

Side-by-side comparison of all 6 model(s) with the `text-to-speech` capability.

| Model | Family | Parameters | Precision | Devices | License | Runtime | Benchmark | Source |
|---|---|---|---|---|---|---|---|---|
| Kokoro-82M | Kokoro | 82M | fp32 | iPhone/Mac | Apache-2.0 | CoreAIRunner | — | 🐼 Zoo |
| VibeVoice 0.5B | VibeVoice | 0.5B | fp16 | Mac | MIT | CoreAIRunner | 10.2 realtime_factor (M4 Max) | 🔗 Independent |
| VibeVoice 1.5B | VibeVoice | 1.5B | fp16 | Mac | MIT | CoreAIRunner | 4.99 realtime_factor (M4 Max) | 🔗 Independent |
| VibeVoice 7B | VibeVoice | 7B | fp16 | Mac | MIT | CoreAIRunner | 2.37 realtime_factor (M4 Max) | 🔗 Independent |
| VoxCPM-0.5B | VoxCPM | 0.5B | int8 | iPhone/Mac | Apache-2.0 | CoreAIRunner | 0.9 frames_per_second (iPhone 17 Pro) | 🐼 Zoo |
| VoxCPM2 2B | VoxCPM | 2B | int8 | iPhone/Mac | Apache-2.0 | CoreAIRunner | — | 🐼 Zoo |

> Generated automatically by `scripts/generate.py` from `catalog.yaml` + `benchmarks.yaml`.

