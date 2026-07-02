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

### See readiness scores

```bash
coreai-catalog scores
```

Every model gets a 0–100 score based on 13 factors: device support, benchmark availability, license clarity, runtime stability, and more.

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

### Install a model

```bash
coreai-catalog install unlimited-ocr
```

This downloads the `.aimodel` bundle from Hugging Face to `~/.coreai-catalog/models/` and generates a Swift integration snippet.

### See what was installed

```bash
coreai-catalog installed
cat ~/.coreai-catalog/models/unlimited-ocr/snippet.swift
```

### Integrate in Swift

See [`examples/`](../examples/) for complete integration guides:

- [OCR with Unlimited-OCR](../examples/ocr-swiftui/) — document text extraction
- [VLM chat with Qwen3-VL](../examples/vlm-chat/) — image + text → response
- [Embeddings + RAG](../examples/embeddings-rag/) — on-device semantic search

> **Note:** Swift snippets in the catalog are conceptual and intended to show the
> correct API surface (`LanguageModelSession` + `CoreAILanguageModel` for LLMs,
> `SpeechModel` for transcription, `DiffusionPipeline` for image generation,
> `ImageSegmenter` for segmentation, `ObjectDetector` for detection).
> For complete, compiling examples, see
> [apple/coreai-models](https://github.com/apple/coreai-models).

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
- [Contributing](../CONTRIBUTING.md) — add a model or artifact
