# Apple AI Terminology Map

Generated from `terms.yaml`.

## System surfaces

### Apple Intelligence

Personal intelligence system across Apple devices, powered by Apple Foundation Models; provides personal context, app actions and on-screen awareness.

**Source:** https://developer.apple.com/apple-intelligence/

### Visual Intelligence

System visual-understanding capability; the 2026 update adds image input to the on-device model for on-device visual tasks.

**Source:** https://developer.apple.com/apple-intelligence/whats-new/

### Image Playground

Image-generation experience and developer API in the Apple Intelligence ecosystem.

**Source:** https://developer.apple.com/documentation/imageplayground

## Developer frameworks

### Core AI

WWDC26 framework for bringing PyTorch models to production on Apple Silicon (LLMs and generative AI); successor to Core ML for generative AI; exports the .aimodel format.

**Source:** https://developer.apple.com/documentation/coreai/

### Foundation Models framework

Native Swift API giving access to Apple Foundation Models (on-device and Private Cloud Compute) and to any provider with a Swift package conforming to the LanguageModel protocol.

**Source:** https://developer.apple.com/documentation/FoundationModels

### Core ML

Framework for integrating traditional ML models into apps; predates Core AI and is superseded by it for generative AI; uses .mlpackage / .mlmodel.

**Source:** https://developer.apple.com/documentation/coreml

### MLX

Open-source array framework for ML on Apple Silicon (research, training, fine-tuning, inference) with unified memory and lazy evaluation; a parallel research/training layer, not a Core AI dependency.

**Source:** https://github.com/ml-explore/mlx

### App Intents

Framework that connects app content and actions to Apple Intelligence, Siri and Spotlight through schemas, entities and intents.

**Source:** https://developer.apple.com/documentation/appintents

### Vision

Framework for image analysis such as detection, recognition and tracking; Vision tools can be called by the model during generation.

**Source:** https://developer.apple.com/documentation/vision

### Speech

Framework for speech recognition and audio analysis on Apple platforms.

**Source:** https://developer.apple.com/documentation/speech

### Evaluations framework

WWDC26 Swift framework (sessions 298/299/335) for measuring intelligence feature quality. API: subject(from:), ModelSample, Metric, Evaluator, ModelJudgeEvaluator, ScoreDimension, TrajectoryExpectation, ToolCallEvaluator. Runs in Swift Testing, supports macOS/iOS/watchOS/visionOS, on-device or against Private Cloud Compute.

**Source:** https://developer.apple.com/apple-intelligence/whats-new/

### Metal

GPU programming framework; backs the custom Metal kernels some Core AI model conversions require.

**Source:** https://developer.apple.com/metal/

### CoreAIKit

Swift package from the coreai-models project providing higher-level abstractions for running .aimodel bundles: KitLanguageModel (LanguageModel conformance), GraphModel (multi-graph encoders/transducers), TextEmbedder, ImageTextEncoder, and the CoreAIRunner LLM driver. The primary programmatic interface to Core AI artifacts.

**Source:** https://github.com/apple/coreai-models

## Model providers

### Apple Foundation Models

Apple's proprietary models (on-device and server via Private Cloud Compute) that power Apple Intelligence; third generation (AFM 3) at WWDC26; not open weights and not downloadable.

**Source:** https://machinelearning.apple.com/research/introducing-third-generation-of-apple-foundation-models

### Private Cloud Compute

Apple's privacy-preserving server infrastructure for running larger Foundation Models off-device.

**Source:** https://security.apple.com/blog/private-cloud-compute/

## Provider protocols

### LanguageModel protocol

Public Swift protocol a provider implements so any model (Apple, Claude, Gemini, local) can back a LanguageModelSession without changing app logic.

**Source:** https://developer.apple.com/videos/play/wwdc2026/339/

### CoreAILanguageModel

Apple adapter that wraps a Core AI .aimodel bundle into a LanguageModel conforming to the Foundation Models framework, enabling session.respond / stream / Tool usage with one-line integration.

**Source:** https://developer.apple.com/documentation/FoundationModels

## AI primitives

### LanguageModelSession

Session object that runs prompts and tools against a LanguageModel in the Foundation Models framework.

**Source:** https://developer.apple.com/documentation/FoundationModels

### Tool calling

Model invocation of app-provided tools (including Vision tools) during generation.

**Source:** https://developer.apple.com/documentation/FoundationModels

### Spotlight semantic index

Semantic index that App Intents entity schemas contribute to, so Siri can surface app content with attribution back to the app.

**Source:** https://developer.apple.com/documentation/appintents

### SpotlightSearchTool

FoundationModels.Tool that turns the Core Spotlight index into a retrieval tool for a LanguageModelSession, enabling on-device RAG. Works behind any LanguageModel, not just Apple's system model.

**Source:** https://developer.apple.com/videos/play/wwdc2026/246/

### DynamicProfile

WWDC26 mechanism to declare multiple profiles (model + instructions + tools + modifiers) within a single LanguageModelSession and switch between them as the conversation evolves. Enables on-device model routing.

**Source:** https://developer.apple.com/videos/play/wwdc2026/242/

### coreai-pipelined engine

An alternate Core AI GPU execution engine that fuses decode operations into a pipelined graph, achieving higher throughput than the stock engine. Used by most zoo LLMs. Identified in benchmarks as 'coreai-pipelined'. The stock engine is 'coreai' without pipelining.

**Source:** https://developer.apple.com/documentation/coreai/

