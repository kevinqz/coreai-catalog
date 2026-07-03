# ocr-vlm — document OCR / image chat with a Core AI vision-language model

A real, buildable SwiftPM executable (not a conceptual snippet): encodes an
image through the multimodal engine of
[apple/coreai-models](https://github.com/apple/coreai-models) and generates
text from image + prompt. Use it for document OCR ("Extract all text from
this image as markdown") or general image Q&A.

This replaces the old conceptual `ocr-swiftui`/`vlm-chat` examples, which
routed an image model through a text-only chat call (redteam finding C1)
and claimed a license that contradicted the catalog (finding C4). The
capability tables below are generated from `catalog.yaml`, so this README
cannot disagree with the catalog again.

## Requirements — read this first

- **macOS 27.0+ / iOS 27.0+ and Xcode 27+** (platforms declared by
  apple/coreai-models `Package.swift`).
- **A Mac on macOS 26 (most dev Macs today) CANNOT build or run this.**
  `swift package dump-package` and `xcrun swiftc -parse` still work there.

## 1. Install a model

```bash
pip install coreai-catalog
coreai-catalog install qwen3-vl-2b        # general VLM (image + text -> text)
# or
coreai-catalog install unlimited-ocr      # document-OCR specialist
```

Artifacts land in `~/.coreai-catalog/models/<model-id>/artifacts/`
(mirroring the Hugging Face repo layout), with `manifest.json` and
`snippet.swift` alongside.

> **Bundle-layout note (honest limitation):** this example drives the VLM
> engine from apple/coreai-models, whose own VLM exports are `.llmasset`
> bundles with a `metadata.json` containing a `vision` block
> (`models/vlm/README.md`, "Bundle layout"). Community-converted catalog
> artifacts may ship a different directory layout — check the artifact
> repo (linked in the tables below) for its layout before pointing this
> tool at it. The code fails with an explicit error if the bundle has no
> `vision` config.

## 2. Build and run (macOS 27+)

```bash
cd examples/ocr-vlm
swift build -c release
swift run -c release ocr-vlm <path-to-vlm-bundle-dir> page.png \
  "Extract all text from this image as markdown."
```

## 3. Use it in an app (Xcode last mile)

Add `https://github.com/apple/coreai-models` (product **CoreAILM**) plus
`https://github.com/huggingface/swift-transformers` (product
**Transformers**), copy the installed bundle directory into your app as a
folder reference (the `~/.coreai-catalog` cache does not exist on iOS
devices), and resolve the bundle URL from `Bundle.main` instead of a CLI
argument. Full walkthrough:
[docs/getting-started.md](../../docs/getting-started.md).

## Model facts (generated from catalog.yaml)

### Qwen3-VL 2B — general vision-language

<!-- BEGIN GENERATED: capability-table model=qwen3-vl-2b -->
<!-- Generated from catalog.yaml by scripts/generate_example_tables.py
     — do not edit by hand. Run the script to refresh. -->

| Field | Value (from catalog.yaml) |
|---|---|
| Model | Qwen3-VL 2B (`qwen3-vl-2b`) |
| Capabilities | vision-language |
| Inputs | image, text |
| Outputs | text |
| License | Apache-2.0 |
| Commercial use | likely |
| Parameters | 2B |
| Artifact size | 2.3GB |
| Devices | iPhone: yes · iPad: unknown · Mac: yes |
| Runner | CoreAIRunner |
| Status | confirmed (experimental) |
| Last verified | 2026-06-24 |
| Artifact | https://huggingface.co/mlboydaisuke/Qwen3-VL-2B-CoreAI |
<!-- END GENERATED: capability-table -->

### Unlimited-OCR — document OCR

<!-- BEGIN GENERATED: capability-table model=unlimited-ocr -->
<!-- Generated from catalog.yaml by scripts/generate_example_tables.py
     — do not edit by hand. Run the script to refresh. -->

| Field | Value (from catalog.yaml) |
|---|---|
| Model | Unlimited-OCR (`unlimited-ocr`) |
| Capabilities | document-ocr |
| Inputs | document_image, image |
| Outputs | markdown, html, latex |
| License | MIT |
| Commercial use | check_license |
| Parameters | not_published |
| Artifact size | not_published |
| Devices | iPhone: yes · iPad: unknown · Mac: yes |
| Runner | stock-runner |
| Status | confirmed (experimental) |
| Last verified | 2026-06-24 |
| Artifact | https://huggingface.co/mlboydaisuke/Unlimited-OCR-CoreAI |
<!-- END GENERATED: capability-table -->

The catalog records Unlimited-OCR's outputs as `markdown, html, latex`
but does not specify how the output format is selected — that contract
lives with the upstream model, not the catalog. This example simply
prints whatever the model generates.

## Where this code comes from

The API usage is copied from apple/coreai-models (commit `e203a0d`),
not invented:

- `swift/Sources/Tools/llm-runner/LLMRunnerMain.swift`,
  `runVLMInference(...)` — the reference image-input flow: cast the engine
  to `MultimodalInferenceEngine`, `encodeImage(at:)`, expand the image
  placeholder token, `generate(with:tokens:...)`, incremental decode.
- `swift/Sources/CoreAILanguageModels/LanguageModel/CoreAIRunner.swift:29-71`
  — bundle + engine construction.
- `swift/Sources/CoreAILanguageModels/InferenceEngines/CoreAISequentialVLMEngine.swift:44-75`
  — the VLM model contract (vision encoder / projector / embed / decoder).
