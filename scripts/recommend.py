#!/usr/bin/env python3
"""
Core AI Catalog recommendation engine — recommends model candidates
for a given task and optional device target.

Usage:
  python scripts/recommend.py --task "robot vision" --device iphone
  python scripts/recommend.py --task "private on-device OCR" --device iphone
  python scripts/recommend.py --task "on-device RAG"
  python scripts/recommend.py --task "voice assistant" --device mac
  python scripts/recommend.py --json --task "object detection"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


# Task → capability mapping
TASK_MAP: dict[str, list[str]] = {
    "robot vision": ["object-detection", "vision-language", "monocular-depth", "promptable-segmentation"],
    "object detection": ["object-detection"],
    "segmentation": ["instance-segmentation", "promptable-segmentation"],
    "private chat": ["chat", "text-generation"],
    "chat": ["chat", "text-generation"],
    "on-device rag": ["embedding", "reranking", "chat"],
    "rag": ["embedding", "reranking", "chat"],
    "embedding": ["embedding"],
    "voice assistant": ["speech-to-text", "text-to-speech", "chat"],
    "speech to text": ["speech-to-text"],
    "asr": ["speech-to-text"],
    "transcription": ["speech-to-text"],
    "text to speech": ["text-to-speech"],
    "tts": ["text-to-speech"],
    "private on-device ocr": ["document-ocr", "vision-language"],
    "ocr": ["document-ocr", "vision-language"],
    "document ocr": ["document-ocr"],
    "image generation": ["image-generation"],
    "text to image": ["image-generation"],
    "super resolution": ["super-resolution"],
    "upscale": ["super-resolution"],
    "depth estimation": ["monocular-depth"],
    "monocular depth": ["monocular-depth"],
    "vision language": ["vision-language"],
    "vlm": ["vision-language"],
    "audio understanding": ["audio-understanding"],
    "music generation": ["music-generation", "text-to-audio"],
    "text to audio": ["text-to-audio"],
    "text to video": ["text-to-video"],
    "gui grounding": ["gui-grounding"],
    "computer use": ["gui-grounding"],
    "robotics": ["vision-language-action", "robotics"],
    "vla": ["vision-language-action"],
    "image to 3d": ["image-to-3d"],
    "3d generation": ["image-to-3d"],
    "image text similarity": ["image-text-similarity"],
    "clip": ["image-text-similarity"],
    "code agent": ["agentic", "chat"],
    "agentic": ["agentic"],
    "reasoning": ["reasoning", "chat"],
    "diffusion lm": ["diffusion-lm"],
    "speculative decoding": ["speculative-decoding"],
}


def resolve_task(task: str) -> list[str]:
    """Resolve a free-text task to a list of capabilities."""
    lower = task.lower().strip()

    # Direct match
    if lower in TASK_MAP:
        return TASK_MAP[lower]

    # Fuzzy: find all task keys that are substrings of the query or vice versa
    matches = set()
    for key, caps in TASK_MAP.items():
        if key in lower or lower in key:
            matches.update(caps)

    if matches:
        return list(matches)

    # Last resort: treat the task itself as a capability name
    return [lower.replace(" ", "-")]


def score_for_ranking(model: dict, has_benchmark: bool, device_filter: str | None) -> int:
    """Quick ranking score biased toward deployability."""
    score = 0
    if model.get("artifact", {}).get("availability") == "available":
        score += 15
    if model.get("license", {}).get("commercial_use") == "likely":
        score += 10
    if has_benchmark:
        score += 15
    if model.get("status") == "confirmed":
        score += 10
    rt = model.get("runtime", {})
    if rt.get("stock_runtime") is True:
        score += 10
    if rt.get("patch_required") is False:
        score += 5
    if rt.get("custom_kernel") is False:
        score += 5
    if model.get("confidence") == "high":
        score += 10
    elif model.get("confidence") == "medium":
        score += 5

    # Device preference
    ds = model.get("device_support", {})
    if device_filter:
        if ds.get(device_filter) is True:
            score += 15
        elif ds.get(device_filter) is False:
            score -= 20  # penalize models that don't support the target device

    # Maturity bonus
    if model.get("maturity") in ("stable", "active"):
        score += 5

    return score


def main() -> int:
    parser = argparse.ArgumentParser(description="Get model recommendations for a task")
    parser.add_argument("--task", "-t", required=True, help="Task description (e.g. 'robot vision', 'private chat', 'OCR')")
    parser.add_argument("--device", "-d", help="Target device (iphone, mac)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--limit", type=int, default=5, help="Max recommendations (default 5)")
    args = parser.parse_args()

    catalog = read_yaml(ROOT / "catalog.yaml")
    benchmarks = read_yaml(ROOT / "benchmarks.yaml")
    artifacts = read_yaml(ROOT / "artifacts.yaml")

    models = catalog.get("models", [])
    benched_ids = {b["model_id"] for b in benchmarks.get("benchmarks", [])}
    art_by_id = {a["id"]: a for a in artifacts.get("artifacts", [])}

    # Resolve task → capabilities
    capabilities = resolve_task(args.task)

    # Filter and score
    candidates = []
    for m in models:
        model_caps = {c.lower() for c in m.get("capabilities", [])}
        matched = model_caps & {c.lower() for c in capabilities}
        if not matched:
            continue

        # Device filter (hard filter if device specified)
        if args.device:
            ds = m.get("device_support", {})
            if ds.get(args.device.lower()) is not True:
                continue

        score = score_for_ranking(m, m["id"] in benched_ids, args.device.lower() if args.device else None)
        candidates.append({
            "id": m["id"],
            "name": m["name"],
            "family": m["family"],
            "matched_capabilities": sorted(matched),
            "score": score,
            "has_benchmark": m["id"] in benched_ids,
            "device_support": m.get("device_support", {}),
            "license": m.get("license", {}).get("name", ""),
            "commercial_use": m.get("license", {}).get("commercial_use"),
            "artifact_url": art_by_id.get(m.get("artifact_ref"), {}).get("huggingface", {}).get("url", ""),
            "notes": m.get("notes", ""),
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    candidates = candidates[: args.limit]

    if args.json:
        print(json.dumps({
            "task": args.task,
            "resolved_capabilities": capabilities,
            "device": args.device,
            "count": len(candidates),
            "recommendations": candidates,
        }, indent=2, ensure_ascii=False))
    else:
        if not candidates:
            print(f"No models found for task '{args.task}'.")
            print(f"Resolved capabilities: {capabilities}")
            return 0

        print(f"\n  Task: {args.task}")
        print(f"  Capabilities matched: {', '.join(capabilities)}")
        if args.device:
            print(f"  Device: {args.device}")
        print(f"\n  Recommended models ({len(candidates)}):\n")

        for i, r in enumerate(candidates, 1):
            ds = r["device_support"]
            devices = []
            if ds.get("iphone") is True:
                devices.append("iPhone")
            if ds.get("ipad") is True:
                devices.append("iPad")
            if ds.get("mac") is True:
                devices.append("Mac")
            bench = "📊 benchmarked" if r["has_benchmark"] else "not benchmarked"
            lic = r["license"]
            print(f"  {i}. {r['name']}")
            print(f"     ID: {r['id']}")
            print(f"     Runs on: {'/'.join(devices) or 'unknown'}")
            print(f"     License: {lic} ({'likely commercial' if r['commercial_use'] == 'likely' else 'check license'})")
            print(f"     {bench}")
            if r["notes"]:
                # Show first 120 chars of notes
                note = r["notes"][:120].replace("\n", " ")
                if len(r["notes"]) > 120:
                    note += "…"
                print(f"     Note: {note}")
            print()

        if candidates:
            print("  Next steps:")
            print(f"    python scripts/query.py --capability {candidates[0]['matched_capabilities'][0]}")
            print(f"    python scripts/show.py {candidates[0]['id']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
