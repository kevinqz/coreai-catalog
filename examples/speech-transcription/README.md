# speech-transcription — transcribe audio with a Core AI speech model

A real, buildable SwiftPM executable (not a conceptual snippet): loads a
Core AI speech bundle with `SpeechModel` from
[apple/coreai-models](https://github.com/apple/coreai-models) (product
`CoreAISpeech`) and transcribes an audio file on-device.

## Requirements — read this first

- **macOS 27.0+ / iOS 27.0+ and Xcode 27+** (platforms declared by
  apple/coreai-models `Package.swift`).
- **A Mac on macOS 26 (most dev Macs today) CANNOT build or run this.**
  `swift package dump-package` and `xcrun swiftc -parse` still work there.

## 1. Install the model

```bash
pip install coreai-catalog
coreai-catalog install official-whisper-large-v3-turbo
```

The artifact lands in
`~/.coreai-catalog/models/official-whisper-large-v3-turbo/artifacts/`
(mirroring the Hugging Face repo layout), with `manifest.json` and
`snippet.swift` alongside.

> **Bundle-layout caveat (honest limitation):** `SpeechModel` expects a
> *split* bundle directory containing `encoder.aimodel` + `decoder.aimodel`
> (`SpeechRunnerMain.swift:30-34`). This catalog artifact currently ships
> *monolithic* `whisper-large-v3-turbo_float16_fixed128.aimodel` files
> (see the artifact file list in `artifacts.yaml`), which
> apple/coreai-models handles through the speech-runner "legacy" low-level
> path instead (`SpeechRunnerMain.swift:64+`). This example implements the
> `SpeechModel` API — the runtime's public speech surface — and exits with
> an explicit error for monolithic bundles rather than pretending to
> support them.

## 2. Build and run (macOS 27+)

```bash
cd examples/speech-transcription
swift build -c release
swift run -c release speech-transcription <path-to-split-bundle-dir> talk.m4a
```

## 3. Use it in an app (Xcode last mile)

Add `https://github.com/apple/coreai-models` (product **CoreAISpeech**),
copy the installed bundle directory into your app as a folder reference
(the `~/.coreai-catalog` cache does not exist on iOS devices), and pass
its in-bundle URL to `SpeechModel(resourcesAt:)`. Full walkthrough:
[docs/getting-started.md](../../docs/getting-started.md).

## Model facts (generated from catalog.yaml)

<!-- BEGIN GENERATED: capability-table model=official-whisper-large-v3-turbo -->
<!-- Generated from catalog.yaml by scripts/generate_example_tables.py
     — do not edit by hand. Run the script to refresh. -->

| Field | Value (from catalog.yaml) |
|---|---|
| Model | Whisper large-v3-turbo (`official-whisper-large-v3-turbo`) |
| Capabilities | speech-to-text |
| Inputs | audio |
| Outputs | transcript |
| License | Apache-2.0 |
| Commercial use | likely |
| Parameters | 809M / ~1.5GB |
| Artifact size | 1.5GB |
| Devices | iPhone: yes · iPad: unknown · Mac: yes |
| Runner | CoreAITranscribe |
| Status | confirmed (experimental) |
| Last verified | 2026-06-24 |
| Artifact | https://huggingface.co/mlboydaisuke/whisper-large-v3-turbo-CoreAI-official |
<!-- END GENERATED: capability-table -->

Other speech-to-text models indexed in the catalog can be listed with
`coreai-catalog search --capability speech-to-text`.

## Where this code comes from

The API usage is copied from apple/coreai-models (commit `e203a0d`),
not invented:

- `swift/Sources/Tools/speech-runner/SpeechRunnerMain.swift:40-56` — the
  reference split-bundle flow: `SpeechModel(resourcesAt:)` +
  `transcribe(audioURL:)`.
- `swift/Sources/CoreAISpeech/SpeechModel.swift:26-56` — the public API
  (defaults: `WhisperDecoder`, `MelConfig.whisper`; also
  `transcribe(pcm:)` for raw 16 kHz mono samples).
