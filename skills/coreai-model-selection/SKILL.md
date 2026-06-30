# Core AI Model Selection

## When to use
Use this skill when asked to recommend, select, or evaluate Apple Core AI models for a specific use case, device target, or constraint set.

## Prerequisites
The CoreAI Catalog must be available at the working directory or installed via `pip install -e .`.

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

5. **Rank by readiness score.** Higher score = more deployable:
   - A (85-100): Production-ready, stock runtime, benchmarked
   - B (70-84): Good, minor caveats
   - C (55-69): Usable but needs verification
   - D-F (<55): Experimental, missing data, or heavy requirements

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
