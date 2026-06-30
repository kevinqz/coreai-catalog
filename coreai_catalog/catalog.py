"""
Core AI Catalog data layer — loads YAML sources and provides query access.

This module bridges the CLI to the catalog's YAML source-of-truth.
It can work with either the local checkout or a pip-installed package
(with pre-generated JSON bundled as data).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def _find_catalog_root() -> Path:
    """Find the catalog root (where catalog.yaml lives)."""
    # Try CWD first
    cwd = Path.cwd()
    if (cwd / "catalog.yaml").exists():
        return cwd
    # Try relative to this file (development mode)
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "catalog.yaml").exists():
            return p
        p = p.parent
    # Fall back to CWD anyway
    return cwd


class Catalog:
    """In-memory catalog with joined access to all entities."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _find_catalog_root()
        self._loaded = False
        self._models: list[dict] = []
        self._artifacts: list[dict] = []
        self._benchmarks: list[dict] = []
        self._terms: list[dict] = []
        self._sources: list[dict] = []
        self._art_by_id: dict[str, dict] = {}
        self._bench_by_model: dict[str, list[dict]] = {}

    def _load(self) -> None:
        if self._loaded:
            return

        def read_yml(name: str) -> dict:
            path = self.root / f"{name}.yaml"
            if path.exists():
                return yaml.safe_load(path.read_text()) or {}
            return {}

        cat = read_yml("catalog")
        art = read_yml("artifacts")
        bench = read_yml("benchmarks")
        terms = read_yml("terms")
        sources = read_yml("sources")

        self._models = cat.get("models", [])
        self._artifacts = art.get("artifacts", [])
        self._benchmarks = bench.get("benchmarks", [])
        self._terms = terms.get("terms", [])
        self._sources = sources.get("sources", [])

        self._art_by_id = {a["id"]: a for a in self._artifacts if "id" in a}
        self._bench_by_model = {}
        for b in self._benchmarks:
            mid = b.get("model_id", "")
            self._bench_by_model.setdefault(mid, []).append(b)

        self._loaded = True

    @property
    def models(self) -> list[dict]:
        self._load()
        return self._models

    @property
    def artifacts(self) -> list[dict]:
        self._load()
        return self._artifacts

    @property
    def benchmarks(self) -> list[dict]:
        self._load()
        return self._benchmarks

    @property
    def terms(self) -> list[dict]:
        self._load()
        return self._terms

    def get_model(self, model_id: str) -> dict | None:
        """Find a model by ID (case-insensitive)."""
        self._load()
        lower = model_id.lower()
        for m in self._models:
            if m["id"].lower() == lower:
                return m
        return None

    def get_artifact(self, model_id: str) -> dict | None:
        """Get the artifact record for a model."""
        self._load()
        model = self.get_model(model_id)
        if not model:
            return None
        ref = model.get("artifact_ref", "")
        return self._art_by_id.get(ref)

    def get_benchmarks(self, model_id: str) -> list[dict]:
        """Get benchmark records for a model."""
        self._load()
        return self._bench_by_model.get(model_id, [])

    def search(
        self,
        capability: str | None = None,
        device: str | None = None,
        license_type: str | None = None,
        family: str | None = None,
        source_group: str | None = None,
        modality: str | None = None,
    ) -> list[dict]:
        """Filter models by criteria. Returns list of model dicts."""
        self._load()
        results = []
        for m in self._models:
            if capability:
                caps = [c.lower() for c in m.get("capabilities", [])]
                if capability.lower() not in caps:
                    continue
            if device:
                ds = m.get("device_support", {})
                val = ds.get(device.lower())
                if val is not True:
                    continue
            if license_type:
                if m.get("license", {}).get("commercial_use") != license_type:
                    continue
            if family:
                if m.get("family", "").lower() != family.lower():
                    continue
            if source_group:
                if m.get("source_group") != source_group:
                    continue
            if modality:
                inp = [x.lower() for x in m.get("modalities", {}).get("input", [])]
                out = [x.lower() for x in m.get("modalities", {}).get("output", [])]
                if modality.lower() not in inp and modality.lower() not in out:
                    continue
            results.append(m)
        # Sort by readiness score descending so best models appear first
        results.sort(key=lambda m: self.readiness_score(m), reverse=True)
        return results

    def readiness_score(self, model: dict) -> int:
        """Calculate 0-100 readiness score for a model."""
        has_bench = bool(self._bench_by_model.get(model.get("id", "")))
        score = 0
        if model.get("artifact", {}).get("availability") == "available":
            score += 15
        if model.get("license", {}).get("commercial_use") == "likely":
            score += 10
        if model.get("device_support", {}).get("iphone") is True:
            score += 10
        if model.get("device_support", {}).get("mac") is True:
            score += 10
        if has_bench:
            score += 10
        rt = model.get("runtime", {})
        if rt.get("stock_runtime") is True:
            score += 10
        if rt.get("custom_kernel") is False:
            score += 5
        if rt.get("patch_required") is False:
            score += 5
        if rt.get("aot_required") is False:
            score += 5
        if model.get("status") == "confirmed":
            score += 10
        conf = model.get("confidence", "")
        if conf == "high":
            score += 5
        elif conf == "medium":
            score += 3
        elif conf == "low":
            score -= 10
        if model.get("maturity") in ("stable", "active"):
            score += 5
        return max(0, min(100, score))


# Task → capability mapping (shared with recommend.py)
TASK_MAP: dict[str, list[str]] = {
    "robot vision": ["object-detection", "vision-language", "monocular-depth", "promptable-segmentation"],
    "object detection": ["object-detection"],
    "segmentation": ["instance-segmentation", "promptable-segmentation"],
    "private chat": ["chat", "text-generation"],
    "chat": ["chat", "text-generation"],
    "llm": ["chat", "text-generation"],
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
}


def resolve_task(task: str) -> list[str]:
    """Resolve a free-text task to a list of capabilities."""
    lower = task.lower().strip()
    if lower in TASK_MAP:
        return TASK_MAP[lower]
    matches = set()
    for key, caps in TASK_MAP.items():
        if key in lower or lower in key:
            matches.update(caps)
    return list(matches) if matches else [lower.replace(" ", "-")]
