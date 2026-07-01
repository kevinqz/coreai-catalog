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

```swift
import CoreAI
import UIKit

/// Vision-Language Model chat engine.
/// Accepts image + text, returns text descriptions, answers, or captions.
class VLMEngine {
    private let model: CoreAIModel

    init() throws {
        guard let bundleURL = Bundle.main.url(forResource: "qwen3-vl-2b", withExtension: "aimodel") else {
            throw VLMError.bundleNotFound
        }
        model = try CoreAIModel(contentsOf: bundleURL)
    }

    /// Send an image with a text prompt and get a response.
    /// - Parameters:
    ///   - image: The image to analyze
    ///   - prompt: Text instruction (e.g. "Describe what you see")
    /// - Returns: Model's text response
    func analyze(image: UIImage, prompt: String) async throws -> String {
        let request = CoreAIRequest.input(
            image: image.cgImage!,
            text: prompt
        )
        let response = try await model.predict(request)
        return response.text
    }

    /// Multi-turn conversation with image context.
    /// Maintains conversation state across turns.
    func chat(image: UIImage, messages: [(role: String, content: String)]) async throws -> String {
        let conversation = messages.map { msg in
            CoreAIRequest.Message(role: msg.role, content: msg.content)
        }
        let request = CoreAIRequest.conversation(
            image: image.cgImage!,
            messages: conversation
        )
        let response = try await model.predict(request)
        return response.text
    }
}

enum VLMError: Error {
    case bundleNotFound
}
```

## Usage in SwiftUI

```swift
import SwiftUI

struct VLMChatView: View {
    @State private var prompt = "Describe what you see in this image"
    @State private var response = ""
    @State private var isThinking = false
    @State private var selectedImage: UIImage?
    private let engine: VLMEngine?

    init() {
        engine = try? VLMEngine()
    }

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
