# Artifact Provenance

Generated/curated view over `artifacts/` and encoded artifact manifests.

| Area | File | Notes |
|---|---|---|
| Artifact fields | `artifacts/README.md` | Defines GitHub/HF provenance fields. |
| Official Qwen | `artifacts/official-qwen.yaml` | Apple/Core AI recipe provenance for Qwen official artifacts. |
| Official Gemma | `artifacts/official-gemma.yaml` | Apple/Core AI recipe provenance for Gemma official artifacts. |
| Official Mistral | `artifacts/official-mistral.yaml` | Apple/Core AI recipe provenance for Mistral official artifact. |
| Qwen 3.5 zoo | `artifacts/q35.yaml` | Community zoo artifact references. |
| Qwen 3.6 27B zoo | `artifacts/q36-27b.yaml` | Community zoo artifact reference. |
| Qwen 3.6 MoE zoo | `artifacts/q36-moe.yaml` | Community zoo artifact reference. |
| Encoded manifest | `data/artifacts.yaml.b64.part1` | Partial encoded canonical manifest created when direct writes were blocked. |

## Target end state

The final structure should consolidate these records into a single `artifacts.yaml` with one artifact record per model ID.

Recommended shape:

```yaml
artifacts:
  - id: qwen3-5-0-8b
    group: zoo
    github:
      owner: john-rocky
      repo: coreai-model-zoo
    huggingface:
      owner: mlboydaisuke
      repo: qwen3.5-0.8B-CoreAI
    is_official_recipe: false
```
