# Model Details

This view summarizes model runtime and config details. The source of truth is `../catalog.yaml`.

| Group | Detail |
|---|---|
| Community zoo models | Source group `zoo`; may require custom kernels, patches or community runtime paths depending on model. |
| Official recipe models | Source group `official`; modeled as stock runtime entries from upstream `official/`. |
| Unknown fields | Marked as `unknown` instead of guessed. |

## High-signal details

| Model / family | Runtime detail | Notes |
|---|---|---|
| Qwen3.5-0.8B | CoreAIRunner, `.aimodel` | iPhone/Mac; benchmark fields included in `catalog.yaml`. |
| Qwen3.6-35B-A3B | custom `gather_qmm` | Mac-only MoE. |
| GLM-4.7-Flash | custom `gather_qmm` | MoE + MLA. |
| Gemma 4 12B / 31B | custom flash-decode | Mac-only large dense models. |
| LFM2.5-8B-A1B | custom `gather_qmm` | MoE path. |
| Unlimited-OCR | stock runtime noted | Outputs markdown/html/latex. |
| Qwen3-Embedding 0.6B | fp16 | Embedding output vector. |
| Qwen3-Reranker 0.6B | fp16 | Query+documents to score. |
| RF-DETR | vision processor required | Object detection, no NMS. |
| RF-DETR-Seg | vision processor required | Instance segmentation variants. |
| Depth Anything 3 | fp16/fp32 | Small/base variants. |
| gpt-oss-20B official | stock runtime | MXFP4, ~13GB. |
| Qwen3 official | stock runtime | 0.6B/4B iPhone+Mac, 8B Mac. |
| FLUX.2 klein | CoreAIDiffusionPipeline | Mac-only image generation. |
| SAM 3 | CoreAIImageSegmenter | iPhone/Mac promptable segmentation. |
| Whisper large-v3-turbo | CoreAITranscribe | iPhone/Mac speech-to-text. |
