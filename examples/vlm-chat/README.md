# Vision-Language Chat with Qwen3-VL 2B

On-device multimodal chat: send an image + text prompt, get a text response.
Runs entirely on Apple Silicon via Core AI.

## Setup

```bash
pip install coreai-catalog
coreai-catalog install qwen3-vl-2b
```

Artifact: https://huggingface.co/mlboydaisuke/Qwen3-VL-2B-CoreAI

## Integration

> **Note:** The snippet below is conceptual — see [apple/coreai-models](https://github.com/apple/coreai-models) for complete, compiling working examples of the `ChatSession` CoreAIKit API for LLMs.

```swift
import CoreAIKit
import UIKit

/// Vision-Language Model chat engine.
/// Accepts image + text, returns text descriptions, answers, or captions.
/// Uses the CoreAIKit ChatSession API (the model runs via CoreAIRunner under the hood).
class VLMEngine {
    private var chat: ChatSession?

    init() async throws {
        // Qwen3-VL-2B is an LLM (runner: CoreAIRunner), so use the CoreAIKit
        // ChatSession API with the catalog model identifier.
        chat = try await ChatSession(catalog: "qwen3-vl-2b")
    }

    /// Send an image with a text prompt and get a response.
    /// - Parameters:
    ///   - image: The image to analyze
    ///   - prompt: Text instruction (e.g. "Describe what you see")
    /// - Returns: Model's text response
    func analyze(image: UIImage, prompt: String) async throws -> String {
        guard let chat else { throw VLMError.notInitialized }
        // Attach the image and the text prompt to the session.
        let response = try await chat.respond(to: prompt, attachments: [image])
        return response.content
    }

    /// Multi-turn conversation with image context.
    /// Maintains conversation state across turns (ChatSession is stateful).
    func chatTurn(_ text: String) async throws -> String {
        guard let chat else { throw VLMError.notInitialized }
        let response = try await chat.respond(to: text)
        return response.content
    }
}

enum VLMError: Error {
    case notInitialized
}
```

## Usage in SwiftUI

> The `VLMEngine` initializer is `async throws` because `ChatSession(catalog:)` loads the model asynchronously.

```swift
import SwiftUI

struct VLMChatView: View {
    @State private var prompt = "Describe what you see in this image"
    @State private var response = ""
    @State private var isThinking = false
    @State private var selectedImage: UIImage?
    @State private var engine: VLMEngine?

    var body: some View {
        VStack(spacing: 16) {
            // Image picker placeholder
            if let image = selectedImage {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .frame(height: 200)
            }

            TextField("Ask about the image…", text: $prompt)
                .textFieldStyle(.roundedBorder)

            if isThinking { ProgressView() }

            ScrollView { Text(response) }

            Button("Analyze") {
                Task { await analyze() }
            }
        }
        .padding()
        .task {
            // Initialize the engine asynchronously when the view appears
            engine = try? await VLMEngine()
        }
    }

    private func analyze() async {
        guard let engine, let image = selectedImage else { return }
        isThinking = true
        defer { isThinking = false }
        response = (try? await engine.analyze(image: image, prompt: prompt)) ?? "(error)"
    }
}
```

## Capabilities

| Feature | Support |
|---|---|
| Device | iPhone, iPad, Mac |
| Offline | ✅ Fully on-device |
| License | Apache-2.0 (commercial use: likely) |
| Parameters | 2B |
| Architecture | Transformer (vision-language) |
| Streaming | ✅ Supported |

## Common prompts

- "Describe what you see in this image"
- "What objects are in this photo?"
- "Read the text in this image aloud"
- "Is there anything unusual in this scene?"
- "Count the number of people in this image"
