# Credits

Core AI Catalog is built on public upstream sources.

## GitHub credits

- john-rocky / coreai-model-zoo
- john-rocky / CoreML-Models
- apple / coreai-models
- apple / coremltools
- john-rocky / apple-silicon-llm-bench
- john-rocky / coreai-samples
- kevinqz / coreai-catalog

## Hugging Face credits

- mlboydaisuke — converted Apple Core AI artifact publisher used by the upstream repository.

## Attribution policy

- `catalog.yaml` is the main model registry.
- `artifacts.yaml` records artifact provenance and download references.
- Official-recipe entries use `source_group: official` and `officiality.apple_export_recipe: true`.
- Community-port entries use `source_group: zoo` and `officiality.apple_export_recipe: false`.
- `officiality.apple_hosted_artifact` is `false` for all current entries: artifacts are community-packaged (`mlboydaisuke`), not hosted by Apple.
- Unknown fields stay `unknown` until verified from primary sources.
