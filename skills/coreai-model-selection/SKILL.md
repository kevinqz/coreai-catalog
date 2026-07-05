# Core AI Model Selection

## When to use
Use this skill when asked to recommend, select, or evaluate Apple Core AI models for a specific use case, device target, or constraint set.

## Prerequisites
The Core AI Catalog must be available at the working directory or installed via `pip install -e .`.

## Procedure

1. **Clarify the task.** Identify the primary capability needed:
   - `chat` / `text-generation` — conversational LLMs
   - `vision-language` — image+text understanding (VLMs)
   - `speech-to-text` — transcription / ASR
   - `text-to-speech` — TTS
   - `object-detection` — bounding box detection
   - `embedding` — RAG / semantic search
   - `image-generation` — text-to-image
   - `super-resolution` — upscaling
   - `monocular-depth` — depth estimation
   - `promptable-segmentation` / `instance-segmentation` — masks

2. **Filter by device.** Ask or infer the target:
   - `iphone` — must run on iOS (constrains size and architecture)
   - `mac` — can run larger models (Mac-only MoE, 27B+)

3. **Check license.** If commercial use is intended, filter by `commercial_use: likely`.

4. **Use the catalog tools.**
   ```bash
   coreai-catalog recommend --task "<task>" --device <device>
   coreai-catalog search --capability <cap> --device <device> --license likely
   ```

5. **Filter, then rank on facets — not `readiness_score`** (deprecated: blind to
   model quality, see `docs/concepts/suitability-facets.md`).
   - **Gate** on `deployability`: `obtainable == available`, the target device in
     `device_fit` not `false` (keep `unknown`), and `license.commercial_use` when
     commercial use is required.
   - **Rank** survivors by a user-relevant axis: size/latency for on-device, or
     `lifecycle.stage` (official > verified > community > experimental) for trust.
   - **Quality** → compare **benchmark values** for the task; if `measured` is
     false, say the model is unbenchmarked rather than guessing.

6. **Present results.** For each recommendation, surface:
   - Model name and ID
   - Why it matches (capabilities)
   - Devices supported
   - License and commercial use status
   - Benchmark data (if available)
   - Caveats (custom kernel? patch required? AOT?)
   - Install command: `coreai-catalog install <id>`

## Rules

- **Never fabricate specifications.** If a field is `unknown`, report it as unknown.
- **Always cite provenance.** Mention whether it's zoo, official, or external.
- **Prefer benchmarked models** when performance matters.
- **Surface license risk** explicitly — `check_license` means review is needed.
- **Explain officiality precisely:**
  - `apple_export_recipe: true` → Apple official recipe conversion
  - `community_packaged: true` → Community zoo port
  - Neither → Independent converter
