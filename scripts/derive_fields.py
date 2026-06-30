#!/usr/bin/env python3
"""
Derive missing catalog fields from existing data — no upstream collection needed.

Transformations:
  1. ARCHITECTURE: infer from runner field
  2. CONTEXT_WINDOW: extract from notes where mentioned
  3. STREAMING: infer from model type (chat/text-gen vs detection/segmentation/image)
  4. BENCHMARK PRECISION: fill not_published from model's catalog precision
  5. BENCHMARK higher_is_better: derive from metric type

Uses ruamel.yaml to preserve formatting/comments in source YAML.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[1]

# ── 1. Architecture mapping from runner ──
RUNNER_TO_ARCH = {
    "CoreAIRunner": "transformer",
    "CoreAIDiffusionPipeline": "diffusion",
    "CoreAIImageSegmenter": "cnn/transformer",
    "CoreAITranscribe": "transformer",
    "CoreAIVideoPipeline": "diffusion",
    "CoreAIKit-GraphModel": "encoder",
    "stock-runner": "transformer",  # stock-runner is used by LLMs + OCR; default to transformer
    "unknown": "unknown",
}

# ── 2. Context window extraction patterns ──
# Matches: "128K context", "32K context", "4096 context", "128k context window", "context of 128K"
CONTEXT_PATTERNS = [
    re.compile(r"(\d+(?:[.,]\d+)?)\s*([KkMm])\s*(?:context|token|tok|window|ctx)", re.IGNORECASE),
    re.compile(r"(?:context|window|ctx)\s*(?:of\s*)?:?\s*(\d+(?:[.,]\d+)?)\s*([KkMm])", re.IGNORECASE),
    re.compile(r"(\d{4,6})\s*(?:context|token|tok)", re.IGNORECASE),
]


def extract_context_window(notes: str) -> str | None:
    """Extract context window mention from notes text."""
    if not notes:
        return None
    for pat in CONTEXT_PATTERNS:
        match = pat.search(notes)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                num, suffix = groups
                suffix = suffix.upper()
                # Normalize: remove decimal for clean K values
                if suffix == "K":
                    # e.g., "128K"
                    if "." in num:
                        num = str(int(float(num)))
                    return f"{num}K"
                elif suffix == "M":
                    if "." in num:
                        num = str(int(float(num)))
                    return f"{num}M"
            elif len(groups) == 1:
                num = groups[0]
                # Raw token count like 4096
                return num
    return None


# ── 3. Streaming inference ──
# Chat/text-generation models (and anything that streams text/token output) get streaming=true
# Detection, segmentation, image, embedding, depth, etc. get streaming=false
STREAMING_TRUE_CAPS = {
    "chat", "text-generation", "diffusion-lm", "hybrid-llm",
    "vision-language", "audio-understanding",
    "text-to-speech", "music-generation", "text-to-audio",
}

STREAMING_FALSE_CAPS = {
    "object-detection", "instance-segmentation", "promptable-segmentation",
    "monocular-depth", "image-generation", "super-resolution",
    "document-ocr", "embedding", "reranking", "image-to-3d",
    "image-text-similarity", "visual-document-retrieval", "gui-grounding",
    "text-to-video", "vision-language-action", "robotics",
    "image-to-3d", "speculative-decoding",
    "speech-to-text",  # ASR via CoreAITranscribe is non-streaming by default
}


def infer_streaming(capabilities: list[str], runner: str, modalities: dict) -> bool:
    """Infer streaming support from capabilities and runner type."""
    caps = set(capabilities)

    # Chat/text-generation with CoreAIRunner = streaming
    if runner == "CoreAIRunner":
        if caps & STREAMING_TRUE_CAPS:
            return True
        # CoreAIRunner with speech-to-text (qwen3-asr, vibevoice-asr) — these are token-based, streaming
        if "speech-to-text" in caps:
            return True
        # TTS via CoreAIRunner
        if "text-to-speech" in caps:
            return True
        # Embedding, reranking — no streaming
        if caps & STREAMING_FALSE_CAPS:
            return False
        # Vision models that produce text via CoreAIRunner (vl models) — streaming decode
        if "vision-language" in caps or caps & {"gui-grounding", "vision-language-action"}:
            # holo2-4b outputs coordinates, not streaming text
            out = set(modalities.get("output", []))
            if out <= {"coordinates", "action-tokens"}:
                return False
            return True
        # Default for CoreAIRunner text models
        return True

    # stock-runner LLMs also support streaming
    if runner == "stock-runner":
        if caps & {"chat", "text-generation"}:
            return True
        # unlimited-ocr is detection-like
        return False

    # Diffusion, image segmenter, video pipeline — no streaming
    if runner in ("CoreAIDiffusionPipeline", "CoreAIImageSegmenter", "CoreAIVideoPipeline"):
        return False

    # Transcribe — non-streaming by default (batch transcribe)
    if runner == "CoreAITranscribe":
        return False

    # Graph models (encoder/retrieval) — no streaming
    if runner == "CoreAIKit-GraphModel":
        return False

    return False


# ── 5. Benchmark precision from model ──
def get_model_precision(models_by_id: dict, model_id: str) -> str | None:
    model = models_by_id.get(model_id)
    if model:
        return model.get("size", {}).get("precision")
    return None


# ── 6. higher_is_better from metric ──
HIGHER_IS_BETTER_METRICS = {
    "decode_throughput",      # tokens_per_second — higher is better
    "realtime_factor",        # RTF — higher means faster than realtime, so higher is better
}
# All latency metrics → lower is better (higher_is_better=False)
# memory_footprint → lower is better


def infer_higher_is_better(metric: str) -> bool:
    return metric in HIGHER_IS_BETTER_METRICS


def main() -> int:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096  # Prevent line wrapping

    # ── Process catalog.yaml ──
    catalog_path = ROOT / "catalog.yaml"
    with open(catalog_path) as f:
        catalog = yaml.load(f)

    models = catalog["models"]
    arch_count = 0
    ctx_count = 0
    stream_count = 0

    for m in models:
        runner = m["runtime"]["runner"]

        # 1. Add architecture field
        arch = RUNNER_TO_ARCH.get(runner, "unknown")
        if "architecture" not in m:
            m["architecture"] = arch
            arch_count += 1

        # 2. Extract context window from notes
        notes = m.get("notes") or ""
        ctx = extract_context_window(notes)
        if ctx and "context_window" not in m:
            m["context_window"] = ctx
            ctx_count += 1

        # 3. Infer streaming
        if "streaming" not in m:
            caps = m.get("capabilities", [])
            modalities = m.get("modalities", {})
            m["streaming"] = infer_streaming(caps, runner, modalities)
            stream_count += 1

    with open(catalog_path, "w") as f:
        yaml.dump(catalog, f)

    print(f"Catalog: added architecture to {arch_count} models, "
          f"context_window to {ctx_count} models, "
          f"streaming to {stream_count} models")

    # ── Process benchmarks.yaml ──
    bench_path = ROOT / "benchmarks.yaml"
    with open(bench_path) as f:
        bench_data = yaml.load(f)

    # Build model lookup from catalog (re-read to get updated data)
    models_by_id = {m["id"]: m for m in models}

    benchmarks = bench_data["benchmarks"]
    prec_count = 0
    hib_count = 0

    for b in benchmarks:
        # 5. Fill precision from model if not_published
        if b.get("precision") == "not_published":
            model_prec = get_model_precision(models_by_id, b["model_id"])
            if model_prec:
                b["precision"] = f"inferred:{model_prec}"
                prec_count += 1

        # 6. Add higher_is_better
        if "higher_is_better" not in b:
            b["higher_is_better"] = infer_higher_is_better(b["metric"])
            hib_count += 1

    with open(bench_path, "w") as f:
        yaml.dump(bench_data, f)

    print(f"Benchmarks: inferred precision for {prec_count} records, "
          f"added higher_is_better to {hib_count} records")

    return 0


if __name__ == "__main__":
    sys.exit(main())
