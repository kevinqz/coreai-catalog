"""
Core AI Catalog data layer — loads YAML sources and provides query access.

This module bridges the CLI to the catalog's YAML source-of-truth.
It can work with either the local checkout or a pip-installed package
(with pre-generated JSON bundled as data).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml


def _parse_params(val) -> float:
    """Parse a parameter string into a float (in billions) for sorting.

    Handles standard formats ('2B', '350M'), compound formats
    ('35B / ~3B active', '20B / ~13GB'), effective-parameter formats
    ('E2B', 'E4B'), size tiers ('nano', 'small', 'large'), and
    weight-only descriptors ('~1.7GB', '809M / ~1.5GB').
    Returns float('inf') for unparseable or unknown values.
    """
    if not val or val == "unknown" or val == "not_published":
        return float("inf")
    s = str(val).strip().upper()

    # Size tier estimation (common for detection/segmentation models)
    _SIZE_TIERS = {
        "NANO": 0.05, "TINY": 0.08,
        "SMALL": 0.15, "BASE": 0.3,
        "MEDIUM": 0.5, "LARGE": 1.0,
        "XLARGE": 2.0, "2XLARGE": 4.0,
    }
    if s in _SIZE_TIERS:
        return _SIZE_TIERS[s]

    # Effective-parameter format: 'E2B' → 2.0, 'E4B' → 4.0
    if s.startswith("E") and s.endswith("B"):
        try:
            return float(s[1:-1])
        except ValueError:
            pass

    # 'sub-2B' → 1.5 (slightly under 2B)
    if s.startswith("SUB-") and s.endswith("B"):
        try:
            return float(s[4:-1]) * 0.75
        except ValueError:
            pass

    # Compound formats: extract the first parameter count
    # '35B / ~3B active' → 35.0, '20B / ~13GB' → 20.0, '809M / ~1.5GB' → 0.809
    # '2B / DiT 1.9B + T5-XXL 4.76B' → 2.0, '2B (BitNet b1.58)' → 2.0
    first_token = s.split()[0].split("/")[0].split("(")[0].strip()
    try:
        if first_token.endswith("B"):
            return float(first_token[:-1])
        if first_token.endswith("M"):
            return float(first_token[:-1]) / 1000
        return float(first_token)
    except (ValueError, IndexError):
        pass

    # Fallback: try to extract any number followed by B/M anywhere in string
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*([BM])\b", s)
    if m:
        num = float(m.group(1))
        return num if m.group(2) == "B" else num / 1000

    return float("inf")


#: Common abbreviations and aliases → canonical capability names.
CAPABILITY_ALIASES: dict[str, str] = {
    "vlm": "vision-language",
    "vision": "vision-language",
    "llm": "chat",
    "asr": "speech-to-text",
    "stt": "speech-to-text",
    "tts": "text-to-speech",
    "ocr": "document-ocr",
    "rag": "embedding",
    "clip": "image-text-similarity",
    "vla": "vision-language-action",
    "depth": "monocular-depth",
    "segmentation": "promptable-segmentation",
    "detection": "object-detection",
    "coding": "text-generation",
    "text": "text-generation",
    "speech": "speech-to-text",
}


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
                try:
                    return yaml.safe_load(path.read_text()) or {}
                except yaml.YAMLError as e:
                    print(f"Error parsing {name}.yaml: {e}", file=sys.stderr)
                    return {}
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
        if not isinstance(model_id, str) or not model_id.strip():
            return None
        lower = model_id.lower().strip()
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

    def _known_capabilities(self) -> set[str]:
        """Return the set of all canonical capability names defined in the catalog."""
        self._load()
        caps: set[str] = set()
        for m in self._models:
            for c in m.get("capabilities", []):
                caps.add(c)
        return caps

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
        # Coerce non-string filters to None (defensive against int/list/None args)
        capability = str(capability).lower() if capability and isinstance(capability, str) else None
        device = str(device).lower() if device and isinstance(device, str) else None
        license_type = str(license_type) if license_type and isinstance(license_type, str) else None
        family = str(family).lower() if family and isinstance(family, str) else None
        source_group = str(source_group) if source_group and isinstance(source_group, str) else None
        modality = str(modality).lower() if modality and isinstance(modality, str) else None
        # Normalize capability with aliases
        if capability:
            capability = CAPABILITY_ALIASES.get(capability, capability)
        results = []
        # Determine matching mode:
        # - If the resolved capability exactly matches a known capability → exact match only
        # - If not exact but is a known prefix like "vision" → substring match ONLY for
        #   capabilities that start with the query (not arbitrary substring containment)
        #   This prevents "text" from matching text-generation, text-to-speech, etc.
        use_prefix_match = False
        if capability:
            resolved_caps_lower = {c.lower() for c in self._known_capabilities()}
            if capability not in resolved_caps_lower:
                # Check if it's a unique prefix (e.g. "vision" → "vision-language")
                prefix_matches = [c for c in resolved_caps_lower if c.startswith(capability)]
                if len(prefix_matches) >= 1:
                    use_prefix_match = True
                # else: not a prefix of anything, will return no results
        for m in self._models:
            if capability:
                caps = [c.lower() for c in m.get("capabilities", [])]
                if capability in caps:
                    pass  # exact match
                elif use_prefix_match and any(c.startswith(capability) for c in caps):
                    pass  # prefix match (e.g. "vision" matches "vision-language")
                else:
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

    def readiness_score(self, model: dict, task: str | None = None) -> int:
        """Calculate 0-100 readiness score for a model.

        When *task* is provided, a quality-proxy size bonus is applied:
        for quality-sensitive tasks (chat, reasoning, code agent, etc.)
        models with >2B parameters get +3 points. For on-device/edge/mobile
        tasks, large models are NOT boosted (smaller is better).
        """
        if not model or not isinstance(model, dict):
            return 0
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

        # Quality-proxy: boost large models for quality-sensitive tasks
        # unless the task explicitly targets on-device/edge/mobile.
        if task and score > 0:
            tl = task.lower()
            is_edge = any(k in tl for k in ("on-device", "edge", "mobile"))
            if not is_edge:
                params = _parse_params(model.get("size", {}).get("parameters"))
                if params != float("inf") and params > 2.0:
                    score += 3

        return max(0, min(100, score))

    def recommend_models(
        self,
        capabilities: list[str],
        device: str | None = None,
        limit: int = 5,
        task: str | None = None,
        license_type: str | None = None,
    ) -> list[dict]:
        """Unified model recommendation logic shared by CLI and MCP server.

        Ranks models that match any of *capabilities*, applying:
        1. Readiness score + benchmark boost (primary sort key, desc).
        2. First-capability priority: models matching the FIRST resolved
           capability are promoted ahead of models that only match later
           capabilities (secondary sort, stable within each tier).
        3. Parameter count (tertiary: smaller models first on ties).

        Returns a list of recommendation dicts (already sorted + limited),
        each with: id, name, score, matched_capabilities, parameters,
        devices, license, commercial_use, has_benchmark, notes.
        """
        self._load()
        if not capabilities:
            return []

        # Coerce non-string filters to None (defensive)
        device = str(device).lower() if device and isinstance(device, str) else None
        license_type = str(license_type) if license_type and isinstance(license_type, str) else None

        caps_lower = set()
        for c in capabilities:
            if isinstance(c, str):
                caps_lower.add(c.lower())
        if not caps_lower:
            return []
        first_cap = next(iter(caps_lower))  # first element of the set (arbitrary but stable)
        candidates = []
        for m in self._models:
            model_caps = {c.lower() for c in m.get("capabilities", [])}
            matched = model_caps & caps_lower
            if not matched:
                continue
            if device:
                ds = m.get("device_support", {})
                if ds.get(device.lower()) is not True:
                    continue
            if license_type:
                if m.get("license", {}).get("commercial_use") != license_type:
                    continue
            score = self.readiness_score(m, task=task)
            if self._bench_by_model.get(m["id"]):
                score += 5
            candidates.append({
                "id": m["id"],
                "name": m["name"],
                "score": score,
                "matched_capabilities": sorted(matched),
                "parameters": m.get("size", {}).get("parameters"),
                "devices": m.get("device_support", {}),
                "license": m.get("license", {}).get("name"),
                "commercial_use": m.get("license", {}).get("commercial_use"),
                "has_benchmark": bool(self._bench_by_model.get(m["id"])),
                "notes": m.get("notes", ""),
                # internal flags for sorting (stripped before return)
                "_matches_first": first_cap in matched,
                "_params_sort": _parse_params(m.get("size", {}).get("parameters")),
            })

        # Primary sort: score desc. Secondary: first-cap priority. Tertiary: params asc.
        candidates.sort(
            key=lambda c: (-c["score"], 0 if c["_matches_first"] else 1, c["_params_sort"])
        )

        # Strip internal sort keys and apply limit
        result = []
        for c in candidates[:limit]:
            del c["_matches_first"]
            del c["_params_sort"]
            result.append(c)
        return result


# Task → capability mapping
TASK_MAP: dict[str, list[str]] = {
    "robot vision": ["vision-language", "object-detection", "monocular-depth", "promptable-segmentation"],
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
    # ── NLP tasks that map to chat/text-generation ──
    "translation": ["chat", "text-generation"],
    "summarization": ["chat", "text-generation"],
    "summarize": ["chat", "text-generation"],
    "code generation": ["text-generation", "chat"],
    "code completion": ["text-generation", "chat"],
    "math": ["reasoning", "chat"],
    "math reasoning": ["reasoning", "chat"],
    "question answering": ["chat", "text-generation"],
    "qa": ["chat", "text-generation"],
    "text summarization": ["chat", "text-generation"],
    "writing": ["chat", "text-generation"],
    "creative writing": ["chat", "text-generation"],
    "text generation": ["text-generation", "chat"],
    "instruct": ["chat", "text-generation"],
    "instruction following": ["chat", "text-generation"],
    "function calling": ["chat", "agentic"],
    "tool use": ["chat", "agentic"],
    "json generation": ["text-generation", "chat"],
    "classification": ["embedding", "chat"],
    "text classification": ["embedding", "chat"],
    "sentiment analysis": ["embedding", "chat"],
    "zero-shot classification": ["embedding", "chat"],
    "feature extraction": ["embedding"],
    "reranker": ["reranking"],
    "ranking": ["reranking"],
    "reranking": ["reranking"],
    # ── Vision tasks ──
    "image classification": ["vision-language", "image-text-similarity"],
    "image captioning": ["vision-language"],
    "visual question answering": ["vision-language"],
    "vqa": ["vision-language"],
    "visual reasoning": ["vision-language", "reasoning"],
    "scene understanding": ["vision-language", "object-detection"],
    "face detection": ["object-detection"],
    "pose estimation": ["object-detection"],
    "image segmentation": ["promptable-segmentation", "instance-segmentation"],
    "panoptic segmentation": ["promptable-segmentation"],
    # ── Audio tasks ──
    "audio transcription": ["speech-to-text"],
    "speech enhancement": ["speech-to-text"],
    "noise reduction": ["speech-to-text"],
    "voice cloning": ["text-to-speech"],
    # ── Document tasks ──
    "layout analysis": ["document-ocr", "vision-language"],
    "document understanding": ["document-ocr", "vision-language"],
    "table extraction": ["document-ocr", "vision-language"],
    "formula recognition": ["document-ocr"],
    # ── Video/multimodal ──
    "video understanding": ["vision-language"],
    "multimodal chat": ["vision-language", "chat"],
    # ── 3D tasks ──
    "3d reconstruction": ["image-to-3d"],
    "gaussian splatting": ["image-to-3d"],
}


def resolve_task(task: str) -> list[str]:
    """Resolve a free-text task to a list of capabilities."""
    if not isinstance(task, str) or not task.strip():
        return []
    lower = task.lower().strip()
    if lower in TASK_MAP:
        return TASK_MAP[lower]
    matches = set()
    for key, caps in TASK_MAP.items():
        if key in lower or lower in key:
            matches.update(caps)
    return list(matches) if matches else [lower.replace(" ", "-")]
