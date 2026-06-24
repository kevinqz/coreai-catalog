# Credits

Core AI Catalog is a source-grounded catalog built on top of public upstream sources.

## GitHub credits

| Role | User / organization | Repository | Link |
|---|---|---|---|
| Primary upstream model zoo and knowledge base | `john-rocky` | `john-rocky/coreai-model-zoo` | https://github.com/john-rocky/coreai-model-zoo |
| Predecessor project referenced by upstream | `john-rocky` | `john-rocky/CoreML-Models` | https://github.com/john-rocky/CoreML-Models |
| Official Apple recipes | `apple` | `apple/coreai-models` | https://github.com/apple/coreai-models |
| Raw benchmark data referenced by upstream official docs | `john-rocky` | `john-rocky/apple-silicon-llm-bench` | https://github.com/john-rocky/apple-silicon-llm-bench |
| Mac chat samples referenced by upstream official docs | `john-rocky` | `john-rocky/coreai-samples` | https://github.com/john-rocky/coreai-samples |
| This catalog | `kevinqz` | `kevinqz/coreai-catalog` | https://github.com/kevinqz/coreai-catalog |

## Hugging Face credits

| Role | User | Link |
|---|---|---|
| Converted Apple Core AI artifact publisher used by upstream | `mlboydaisuke` | https://huggingface.co/mlboydaisuke |

## Artifact links

See [`docs/huggingface-links.md`](./docs/huggingface-links.md) for every Hugging Face artifact URL currently mapped in this catalog.

## Attribution policy

- `catalog.yaml` remains the main model registry.
- `artifacts.yaml` stores per-model GitHub and Hugging Face provenance.
- Official entries are marked with `official_apple_recipe_conversion: true` in `artifacts.yaml`.
- Community zoo entries are marked with `official_apple_recipe_conversion: false`.
- Unknown fields should stay `unknown` until verified from primary sources.
