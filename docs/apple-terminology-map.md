# Apple Terminology Map

Generated from `terms.yaml`. Verified Apple AI terminology, grouped by ecosystem layer.

Every term cites an official Apple source. This is a reference layer, not legal or affiliation claims; see the README scope and disclaimer.

## System surfaces

| Term | Definition | Verification | Source |
|---|---|---|---|
| Apple Intelligence | Personal intelligence system across Apple devices, powered by Apple Foundation Models; provides personal context, app actions and on-screen awareness. | established_pre_2026 | [link](https://developer.apple.com/apple-intelligence/) |
| Image Playground | Image-generation experience and developer API in the Apple Intelligence ecosystem. | established_pre_2026 | [link](https://developer.apple.com/documentation/imageplayground) |
| Visual Intelligence | System visual-understanding capability; the 2026 update adds image input to the on-device model for on-device visual tasks. | confirmed_wwdc2026 | [link](https://developer.apple.com/apple-intelligence/whats-new/) |

## Developer frameworks

| Term | Definition | Verification | Source |
|---|---|---|---|
| App Intents | Framework that connects app content and actions to Apple Intelligence, Siri and Spotlight through schemas, entities and intents. | established_pre_2026 | [link](https://developer.apple.com/documentation/appintents) |
| Core AI | WWDC26 framework for bringing PyTorch models to production on Apple Silicon (LLMs and generative AI); successor to Core ML for generative AI; exports the .aimodel format. | confirmed_wwdc2026 | [link](https://developer.apple.com/documentation/coreai/) |
| Core ML | Framework for integrating traditional ML models into apps; predates Core AI and is superseded by it for generative AI; uses .mlpackage / .mlmodel. | established_pre_2026 | [link](https://developer.apple.com/documentation/coreml) |
| Evaluations framework | WWDC26 Swift framework to measure the quality of intelligence features and quantify the statistical impact of prompt changes. | confirmed_wwdc2026 | [link](https://developer.apple.com/apple-intelligence/whats-new/) |
| Foundation Models framework | Native Swift API giving access to Apple Foundation Models (on-device and Private Cloud Compute) and to any provider with a Swift package conforming to the LanguageModel protocol. | confirmed_wwdc2026 | [link](https://developer.apple.com/documentation/FoundationModels) |
| Metal | GPU programming framework; backs the custom Metal kernels some Core AI model conversions require. | established_pre_2026 | [link](https://developer.apple.com/metal/) |
| MLX | Open-source array framework for ML on Apple Silicon (research, training, fine-tuning, inference) with unified memory and lazy evaluation; a parallel research/training layer, not a Core AI dependency. | established_pre_2026 | [link](https://github.com/ml-explore/mlx) |
| Speech | Framework for speech recognition and audio analysis on Apple platforms. | established_pre_2026 | [link](https://developer.apple.com/documentation/speech) |
| Vision | Framework for image analysis such as detection, recognition and tracking; Vision tools can be called by the model during generation. | established_pre_2026 | [link](https://developer.apple.com/documentation/vision) |

## Model providers

| Term | Definition | Verification | Source |
|---|---|---|---|
| Apple Foundation Models | Apple's proprietary models (on-device and server via Private Cloud Compute) that power Apple Intelligence; third generation (AFM 3) at WWDC26; not open weights and not downloadable. | confirmed_wwdc2026 | [link](https://machinelearning.apple.com/research/introducing-third-generation-of-apple-foundation-models) |
| Private Cloud Compute | Apple's privacy-preserving server infrastructure for running larger Foundation Models off-device. | established_pre_2026 | [link](https://security.apple.com/blog/private-cloud-compute/) |

## Provider protocols

| Term | Definition | Verification | Source |
|---|---|---|---|
| LanguageModel protocol | Public Swift protocol a provider implements so any model (Apple, Claude, Gemini, local) can back a LanguageModelSession without changing app logic. | confirmed_wwdc2026 | [link](https://developer.apple.com/videos/play/wwdc2026/339/) |

## AI primitives

| Term | Definition | Verification | Source |
|---|---|---|---|
| Dynamic Profiles | Mechanism to swap models, tools and instructions within a single continuous session so app intelligence adapts in real time. | confirmed_wwdc2026 | [link](https://developer.apple.com/apple-intelligence/whats-new/) |
| LanguageModelSession | Session object that runs prompts and tools against a LanguageModel in the Foundation Models framework. | confirmed_wwdc2026 | [link](https://developer.apple.com/documentation/FoundationModels) |
| Spotlight semantic index | Semantic index that App Intents entity schemas contribute to, so Siri can surface app content with attribution back to the app. | confirmed_wwdc2026 | [link](https://developer.apple.com/documentation/appintents) |
| Tool calling | Model invocation of app-provided tools (including Vision tools) during generation. | confirmed_wwdc2026 | [link](https://developer.apple.com/documentation/FoundationModels) |

## Artifact formats

| Term | Definition | Verification | Source |
|---|---|---|---|
| aimodel format | On-device artifact format produced by Core AI from a PyTorch or open model; auto-specializes to the current hardware and OS version on first load (model cache). | confirmed_wwdc2026 | [link](https://developer.apple.com/documentation/coreai/) |
| mlpackage format | Core ML model package format. | established_pre_2026 | [link](https://developer.apple.com/documentation/coreml) |
| safetensors format | Open tensor-serialization format commonly used for original open-model weights on Hugging Face. | established_pre_2026 | [link](https://github.com/huggingface/safetensors) |

## Developer tools

| Term | Definition | Verification | Source |
|---|---|---|---|
| Core AI Debugger | App for visualization and numeric debugging of Core AI models, tracing tensor values back to Python source. | confirmed_wwdc2026 | [link](https://developer.apple.com/videos/play/wwdc2026/325/) |
| Core AI PyTorch Extensions | Core AI tooling that converts prepared PyTorch models into the .aimodel format. | confirmed_wwdc2026 | [link](https://developer.apple.com/videos/play/wwdc2026/325/) |
| Core ML Tools | Python package for converting models from training frameworks to Core ML. | established_pre_2026 | [link](https://github.com/apple/coremltools) |
