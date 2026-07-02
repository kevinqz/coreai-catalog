# On-Device OCR with Unlimited-OCR

Private, on-device document text extraction using the Unlimited-OCR Core AI model.

## Setup

```bash
pip install coreai-catalog
coreai-catalog install unlimited-ocr
```

Artifact: https://huggingface.co/mlboydaisuke/Unlimited-OCR-CoreAI

## Integration

> **Note:** The snippet below is conceptual — see [apple/coreai-models](https://github.com/apple/coreai-models) for complete, compiling working examples of the `LanguageModelSession` API for vision/OCR models.

```swift
import CoreAI
import UIKit

/// OCR engine that runs Unlimited-OCR entirely on-device.
/// No network calls, no data leaves the device.
class OCREngine {
    private let session: LanguageModelSession

    init() async throws {
        // Unlimited-OCR is a stock-runner model, so use LanguageModelSession
        // with CoreAILanguageModel (wraps the installed .aimodel bundle).
        session = LanguageModelSession(model: CoreAILanguageModel())
    }

    /// Extract text from a UIImage.
    /// - Parameter image: Input image (document, receipt, screenshot, etc.)
    /// - Returns: Extracted text (markdown, HTML, or LaTeX depending on content)
    func extractText(from image: UIImage) async throws -> String {
        guard let imageData = image.jpegData(compressionQuality: 0.8) else {
            throw OCRError.imageEncodingFailed
        }
        // Attach the image and ask the model to extract text.
        let attachment = Attachment(data: imageData, type: .image)
        let response = try await session.respond(
            to: "Extract all text from this image, preserving structure as markdown.",
            attachments: [attachment]
        )
        return response.content
    }
}

enum OCRError: Error {
    case imageEncodingFailed
}
```

## Usage in SwiftUI

```swift
import SwiftUI

struct OCRView: View {
    @State private var extractedText = ""
    @State private var isProcessing = false
    @State private var engine: OCREngine?

    var body: some View {
        VStack {
            if isProcessing { ProgressView("Reading…") }

            TextEditor(text: .constant(extractedText))
                .disabled(true)

            Button("Scan Document") {
                Task { await performOCR() }
            }
        }
        .task {
            // Initialize the engine asynchronously when the view appears
            engine = try? await OCREngine()
        }
    }

    private func performOCR() async {
        guard let engine else { return }
        isProcessing = true
        defer { isProcessing = false }

        // Get image from camera or photo picker
        let image = // ... your image source
        let result = try? await engine.extractText(from: image)
        extractedText = result ?? "(no text found)"
    }
}
```

## Capabilities

| Feature | Support |
|---|---|
| Device | iPhone, iPad, Mac |
| Offline | ✅ Fully on-device |
| License | Apache-2.0 (commercial use: likely) |
| Architecture | Encoder |
| Benchmark | Not yet published |

## Caveats

- Input image quality affects OCR accuracy significantly
- Very large images may need downsampling for memory constraints
- The model handles printed and handwritten text in multiple languages
