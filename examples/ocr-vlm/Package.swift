// swift-tools-version: 6.0

// ocr-vlm — compile-checked example package for the coreai-catalog.
//
// Platforms and dependencies mirror apple/coreai-models Package.swift
// (commit e203a0d): platforms [.macOS("27.0"), .iOS("27.0")], product
// "CoreAILM" (target CoreAILanguageModels). The swift-transformers
// dependency matches the ">= 1.1.0" pin declared by coreai-models itself
// and is needed here because the VLM path uses the Tokenizer protocol
// directly (module `Tokenizers`, product `Transformers`).
//
// NOTE: building this package requires the macOS 27 SDK (Xcode 27+).
// On earlier SDKs (e.g. macOS 26) `swift build` fails during dependency
// compilation; `swift package dump-package` still works everywhere.

import PackageDescription

let package = Package(
    name: "ocr-vlm",
    platforms: [.macOS("27.0"), .iOS("27.0")],
    dependencies: [
        .package(url: "https://github.com/apple/coreai-models", from: "0.1.0"),
        .package(url: "https://github.com/huggingface/swift-transformers", from: "1.1.0"),
    ],
    targets: [
        .executableTarget(
            name: "ocr-vlm",
            dependencies: [
                .product(name: "CoreAILM", package: "coreai-models"),
                .product(name: "Transformers", package: "swift-transformers"),
            ]
        )
    ]
)
