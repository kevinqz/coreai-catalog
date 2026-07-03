# Core AI Catalog — Examples

Real, buildable SwiftPM packages — one per major capability the
[apple/coreai-models](https://github.com/apple/coreai-models) runtime
actually ships a product for. Each package pins the real dependency, uses
the real API (with file+line citations back to the upstream sources), and
carries a capability table **generated from `catalog.yaml`** so an example
can never claim something the catalog does not
(`scripts/generate_example_tables.py`).

## Requirements (all examples)

- **macOS 27.0+ / iOS 27.0+ and Xcode 27+** — the platforms declared by
  apple/coreai-models `Package.swift`. **A Mac on macOS 26 (most dev Macs
  today) cannot build or run these examples.** On macOS 26 you can still
  verify them structurally:

  ```bash
  cd examples/llm-chat
  swift package dump-package                        # works on any SDK
  xcrun swiftc -parse Sources/llm-chat/main.swift   # syntax check
  ```

  CI does exactly this: `dump-package` always, `swift build` only when the
  runner has a macOS 27 SDK (`.github/workflows/swift-examples.yml`).

## Available examples

| Example | Runtime product | Catalog model(s) | Task |
|---|---|---|---|
| [llm-chat](./llm-chat/) | `CoreAILM` | `official-qwen3-0-6b` | Text chat / generation |
| [ocr-vlm](./ocr-vlm/) | `CoreAILM` (multimodal engine) | `qwen3-vl-2b`, `unlimited-ocr` | Document OCR / image Q&A |
| [object-detection](./object-detection/) | `CoreAIObjectDetection` | `rf-detr-nano` | Object detection |
| [speech-transcription](./speech-transcription/) | `CoreAISpeech` | `official-whisper-large-v3-turbo` | Speech-to-text |

## Common workflow

```bash
# 1. Find + install a model (downloads the .aimodel bundle from Hugging Face
#    into ~/.coreai-catalog/models/<model-id>/artifacts/)
pip install coreai-catalog
coreai-catalog install official-qwen3-0-6b

# 2. Build and run the matching example (macOS 27+)
cd examples/llm-chat
swift run -c release llm-chat ~/.coreai-catalog/models/official-qwen3-0-6b/artifacts/macos
```

Each example README covers the Xcode/iOS last mile: the
`~/.coreai-catalog` cache only exists on the Mac that ran the CLI, so for
an app (especially iOS) you copy the `.aimodel` bundle into the app as a
folder reference and load it from `Bundle.main`.

## Why there is no embeddings example anymore

The previous `embeddings-rag` example was conceptual and invented an
embedding accessor on the response object that does not exist anywhere in
apple/coreai-models — the runtime ships products for language models,
diffusion, segmentation, speech, and object detection only (its
`Package.swift`). The catalog still indexes embedding models
(`coreai-catalog search --capability embedding`), but until the runtime
exposes an embedding surface, a compiling example cannot honestly be
written, so none is shipped.

## Regenerating the capability tables

```bash
python scripts/generate_example_tables.py           # rewrite
python scripts/generate_example_tables.py --check   # CI / verify
```

## Related

- [Getting started](../docs/getting-started.md) — install → integrate walkthrough
- [Catalog README](../README.md)
- [apple/coreai-models](https://github.com/apple/coreai-models) — the runtime these examples build on
