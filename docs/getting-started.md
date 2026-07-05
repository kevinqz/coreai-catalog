# Getting Started

This guide takes you from zero to running Core AI models on Apple Silicon in 10 minutes.

## 60 seconds — find the right model

```bash
pip install coreai-catalog

# Describe your task in plain English
coreai-catalog recommend --task "private OCR on iPhone" --license likely
```

Output:

```
  Task: private OCR on iPhone
  Capabilities: document-ocr, vision-language

  Recommended models:

  1. Unlimited-OCR
     83 (B) · iPhone/Mac · ✅ MIT
     not benchmarked · not_published params
     Document OCR to markdown; tables to HTML; formulas to LaTeX.

     Install:  coreai-catalog install unlimited-ocr
     Artifact: https://huggingface.co/mlboydaisuke/Unlimited-OCR-CoreAI
```

That's it. You found the best model for your task, verified the license, and got an install command.

## 5 minutes — explore the catalog

### Search by capability and device

```bash
# What vision-language models run on iPhone?
coreai-catalog search --capability vision-language --device iphone

# What LLMs are commercially safe?
coreai-catalog search --capability chat --license likely
```

### See deployability / curation readiness

```bash
coreai-catalog scores
```

`scores` prints a 0–100 curation/deployability composite (`readiness_score`) with a grade — **deprecated as a headline** because it is blind to model quality. Prefer the per-entry **suitability facets** (`deployability` / `lifecycle` / `entry_completeness`) in `dist/search-index.json`, and judge quality from benchmark values. See [`concepts/suitability-facets.md`](concepts/suitability-facets.md).

### Compare two models

```bash
coreai-catalog compare qwen3-vl-2b unlimited-ocr
```

Side-by-side: capabilities, devices, runtime, license, benchmarks.

### Browse all capabilities

```bash
coreai-catalog capabilities
```

## 10 minutes — install and integrate

> **Runtime requirement (read first):** running `.aimodel` bundles requires
> **macOS 27.0+ / iOS 27.0+ and Xcode 27+** — the platforms declared by
> [apple/coreai-models](https://github.com/apple/coreai-models)
> `Package.swift`. A Mac on macOS 26 (most dev Macs today) can browse,
> install, and structurally verify everything below, but **cannot build or
> run** the Swift integrations.

### Install a model

```bash
coreai-catalog install official-qwen3-0-6b
```

This downloads the artifact from Hugging Face into
`~/.coreai-catalog/models/<model-id>/artifacts/` (mirroring the Hugging
Face repo layout) and writes `manifest.json` plus a `snippet.swift`
starting point next to it.

### See what was installed

```bash
coreai-catalog installed
ls ~/.coreai-catalog/models/official-qwen3-0-6b/artifacts/
cat ~/.coreai-catalog/models/official-qwen3-0-6b/snippet.swift
```

### Integrate in Swift — real, buildable examples

[`examples/`](../examples/) contains one compile-checked SwiftPM package
per runtime capability, each pinned to the real
[apple/coreai-models](https://github.com/apple/coreai-models) products and
carrying a capability table generated from `catalog.yaml`:

- [llm-chat](../examples/llm-chat/) — text chat via `CoreAILanguageModel` + `LanguageModelSession` (product `CoreAILM`)
- [ocr-vlm](../examples/ocr-vlm/) — document OCR / image Q&A via the multimodal engine (product `CoreAILM`)
- [object-detection](../examples/object-detection/) — `ObjectDetector` (product `CoreAIObjectDetection`)
- [speech-transcription](../examples/speech-transcription/) — `SpeechModel` (product `CoreAISpeech`)

```bash
cd examples/llm-chat
swift run -c release llm-chat \
  ~/.coreai-catalog/models/official-qwen3-0-6b/artifacts/macos \
  "What is quantum computing?"
```

> The `snippet.swift` written by `coreai-catalog install` is a conceptual
> starting point; the `examples/` packages are the compile-checked path.

### The last mile: from `~/.coreai-catalog` into your Xcode project

`coreai-catalog install` puts the model in a **Mac-side CLI cache**
(`~/.coreai-catalog/models/<model-id>/artifacts/`). Your app — especially
an iOS app, where that path does not exist — needs the bundle inside its
own resources:

1. **Add the runtime package** in Xcode: File → Add Package Dependencies →
   `https://github.com/apple/coreai-models`, then pick the product you
   need (`CoreAILM`, `CoreAIObjectDetection`, `CoreAISpeech`,
   `CoreAISegmentation`, or `CoreAIDiffusion`).
2. **Copy the model into the app.** Drag the installed bundle directory
   (e.g. `artifacts/macos/` for an LLM, or the `.aimodel` directory itself
   for a detector) into your project as a **folder reference** (blue
   folder) — `.aimodel` is a directory whose internal structure must be
   preserved. Check it is listed in the target's "Copy Bundle Resources".
3. **Load it from `Bundle.main`** instead of the CLI cache path:

   ```swift
   // Folder reference "macos" copied into the app bundle:
   let modelURL = Bundle.main.resourceURL!.appendingPathComponent("macos")
   let model = try await CoreAILanguageModel(resourcesAt: modelURL)
   ```

   For Mac command-line tools you can skip the copy and pass the
   `~/.coreai-catalog/...` path directly, exactly as the `examples/`
   CLIs do.

Large models inflate the app download; for iOS consider on-demand
resources or downloading the bundle at first launch and loading it from
`Application Support` by `URL` — `resourcesAt:` takes any file URL.

## For agents: MCP server

Connect the catalog to Claude Desktop, Cursor, or any MCP-compatible client:

```bash
pip install "coreai-catalog[mcp]"
```

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "coreai-catalog": {
      "command": "coreai-catalog-mcp"
    }
  }
}
```

Now your agent can call `search_models`, `recommend_model`, `compare_models`, `check_license`, and 7 more tools.

## For automation: JSON API

```bash
# Raw GitHub URLs (no clone needed)
curl -s https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/catalog.json | python -m json.tool

# Or use the CLI
coreai-catalog search --capability chat --device mac --json | python -m json.tool
```

Base URL: `https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/`

## Next steps

- [Philosophy](../PROJECT_PHILOSOPHY.md) — why this project exists
- [Concepts](./concepts/) — understand model vs artifact vs upstream
- [Task pages](./tasks/) — browse by use case
- [Contributing](../CONTRIBUTING.md) — add a model or artifact (model PRs and benchmark PRs are separate lanes)
- [coreai-fabric](https://github.com/kevinqz/coreai-fabric) — convert a new model yourself (recipe → convert → verify → publish to your own HF repo → register here via PR)
