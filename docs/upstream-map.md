# Upstream Map

`upstreams.yaml` separates source entities by their role in the catalog.

## Source layers

| Layer | File/category | Purpose |
|---|---|---|
| Framework | `framework_sources` | Apple Core AI, Core ML, Core ML Tools and official runtime/tooling context. |
| Conversion | `conversion_sources` | Repositories that convert, package or document Core AI artifacts. |
| Artifact host | `artifact_hosts` | Hugging Face accounts or other artifact hosting locations. |
| Benchmark | `benchmark_sources` | Benchmark repositories and raw performance provenance. |
| Samples | `sample_sources` | App/runtime usage examples. |
| Original model | `original_model_sources` | Original creators and upstream model family sources. |
| License | `license_sources` | License documents and review state. |

## Why this is separate from `artifacts.yaml`

`artifacts.yaml` answers: where is the converted artifact hosted?

`upstreams.yaml` answers: who created the original model family, what framework/tooling validates the runtime, and what license/source should be reviewed?

## Trust levels

| Trust value | Meaning |
|---|---|
| `official_primary` | Official source from Apple or original model owner. |
| `community_primary` | Primary community source used by this catalog. |
| `artifact_host` | Host of converted artifacts, not necessarily original creator. |
| `original_model_primary` | Original model family owner/source. |
| `license_primary` | Primary license text or license authority. |
| `needs_review` | Placeholder until exact source is verified. |

## Highest priority additions

The most important missing layer was original-model attribution. That is now represented for Qwen, Gemma, gpt-oss, Mistral, Granite, LFM, MiniCPM/VoxCPM, SAM, FLUX, Whisper, RF-DETR, Depth Anything, Kokoro and several review-needed families.

## Review-needed upstreams

These entries still require exact primary-source verification before being marked high-confidence:

- GLM-4.7-Flash
- Nanbeige4.1-3B
- AdcSR ×4
- Unlimited-OCR
- OpenRAIL-style license source for AdcSR

## Maintenance rule

Do not put all upstream links directly into `catalog.yaml`. Keep model facts in `catalog.yaml`, converted artifact provenance in `artifacts.yaml`, and source taxonomy in `upstreams.yaml`.
