// swift-tools-version: 6.0

// CoreAIBenchRunner — pinned open-source benchmark runner for coreai-catalog
// (redteam findings B1/B8; spec §3.2 step 1).
//
// Platform honesty: the apple/coreai-models runtime declares
// `platforms: [.macOS("27.0"), .iOS("27.0")]` (apple/coreai-models
// Package.swift:12 @ e203a0da, and at tag 0.1.0), so this runner honestly
// requires macOS 27 too. It cannot be built or run on macOS 26.x.

import PackageDescription

let package = Package(
    name: "CoreAIBenchRunner",
    platforms: [.macOS("27.0")],
    dependencies: [
        // Runtime under test. CoreAILM is the library product wrapping the
        // CoreAILanguageModels target (apple/coreai-models Package.swift:14-19).
        .package(url: "https://github.com/apple/coreai-models", from: "0.1.0"),
        .package(url: "https://github.com/apple/swift-argument-parser", from: "1.2.0"),
    ],
    targets: [
        .executableTarget(
            name: "coreai-bench-runner",
            dependencies: [
                .product(name: "CoreAILM", package: "coreai-models"),
                .product(name: "ArgumentParser", package: "swift-argument-parser"),
            ],
            path: "Sources/CoreAIBenchRunner"
        )
    ]
)
