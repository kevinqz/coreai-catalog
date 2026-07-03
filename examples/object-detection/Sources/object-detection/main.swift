// object-detection — detect objects in an image with an Apple Core AI
// .aimodel detector and print label / confidence / bounding box.
//
// Every API call below mirrors apple/coreai-models (commit e203a0d) exactly:
//   * documented app snippet: models/yolo/README.md, section "In your iOS
//     and macOS applications" (ObjectDetector(resourcesAt:),
//     detect(image:)/detect(images:parameters:), DetectionParameters,
//     warmup(imageCount:parameters:))
//   * CLI reference:          swift/Sources/Tools/object-detector/
//     ObjectDetectionMain.swift (DetectionParameters(threshold:maxDetections:),
//     CGImage loading via ImageIO, DetectedObject fields label/labelIndex/
//     confidence/boundingBox — boundingBox uses a top-left origin, see the
//     render helper comment there)
//   * public types:           swift/Sources/CoreAIObjectDetector/
//     ObjectDetector.swift:23 and DetectionOutputs.swift:33-104
//
// Requires macOS 27.0+ (see Package.swift). A macOS 26 machine can parse
// and dump this package but cannot build or run it.

import CoreAIObjectDetector
import CoreGraphics
import Foundation
import ImageIO

let arguments = CommandLine.arguments
guard arguments.count >= 3 else {
    print("usage: object-detection <path-to-model.aimodel> <image-path> [threshold]")
    print("")
    print("The model path must point at the .aimodel directory itself, e.g.")
    print("  ~/.coreai-catalog/models/rf-detr-nano/artifacts/rfdetr-nano_float32.aimodel")
    exit(64)
}
let modelPath = arguments[1]
let imagePath = arguments[2]
let threshold = arguments.count >= 4 ? Float(arguments[3]) ?? 0.3 : 0.3

// ── Load the image (ObjectDetectionMain.swift, loadCGImage(from:)) ──────────
func loadCGImage(from path: String) throws -> CGImage {
    let expanded = NSString(string: path).expandingTildeInPath
    let url = URL(fileURLWithPath: expanded)
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else {
        throw CocoaError(.fileReadNoSuchFile)
    }
    guard let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw CocoaError(.fileReadCorruptFile)
    }
    return cgImage
}
let image = try loadCGImage(from: imagePath)

// ── Load the detector and run (models/yolo/README.md app snippet) ───────────
let detector = try await ObjectDetector(resourcesAt: modelPath)
let parameters = DetectionParameters(threshold: threshold, maxDetections: 100)
let detections = try await detector.detect(image: image, parameters: parameters)

// ── Print results (same fields the object-detector CLI reports) ─────────────
print("Detections (\(detections.count)):")
for (index, detection) in detections.enumerated() {
    let box = detection.boundingBox
    print(
        "  [\(index)] \(detection.label) score=\(String(format: "%.3f", detection.confidence))"
            + "  box=(\(Int(box.origin.x)),\(Int(box.origin.y)),\(Int(box.size.width))x\(Int(box.size.height)))"
    )
}
