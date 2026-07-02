# Core AI vs Core ML vs MLX

Apple's machine-learning landscape has three major runtime/framework layers. They
serve different purposes, use different file formats, and target different developer
audiences. This page explains each, how they relate, and why Core AI Catalog
focuses on Core AI while cataloging all formats.

## At a glance

| | **Core AI** | **Core ML** | **MLX** |
|---|---|---|---|
| **Introduced** | 2026 (newest) | 2017 | 2023 |
| **Framework** | CoreAIKit | Core ML framework | MLX (Python / Swift API) |
| **Artifact format** | `.aimodel` | `.mlmodel` / `.mlpackage` | In-memory (`.safetensors` / `.gguf`) |
| **Primary use** | On-device generative AI (LLMs, diffusion, VLMs) | Classic on-device ML (classification, detection) | Research & training on Apple Silicon |
| **Unified memory** | Yes (zero-copy) | No (weights copied to compute device) | Yes (zero-copy) |
| **Developer experience** | Swift-native, pipeline-based | Swift-native, model-centric | Python-first, NumPy-like |
| **Runs on** | iOS 27+ / macOS 27+ | iOS 11+ / macOS 10.13+ | macOS 13.5+ |

## Core AI

**Core AI** is Apple's newest on-device ML framework, built for the generative-AI era.
It ships as **CoreAIKit** and uses the **`.aimodel`** bundle format.

Key characteristics:

- **Designed for generative models** — LLMs, vision-language models, diffusion models,
  speech models, embeddings.
- **Pipeline-based API** — models load through typed runners like `CoreAIRunner`,
  `CoreAITranscribe`, `CoreAIDiffusionPipeline`, `CoreAIImageSegmenter`.
- **Unified memory** — weights stay in shared Apple Silicon memory; no copy between
  CPU and GPU address spaces.
- **AOT compilation** — many artifacts support ahead-of-time compilation (`aot_required`)
  for faster cold-start.

Every model in the catalog currently ships as an `.aimodel` artifact:

```yaml
artifact:
  format: aimodel
  availability: available
```

Core AI is what the catalog is **about** — but it is not the only way to run ML on Apple
platforms.

## Core ML

**Core ML** is Apple's long-standing on-device ML framework, introduced in 2017. It
uses `.mlmodel` (compiled) and `.mlpackage` (source) formats and the **Core ML
framework**.

Key characteristics:

- **Battle-tested** — the default for classic ML tasks: image classification, object
  detection, pose estimation, tabular models.
- **Core ML Tools** (`coremltools`) converts PyTorch / TensorFlow / ONNX models to
  `.mlpackage`.
- **Neural Engine optimized** — Core ML models are first-class citizens on the Apple
  Neural Engine (ANE).
- **Broad OS support** — runs on iOS 11+, making it the most compatible option.

Core ML remains the right choice for many production apps — especially non-generative
models deployed at scale. The catalog tracks Core ML tooling in `upstreams.yaml`:

```yaml
- id: apple-coreml-docs
  title: Apple Core ML Developer Documentation
  category: framework
  trust: official_primary

- id: apple-coremltools
  title: apple/coremltools
  category: framework_tooling
  trust: official_primary
```

## MLX

**MLX** is Apple's machine-learning framework optimized for Apple Silicon, released in
2023. It is a **research and training framework**, not a deployment runtime.

Key characteristics:

- **Python-first** — NumPy-like API; PyTorch users feel at home.
- **Unified memory** — like Core AI, MLX exploits Apple Silicon's shared memory for
  zero-copy tensor operations.
- **Training-capable** — unlike Core ML or Core AI (which are inference-focused), MLX
  supports full training loops.
- **Community ecosystem** — `mlx-lm`, `mlx-vlm`, and Hugging Face integration make it
  popular for running LLMs on Mac.

MLX-to-Core AI bridges exist: `lucasnewman/mlx2coreai` captures MLX graphs and lowers
them to `.aimodel`:

```yaml
- id: lucasnewman-mlx2coreai
  title: lucasnewman/mlx2coreai
  category: conversion_and_zoo
  notes: Captures MLX graphs, lowers to CoreAI MLIR, writes .aimodel.
```

## Compute units: Neural Engine, GPU, and CPU

All three frameworks can target three compute units on Apple Silicon:

| Compute unit | Best for | Typical models | Notes |
|---|---|---|---|
| **Neural Engine (ANE)** | Matrix math, low-power inference | Small classifiers, quantized models | Most power-efficient; limited in generative workloads |
| **GPU** | Parallel compute, large-batch, generative | LLMs, diffusion, VLMs | Default for Core AI decode; highest raw throughput |
| **CPU** | Fallback, scalar logic, pre/post-processing | Tokenizers, embedding lookup | Always available; slowest for heavy matmul |

The catalog records which compute unit each benchmark was measured on:

```yaml
- id: qwen3-5-0-8b-iphone17pro-gpu-toks
  compute_unit: GPU        # ← decode throughput: 71.9 tok/s
  value: 71.9

- id: qwen3-5-0-8b-iphone17pro-ane-toks
  compute_unit: ANE        # ← same model on ANE: 14.7 tok/s
  value: 14.7
```

Same model, same device — but the GPU delivers **5× the throughput** of the ANE for this
8B-parameter LLM. This is why compute-unit-scoped benchmarks matter.

## How they relate

```
        ┌─────────────────────────────────────────┐
        │           Apple Silicon                 │
        │   (Unified CPU + GPU + Neural Engine)   │
        └──────────┬──────────┬──────────┬────────┘
                   │          │          │
              ┌────▼───┐ ┌───▼────┐ ┌───▼───┐
              │ Core AI │ │ Core ML │ │  MLX  │
              │ (2026)  │ │ (2017)  │ │(2023) │
              └────┬────┘ └────┬───┘ └───┬───┘
                   │           │         │
              .aimodel   .mlpackage  .safetensors
```

- **Core AI and MLX share unified memory** — both are built for Apple Silicon's
  shared-memory architecture.
- **Core ML has its own memory model** — weights are copied to the target compute device.
- **Conversion paths** connect them: `coremltools` (PyTorch → Core ML),
  `mlx2coreai` (MLX → Core AI), `coreai-onnx` (ONNX → Core AI).

## Why Core AI Catalog focuses on Core AI

The catalog centers on **Core AI** because:

1. **It's the newest and least documented.** Developers need a map.
2. **The ecosystem is fragmented.** Artifacts are scattered across community zoos,
   Hugging Face accounts, and Apple recipe repos — the catalog unifies them.
3. **Generative AI is the gap.** Core ML has mature tooling for classic ML; Core AI is
   where new LLMs, VLMs, and diffusion models land.
4. **Agent-native discovery.** Core AI models need structured metadata for agents to
   recommend, compare, and install them — which is the catalog's core mission.

But the catalog **references all three frameworks** in `upstreams.yaml`, because
developers need to understand the full landscape. Core ML and MLX are tracked as
framework sources and conversion paths are documented so you know how to move between
them.

## Choosing a framework

| If you need... | Use |
|---|---|
| On-device LLM, VLM, diffusion, or TTS | **Core AI** |
| Classic classification, detection, or tabular ML | **Core ML** |
| To train or fine-tune on Mac | **MLX** |
| Maximum OS compatibility (pre-iOS 27) | **Core ML** |
| Research prototyping with PyTorch ergonomics | **MLX** |

The catalog's 79 models are all `.aimodel` (Core AI) artifacts today, but the framework
and conversion taxonomy in `upstreams.yaml` ensures the catalog can grow to cover
cross-format workflows as the ecosystem evolves.
