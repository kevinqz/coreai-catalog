// swift-tools-version: 6.0

// object-detection — compile-checked example package for the coreai-catalog.
//
// Platforms and dependency mirror apple/coreai-models Package.swift
// (commit e203a0d): platforms [.macOS("27.0"), .iOS("27.0")], product
// "CoreAIObjectDetection" (target CoreAIObjectDetector).
//
// NOTE: building this package requires the macOS 27 SDK (Xcode 27+).
// On earlier SDKs (e.g. macOS 26) `swift build` fails during dependency
// compilation; `swift package dump-package` still works everywhere.

import PackageDescription

let package = Package(
    name: "object-detection",
    platforms: [.macOS("27.0"), .iOS("27.0")],
    dependencies: [
        .package(url: "https://github.com/apple/coreai-models", from: "0.1.0")
    ],
    targets: [
        .executableTarget(
            name: "object-detection",
            dependencies: [
                .product(name: "CoreAIObjectDetection", package: "coreai-models")
            ]
        )
    ]
)
