// ocr-vlm — image + text -> text with an Apple Core AI vision-language model.
//
// Use it for document OCR ("Extract all text from this image as markdown")
// or general VLM chat about an image. This is the image-input code path that
// the old conceptual catalog examples got wrong (redteam finding C1): a VLM
// bundle is driven through the multimodal engine, NOT through a text-only
// LanguageModelSession prompt.
//
// Every API call below mirrors apple/coreai-models (commit e203a0d) exactly:
//   * engine + bundle setup: swift/Sources/CoreAILanguageModels/LanguageModel/
//     CoreAIRunner.swift:29-71 (CoreAIRunner(contentsOf:), makeInferenceEngine())
//   * VLM inference flow:    swift/Sources/Tools/llm-runner/LLMRunnerMain.swift,
//     runVLMInference(...) — engine cast to MultimodalInferenceEngine,
//     encodeImage(at:), placeholder-token prompt assembly ("USER: <image>xN
//     \n prompt \nASSISTANT:" fallback), generate(with:tokens:...), and the
//     incremental decode loop over InferenceOutput.tokenId
//   * engine contract:       swift/Sources/CoreAILanguageModels/InferenceEngines/
//     CoreAISequentialVLMEngine.swift:44-75 (model contract doc comment) and
//     InferenceEngine.swift:301-315 (MultimodalInferenceEngine protocol)
//
// Requires macOS 27.0+ (see Package.swift). A macOS 26 machine can parse
// and dump this package but cannot build or run it.

import CoreAILanguageModels
import Foundation
import Tokenizers

let arguments = CommandLine.arguments
guard arguments.count >= 3 else {
    print("usage: ocr-vlm <path-to-vlm-bundle-dir> <image-path> [prompt]")
    print("")
    print("default prompt: \"Extract all text from this image as markdown.\"")
    print("The bundle dir must contain a VLM export (metadata.json with a")
    print("'vision' block, vision/embedding/main .aimodel assets).")
    exit(64)
}
let modelURL = URL(fileURLWithPath: (arguments[1] as NSString).expandingTildeInPath)
let imageURL = URL(fileURLWithPath: (arguments[2] as NSString).expandingTildeInPath)
let prompt = arguments.count >= 4 ? arguments[3] : "Extract all text from this image as markdown."
let maxTokens = 1024

// ── Load bundle + engine (CoreAIRunner.swift:29-71) ─────────────────────────
let bundle = try LanguageBundle(at: modelURL)
let runner = CoreAIRunner(from: bundle)
let engine = try await runner.makeInferenceEngine()

// The image path requires a multimodal engine and a vision config
// (LLMRunnerMain.swift, runVLMInference guards).
guard let vlmEngine = engine as? any MultimodalInferenceEngine else {
    print("error: this bundle is not a vision-language model (engine is not multimodal)")
    exit(1)
}
guard let visionConfig = bundle.visionConfig else {
    print("error: VLM bundle missing 'vision' config in metadata.json")
    exit(1)
}
let tokenizer = try await bundle.loadTokenizer()

// ── Encode the image (MultimodalInferenceEngine.encodeImage(at:)) ───────────
let embeddedInput = try await vlmEngine.encodeImage(at: imageURL)

// ── Assemble the prompt with image placeholder tokens ───────────────────────
// Generic "USER: <image>xN \n prompt \nASSISTANT:" format — the documented
// fallback in LLMRunnerMain.swift when no multimodal chat template applies.
var vlmTokens = tokenizer.encode(text: "USER: ", addSpecialTokens: true).map { Int32($0) }
vlmTokens.append(
    contentsOf: [Int32](repeating: visionConfig.imageTokenId, count: embeddedInput.tokenCount))
vlmTokens.append(
    contentsOf: tokenizer.encode(text: "\n" + prompt + "\nASSISTANT:", addSpecialTokens: false)
        .map { Int32($0) })

// Stop tokens: tokenizer EOS (LLMRunnerMain.swift, runVLMInference).
var eosTokenIds = Set<Int32>()
if let eos = tokenizer.eosTokenId { eosTokenIds.insert(Int32(eos)) }

// ── Generate and stream-decode ──────────────────────────────────────────────
let tokenStream = try vlmEngine.generate(
    with: embeddedInput,
    tokens: vlmTokens,
    samplingConfiguration: SamplingConfiguration.greedy,
    inferenceOptions: InferenceOptions(maxTokens: maxTokens)
)

var generatedTokens: [Int] = []
var previousText = ""
for try await output in tokenStream {
    let token = output.tokenId
    if eosTokenIds.contains(token) { break }
    generatedTokens.append(Int(token))

    // Incremental decode: print only the newly decoded suffix.
    let fullText = tokenizer.decode(tokens: generatedTokens)
    let delta = String(fullText.dropFirst(previousText.count))
    previousText = fullText
    print(delta, terminator: "")
    fflush(stdout)
}
print()
