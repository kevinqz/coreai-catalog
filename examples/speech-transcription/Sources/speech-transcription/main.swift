// speech-transcription — transcribe an audio file with an Apple Core AI
// speech bundle (encoder.aimodel + decoder.aimodel).
//
// Every API call below mirrors apple/coreai-models (commit e203a0d) exactly:
//   * runner reference: swift/Sources/Tools/speech-runner/
//     SpeechRunnerMain.swift:40-56 (SpeechModel(resourcesAt:) +
//     transcribe(audioURL:) for split bundles)
//   * public API:       swift/Sources/CoreAISpeech/SpeechModel.swift:26-56
//     (init(resourcesAt:decoder:melConfig:) defaults to WhisperDecoder and
//     MelConfig.whisper; transcribe(audioURL:) and transcribe(pcm:))
//
// IMPORTANT bundle-layout caveat (kept honest, see SpeechRunnerMain.swift):
// SpeechModel expects a SPLIT bundle directory containing encoder.aimodel
// and decoder.aimodel. Some catalog artifacts ship a single monolithic
// .aimodel instead — apple/coreai-models handles those through the
// speech-runner "legacy" low-level path (SpeechRunnerMain.swift:64+),
// not through SpeechModel.
//
// Requires macOS 27.0+ (see Package.swift). A macOS 26 machine can parse
// and dump this package but cannot build or run it.

import CoreAISpeech
import Foundation

let arguments = CommandLine.arguments
guard arguments.count >= 3 else {
    print("usage: speech-transcription <path-to-speech-bundle-dir> <audio-file>")
    print("")
    print("The bundle dir must contain encoder.aimodel and decoder.aimodel.")
    print("Audio: wav/flac/m4a etc. (decoded to 16 kHz mono internally).")
    exit(64)
}
let bundleURL = URL(fileURLWithPath: (arguments[1] as NSString).expandingTildeInPath)
let audioURL = URL(fileURLWithPath: (arguments[2] as NSString).expandingTildeInPath)

guard FileManager.default.fileExists(atPath: bundleURL.appending(path: "encoder.aimodel").path)
else {
    print("error: \(bundleURL.path) does not contain encoder.aimodel.")
    print("SpeechModel needs a split bundle (encoder.aimodel + decoder.aimodel);")
    print("monolithic single-.aimodel exports need the low-level path shown in")
    print("apple/coreai-models swift/Sources/Tools/speech-runner/SpeechRunnerMain.swift.")
    exit(1)
}

// SpeechRunnerMain.swift:42 — defaults: WhisperDecoder, MelConfig.whisper.
let model = try await SpeechModel(resourcesAt: bundleURL)

print("Transcribing \(audioURL.lastPathComponent)…")
let text = try await model.transcribe(audioURL: audioURL)
print(text)
