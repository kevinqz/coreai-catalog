# On-Device OCR with Unlimited-OCR

Private, on-device document text extraction using the Unlimited-OCR Core AI model.

## Setup

```bash
pip install coreai-catalog
coreai-catalog install unlimited-ocr
```

Artifact: https://huggingface.co/mlboydaisuke/Unlimited-OCR-CoreAI

## Integration

> **Note:** The snippet below is conceptual — see [apple/coreai-models](https://github.com/apple/coreai-models) for complete, compiling working examples of the `AIModel` GraphModel API.

```swift
import CoreAI
import UIKit

/// OCR engine that runs Unlimited-OCR entirely on-device.
/// No network calls, no data leaves the device.
class OCREngine {
    private let model: AIModel

    init() throws {
        // 1. Load the .aimodel bundle from your app bundle
        //    After installing, copy the .aimodel from
        //    ~/.coreai-catalog/models/unlimited-ocr/artifacts/ into your Xcode project
        guard let bundleURL = Bundle.main.url(forResource: "unlimited-ocr", withExtension: "aimodel") else {
            throw OCRError.bundleNotFound
        }
        model = try AIModel(contentsOf: bundleURL)
    }

    /// Extract text from a UIImage.
    /// - Parameter image: Input image (document, receipt, screenshot, etc.)
    /// - Returns: Extracted text, bounding boxes, and confidence scores
    func extractText(from image: UIImage) async throws -> OCRResult {
        // Build a request with the image input (exact input key names vary by model;
        // see the model's spec in apple/coreai-models for the required inputs)
        let request = try model.makeRequest(inputs: [
            "image": image.cgImage!,
        ])
        let result = try await model.run(request)

        return OCRResult(
            text: result.outputs["text"] as? String ?? "",
            boundingBoxes: result.outputs["boxes"] as? [[Float]] ?? [],
            confidenceScores: result.outputs["scores"] as? [Float] ?? []
        )
    }
}

struct OCRResult {
    let text: String
    let boundingBoxes: [[Float]]
    let confidenceScores: [Float]
}

enum OCRError: Error {
    case bundleNotFound
}
```

## Usage in SwiftUI

```swift
import SwiftUI

struct OCRView: View {
    @State private var extractedText = ""
    @State private var isProcessing = false
    private let engine: OCREngine?

    init() {
        engine = try? OCREngine()
    }

    var body: some View {
        VStack {
            if isProcessing { ProgressView("Reading…") }

            TextEditor(text: .constant(extractedText))
                .disabled(true)

            Button("Scan Document") {
                Task { await performOCR() }
            }
        }
    }

    private func performOCR() async {
        guard let engine else { return }
        isProcessing = true
        defer { isProcessing = false }

        // Get image from camera or photo picker
        let image = // ... your image source
        let result = try? await engine.extractText(from: image)
        extractedText = result?.text ?? "(no text found)"
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
