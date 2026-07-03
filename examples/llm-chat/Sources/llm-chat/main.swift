// llm-chat — minimal on-device chat CLI for Apple Core AI language models.
//
// The API usage below mirrors apple/coreai-models (commit e203a0d) exactly:
//   * models/qwen3/README.md, section "Run a Core AI Language Model"
//     (the documented FoundationModels integration snippet)
//   * swift/Tests/LanguageModelsTests/PublicInterfaceTests.swift:19-34
//     (Apple's compile-time check that this exact usage chain resolves:
//      CoreAILanguageModel(resourcesAt:) -> LanguageModelSession(model:)
//      -> session.respond(to:) -> response.content)
//
// Requires macOS 27.0+ (see Package.swift). A macOS 26 machine can parse
// and dump this package but cannot build or run it.

import CoreAILanguageModels
import Foundation
import FoundationModels

let arguments = CommandLine.arguments
guard arguments.count >= 2 else {
    print("usage: llm-chat <path-to-model-bundle-dir> [prompt]")
    print("")
    print("The bundle dir is the directory that contains the .aimodel")
    print("(and, for most LLMs, a tokenizer/ folder). After")
    print("`coreai-catalog install official-qwen3-0-6b` that is e.g.:")
    print("  ~/.coreai-catalog/models/official-qwen3-0-6b/artifacts/macos")
    print("")
    print("With no [prompt], starts an interactive multi-turn chat loop.")
    exit(64)
}
let modelURL = URL(fileURLWithPath: (arguments[1] as NSString).expandingTildeInPath)

// Load the .aimodel bundle and expose it through the FoundationModels API.
// Mirrors models/qwen3/README.md ("In your iOS and macOS applications via
// Foundation Models") and PublicInterfaceTests.swift:27-31.
let model = try await CoreAILanguageModel(resourcesAt: modelURL)

// LanguageModelSession (FoundationModels) is stateful: repeated respond(to:)
// calls on the same session carry the conversation transcript forward.
let session = LanguageModelSession(model: model)

if arguments.count >= 3 {
    // Single-shot mode.
    let response = try await session.respond(to: arguments[2])
    print(response.content)
} else {
    // Interactive multi-turn chat. Ctrl-D or an empty line exits.
    print("Interactive chat — empty line or Ctrl-D to exit.")
    while true {
        print("> ", terminator: "")
        guard let line = readLine(), !line.isEmpty else { break }
        let response = try await session.respond(to: line)
        print(response.content)
    }
}