### gather_qmm Metal kernel

Custom Metal kernel for grouped-query matrix multiplication used by MoE (Mixture-of-Experts) models on Core AI. Reads only the routed experts instead of the full weight matrix, enabling large MoE models (Qwen3.6-35B, GLM-4.7-Flash, LFM2.5-8B-A1B) to run on iPhone.

**Source:** https://developer.apple.com/documentation/coreai/

### FlowMatch sampler

Host-side sampling loop for flow-matching diffusion models (FLUX.2, LTX-Video, VoxCPM). The neural networks run as Core AI bundles; only the data-dependent control flow (scheduling, timestep iteration) stays on host. The standard zoo pattern: convert heavy nets, keep control flow in Python.

**Source:** https://developer.apple.com/documentation/coreai/

### On-device specialization (AIModelCache)

The on-device first-run compilation of a .aimodel for the specific hardware, managed via AIModelCache / AIModel.specialize(). Converts the portable IR to a compiled graph for the device's GPU/ANE/CPU. AOT-compiled (.aimodelc) bundles skip this step entirely.

**Source:** https://developer.apple.com/documentation/coreai/

### Palettization (k-means LUT)

Apple's term for k-means codebook compression: each weight maps to an index into a LUT of 2^n_bits centroids. Per-channel palettization consistently beats per-channel quantization by ~15-19 dB. Part of coreai-optimization (coreai-opt).

**Source:** https://github.com/apple/coreai-optimization

### @Generable

Foundation Models macro for guided/structured generation: annotated Swift structs produce a JSON schema that constrains model decoding. Works with LanguageModelSession. Requires engine logits, so GPU-pipelined bundles need the adapter path.

**Source:** https://developer.apple.com/documentation/FoundationModels

### Host-cache KV workaround

Beta workaround for the MPSGraph in-graph KV-write bug (FB23024751): express the KV cache as model input/output instead of a Core AI state, append with torch.cat, attend with masked SDPA, and write the new column back on the host between steps. Superseded by the input-mask escape and pipelined engine for dynamic models.

**Source:** https://github.com/apple/coreai-models/issues/5

### Flash-decode Metal kernel

Custom Metal kernel that replaces the stock MPSGraph SDPA for full-attention models with ≥16 heads × head_dim 512. The stock SDPA overflows the GPU scratch heap on large Q tensors. Required by Gemma 4 12B/31B dense models to run on the pipelined engine.

**Source:** https://github.com/apple/coreai-models/issues/27

## Artifact formats

### aimodel format

On-device artifact format produced by Core AI from a PyTorch or open model; auto-specializes to the current hardware and OS version on first load (model cache).

**Source:** https://developer.apple.com/documentation/coreai/

### mlpackage format

Core ML model package format.

**Source:** https://developer.apple.com/documentation/coreml

### safetensors format

Open tensor-serialization format commonly used for original open-model weights on Hugging Face.

**Source:** https://github.com/huggingface/safetensors

### Core AI IR (.mlirb)

The intermediate representation produced by coreai-torch's TorchConverter. Stored as main.mlirb inside the .aimodel bundle, alongside metadata.json and main.hash. The IR is lowered by the Core AI compiler to GPU/ANE/CPU code.

**Source:** https://developer.apple.com/documentation/coreai/

### LanguageBundle

Directory structure for LLM .aimodel bundles: metadata.json (kind 'llm', assets.main, language.{tokenizer,vocab_size,max_context_length,function_map}) + tokenizer/ + the .aimodel. Required by the pipelined engine and Foundation Models integration.

**Source:** https://developer.apple.com/documentation/coreai/

### .aimodelc (AOT-compiled bundle)

Ahead-of-time compiled output of a .aimodel for a specific hardware architecture. Produced by 'xcrun coreai-build compile'. Embeds the precompiled MPSGraph so load is near-instant. Required for iOS deployment of large models. Architecture named by GPU family (e.g. h18p = iPhone 17/18 class).

**Source:** https://developer.apple.com/documentation/coreai/

## Developer tools

### Core ML Tools

Python package for converting models from training frameworks to Core ML.

**Source:** https://github.com/apple/coremltools

### Core AI PyTorch Extensions

Core AI tooling that converts prepared PyTorch models into the .aimodel format.

**Source:** https://developer.apple.com/videos/play/wwdc2026/325/

### Core AI Debugger

App for visualization and numeric debugging of Core AI models, tracing tensor values back to Python source.

**Source:** https://developer.apple.com/videos/play/wwdc2026/325/

### CoreAIKit GraphModel

CoreAIKit abstraction for running multi-graph models (encoders, transducers) as stateless .aimodel bundles via AIModel.run, without the full LLM runtime. Used by non-LLM models like Parakeet TDT, ColModernVBERT, YOLOX.

**Source:** https://developer.apple.com/documentation/coreai/

### AOT compilation (.aimodelc)

Ahead-of-time compilation of a Core AI .aimodel bundle into a .aimodelc for a specific hardware architecture (e.g. h18p for iPhone 17/18). Required when the model graph is too large to specialize on-device within reasonable time. Compiled via 'xcrun coreai-build compile --preferred-compute gpu --architecture h18p'.

**Source:** https://developer.apple.com/documentation/coreai/

### Core AI Instruments

Instruments template for profiling Core AI inference and specialization timing. Pairs with the Core AI Debugger (graph visualization) and the in-Xcode debug gauge (streaming Core AI activity).

**Source:** https://developer.apple.com/documentation/coreai/

