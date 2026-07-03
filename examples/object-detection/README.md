# object-detection — detect objects in an image with a Core AI model

A real, buildable SwiftPM executable (not a conceptual snippet): loads a
detector `.aimodel` with `ObjectDetector` from
[apple/coreai-models](https://github.com/apple/coreai-models) (product
`CoreAIObjectDetection`) and prints label / confidence / bounding box for
each detection.

## Requirements — read this first

- **macOS 27.0+ / iOS 27.0+ and Xcode 27+** (platforms declared by
  apple/coreai-models `Package.swift`).
- **A Mac on macOS 26 (most dev Macs today) CANNOT build or run this.**
  `swift package dump-package` and `xcrun swiftc -parse` still work there.

## 1. Install the model

```bash
pip install coreai-catalog
coreai-catalog install rf-detr-nano
```

The artifact lands in `~/.coreai-catalog/models/rf-detr-nano/artifacts/`
(mirroring the Hugging Face repo layout, which for this repo contains
several `.aimodel` variants), with `manifest.json` and `snippet.swift`
alongside. Point the tool at the `.aimodel` directory itself, e.g.
`artifacts/rfdetr-nano_float32.aimodel`.

## 2. Build and run (macOS 27+)

```bash
cd examples/object-detection
swift build -c release
swift run -c release object-detection \
  ~/.coreai-catalog/models/rf-detr-nano/artifacts/rfdetr-nano_float32.aimodel \
  photo.jpg 0.3
```

## 3. Use it in an app (Xcode last mile)

Add `https://github.com/apple/coreai-models` (product
**CoreAIObjectDetection**), copy the installed `.aimodel` directory into
your app as a folder reference (the `~/.coreai-catalog` cache does not
exist on iOS devices), and pass its in-bundle path to
`ObjectDetector(resourcesAt:)`. Full walkthrough:
[docs/getting-started.md](../../docs/getting-started.md).

## Model facts (generated from catalog.yaml)

<!-- BEGIN GENERATED: capability-table model=rf-detr-nano -->
<!-- Generated from catalog.yaml by scripts/generate_example_tables.py
     — do not edit by hand. Run the script to refresh. -->

| Field | Value (from catalog.yaml) |
|---|---|
| Model | RF-DETR Nano (`rf-detr-nano`) |
| Capabilities | object-detection |
| Inputs | image |
| Outputs | boxes, classes, scores |
| License | Apache-2.0 |
| Commercial use | likely |
| Parameters | nano |
| Artifact size | 108MB |
| Devices | iPhone: yes · iPad: unknown · Mac: yes |
| Runner | CoreAIRunner |
| Status | confirmed (experimental) |
| Last verified | 2026-06-24 |
| Artifact | https://huggingface.co/mlboydaisuke/RF-DETR-CoreAI |
<!-- END GENERATED: capability-table -->

Other detectors indexed in the catalog: `rf-detr-small`, `rf-detr-medium`,
`rf-detr-large`, `yolox-s` — find them with
`coreai-catalog search --capability object-detection`.

## Where this code comes from

The API usage is copied from apple/coreai-models (commit `e203a0d`),
not invented:

- `models/yolo/README.md`, section "In your iOS and macOS applications" —
  the documented `ObjectDetector(resourcesAt:)` / `detect(image:parameters:)`
  / `DetectionParameters` snippet.
- `swift/Sources/Tools/object-detector/ObjectDetectionMain.swift` — the
  reference CLI: `DetectionParameters(threshold:maxDetections:)`, ImageIO
  `CGImage` loading, and the `DetectedObject` fields printed here.
  Bounding boxes use a top-left origin (see the render helper there).
- `swift/Sources/CoreAIObjectDetector/ObjectDetector.swift:23` and
  `DetectionOutputs.swift:33-104` — the public types.
