# llm-chat — on-device chat with a Core AI language model

A real, buildable SwiftPM executable (not a conceptual snippet): loads a
`.aimodel` LLM bundle with `CoreAILanguageModel` and chats through the
FoundationModels `LanguageModelSession` API.

## Requirements — read this first

- **macOS 27.0+ / iOS 27.0+ and Xcode 27+.** These are the platforms
  declared by [apple/coreai-models](https://github.com/apple/coreai-models)
  `Package.swift`, which this example depends on.
- **A Mac on macOS 26 (most dev Macs today) CANNOT build or run this.**
  On macOS 26 you can still verify the package structure with
  `swift package dump-package` and syntax-parse the sources with
  `xcrun swiftc -parse Sources/llm-chat/main.swift` — but `swift build`
  fails because the dependency requires the macOS 27 SDK.

## 1. Install the model

```bash
pip install coreai-catalog
coreai-catalog install official-qwen3-0-6b
```

`coreai-catalog install` downloads the artifact from Hugging Face into
`~/.coreai-catalog/models/official-qwen3-0-6b/artifacts/` (mirroring the
Hugging Face repo layout) and writes `manifest.json` + `snippet.swift`
next to it. For this artifact the macOS bundle directory is
`artifacts/macos/` (contains the `.aimodel` and a `tokenizer/` folder).

## 2. Build and run (macOS 27+)

```bash
cd examples/llm-chat
swift build -c release
swift run -c release llm-chat \
  ~/.coreai-catalog/models/official-qwen3-0-6b/artifacts/macos \
  "What is quantum computing?"

# or interactive multi-turn chat:
swift run -c release llm-chat \
  ~/.coreai-catalog/models/official-qwen3-0-6b/artifacts/macos
```

## 3. Use it in an app (Xcode last mile)

1. **Add the package**: File → Add Package Dependencies →
   `https://github.com/apple/coreai-models`, product **CoreAILM**.
2. **Get the model into the app.** The `~/.coreai-catalog` cache is a
   Mac-side CLI convenience — it does not exist on iOS devices. Drag the
   installed bundle directory (e.g. `artifacts/macos/`) into your Xcode
   project as a **folder reference** (blue folder) so the `.aimodel`
   directory structure is preserved inside the app bundle.
3. **Load it by URL** exactly as `main.swift` does, but resolve the URL
   from the app bundle instead of a CLI argument:

   ```swift
   let modelURL = Bundle.main.resourceURL!.appendingPathComponent("macos")
   let model = try await CoreAILanguageModel(resourcesAt: modelURL)
   let session = LanguageModelSession(model: model)
   ```

See [docs/getting-started.md](../../docs/getting-started.md) for the full
install → integrate walkthrough.

## Model facts (generated from catalog.yaml)

<!-- BEGIN GENERATED: capability-table model=official-qwen3-0-6b -->
<!-- Generated from catalog.yaml by scripts/generate_example_tables.py
     — do not edit by hand. Run the script to refresh. -->

| Field | Value (from catalog.yaml) |
|---|---|
| Model | Qwen3 0.6B (`official-qwen3-0-6b`) |
| Capabilities | chat, text-generation |
| Inputs | text |
| Outputs | text |
| License | Apache-2.0 |
| Commercial use | likely |
| Parameters | 0.6B |
| Artifact size | not_published |
| Devices | iPhone: yes · iPad: unknown · Mac: yes |
| Runner | stock-runner |
| Status | confirmed (experimental) |
| Last verified | 2026-06-24 |
| Artifact | https://huggingface.co/mlboydaisuke/qwen3-0.6b-CoreAI-official |
<!-- END GENERATED: capability-table -->

Any chat-capable catalog model with runner `stock-runner` or
`CoreAIRunner` can be substituted — find them with
`coreai-catalog search --capability chat`.

## Where this code comes from

The API usage is copied from apple/coreai-models (commit `e203a0d`),
not invented:

- `models/qwen3/README.md`, section "Run a Core AI Language Model" — the
  documented `CoreAILanguageModel(resourcesAt:)` + `LanguageModelSession`
  integration snippet.
- `swift/Tests/LanguageModelsTests/PublicInterfaceTests.swift:19-34` —
  Apple's own compile-time check of this exact usage chain.
