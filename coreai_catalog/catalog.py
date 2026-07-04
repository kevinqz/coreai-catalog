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


#: Readiness-score weights. Single source of truth for every point value
#: used in `Catalog.readiness_score()`. Keep keys names aligned with the
#: field being checked so they are easy to audit.
SCORING_WEIGHTS: dict[str, int] = {
    "artifact_available": 15,
    "license_likely": 10,
    "device_iphone": 10,
    "device_mac": 10,
    "has_benchmark": 10,
    "stock_runtime": 10,
    "no_custom_kernel": 5,
    "no_patch_required": 5,
    "no_aot_required": 5,
    "status_confirmed": 10,
    "confidence_high": 5,
    "confidence_medium": 3,
    "confidence_low": -10,
    "maturity_stable_active": 5,
    "quality_bonus_large_model": 3,
    # Separate from readiness_score but used in recommend_models
    "recommend_benchmark_boost": 5,
}


# ---------------------------------------------------------------------------
# Decomposed suitability facets (SotA readiness reshape).
#
# readiness_score() is a single curation/deployability composite that is BLIND
# to model quality (it counts only benchmark PRESENCE, not values) and is
# therefore deprecated as a headline signal. The functions below split it into
# the three orthogonal axes SotA registries actually surface, and are emitted
# per-entry in dist/search-index.json:
#   - deployability_facets(): can I obtain/run/license it? (per-axis, no score)
#   - lifecycle_of():         how mature is the ENTRY? (ordinal stage)
#   - entry_completeness():   how complete is the ENTRY? (coverage, not quality)
# Model QUALITY stays where it belongs: benchmark VALUES, per <task,metric>.
# ---------------------------------------------------------------------------

def deployability_facets(model: dict, has_bench: bool = False) -> dict[str, Any]:
    """Decomposed deployment facets for filtering/badges — NOT a quality score.

    Derived from the entry's device_support/runtime/license/artifact fields.
    Collapses the four collinear runtime flags (stock_runtime, custom_kernel,
    patch_required, aot_required) into one ``runtime`` axis.
    """
    if not isinstance(model, dict):
        return {}
    ds = model.get("device_support") or {}
    rt = model.get("runtime") or {}
    lic = model.get("license") or {}
    stock = rt.get("stock_runtime")
    runtime = "stock" if stock is True else "patched" if stock is False else "unknown"
    return {
        "obtainable": (model.get("artifact") or {}).get("availability", "unknown"),
        "runtime": runtime,
        "device_fit": {
            "mac": ds.get("mac", "unknown"),
            "iphone": ds.get("iphone", "unknown"),
            "ipad": ds.get("ipad", "unknown"),
        },
        "license": {
            "name": lic.get("name"),
            "commercial_use": lic.get("commercial_use"),
        },
        "measured": bool(has_bench),
    }


def lifecycle_of(model: dict) -> dict[str, Any]:
    """Ordinal maturity stage of the catalog ENTRY (MLTRL / MLflow-tags style).

    Derived from source_group/status/maturity. An explicit ``lifecycle`` block
    on the entry (e.g. authored by coreai-fabric) takes precedence. Separate
    from model quality.
    """
    if not isinstance(model, dict):
        return {}
    explicit = model.get("lifecycle")
    if isinstance(explicit, dict) and explicit.get("stage"):
        return explicit
    status = model.get("status")
    maturity = model.get("maturity")
    group = model.get("source_group")
    if status == "deprecated":
        stage = "deprecated"
    elif group == "official" and status == "confirmed":
        stage = "official"
    elif group == "fabric" or status == "needs_review":
        # community = community-converted or not-yet-verified provenance
        stage = "community"
    elif status == "confirmed" and maturity in ("stable", "active"):
        stage = "verified"
    else:
        # confirmed but experimental/research maturity
        stage = "experimental"
    return {
        "stage": stage,
        "verification": status or "unknown",
        "curator_confidence": model.get("confidence"),
        "last_verified": model.get("last_verified"),
    }


def entry_completeness(model: dict, has_bench: bool = False) -> dict[str, Any]:
    """Coverage of key metadata for this catalog ENTRY (Kaggle-Usability style).

    NOT model quality/accuracy: an 'unknown' or absent facet lowers coverage,
    never a hidden quality score.
    """
    if not isinstance(model, dict):
        return {"pct": 0.0, "present": 0, "of": 0, "fields": {}}
    ds = model.get("device_support") or {}
    rt = model.get("runtime") or {}
    lic = model.get("license") or {}
    art = model.get("artifact") or {}
    fields = {
        "artifact_availability_known": art.get("availability") not in (None, "unknown"),
        "device_support_known": ds.get("mac") not in (None, "unknown"),
        "runtime_profile_known": rt.get("stock_runtime") is not None,
        "license_triaged": bool(lic.get("commercial_use")),
        "benchmarked": bool(has_bench),
        "io_contract_present": bool(model.get("io_contract")),
    }
    present = sum(1 for v in fields.values() if v)
    of = len(fields)
    return {
        "pct": round(present / of, 3) if of else 0.0,
        "present": present,
        "of": of,
        "fields": fields,
    }


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
    """Find the catalog root (where catalog.yaml lives).

    Search order:
      1. CWD (if catalog.yaml exists — dev mode or cloned repo)
      2. Walk up from this file (development mode from repo root)
      3. Bundled package data (pip install / PyPI)
    """
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
    # Try bundled package data (pip install from PyPI)
    bundled = Path(__file__).resolve().parent / "data"
    if (bundled / "catalog.yaml").exists():
        return bundled
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
        self._known_caps: set[str] = set()
        self._models_by_id: dict[str, dict] = {}
        self._load_mtime: float = 0.0

    def _check_mtime_changed(self) -> bool:
        """Check if source files have been modified since last load."""
        import os
        max_mtime = 0.0
        for name in ("catalog.yaml", "benchmarks.jsonl", "artifacts.yaml"):
            p = self.root / name
            if p.exists():
                try:
                    max_mtime = max(max_mtime, os.path.getmtime(p))
                except OSError:
                    pass
        return max_mtime != self._load_mtime

    def _load(self) -> None:
        if self._loaded and not self._check_mtime_changed():
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
        terms = read_yml("terms")
        sources = read_yml("sources")

        self._models = cat.get("models", [])
        self._artifacts = art.get("artifacts", [])
        self._terms = terms.get("terms", [])
        self._sources = sources.get("sources", [])

        # Load benchmarks from JSONL (single source of truth)
        self._benchmarks = self._load_benchmarks()
        self._art_by_id = {a["id"]: a for a in self._artifacts if "id" in a}
        self._bench_by_model = {}
        for b in self._benchmarks:
            mid = b.get("model_id", "")
            self._bench_by_model.setdefault(mid, []).append(b)

        # Cache the union of all capability names (used by search())
        self._known_caps: set[str] = set()
        for m in self._models:
            for c in m.get("capabilities", []):
                self._known_caps.add(c)

        # O(1) model lookup by lowercased ID
        self._models_by_id = {m["id"].lower(): m for m in self._models if "id" in m}

        self._loaded = True
        self._load_mtime = self._check_mtime_changed() and 0.0  # force re-eval next time if mtime check fails
        # Actually just record current mtime
        import os
        for name in ("catalog.yaml", "benchmarks.jsonl", "artifacts.yaml"):
            p = self.root / name
            if p.exists():
                try:
                    self._load_mtime = max(self._load_mtime, os.path.getmtime(p))
                except OSError:
                    pass

    def _load_benchmarks(self) -> list[dict]:
        """Load benchmarks from benchmarks.jsonl (single source of truth).

        The legacy benchmarks.yaml store is retired — a missing JSONL file
        means "no benchmarks", never "fall back to old data".
        """
        import json as _json

        jsonl_path = self.root / "benchmarks.jsonl"
        if not jsonl_path.exists():
            return []
        benchmarks = []
        skipped = 0
        for line in jsonl_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                entry = _json.loads(line)
                # Minimal schema validation: must have model_id
                if not isinstance(entry, dict) or "model_id" not in entry:
                    print(f"Warning: skipping malformed benchmark entry (no model_id)", file=sys.stderr)
                    skipped += 1
                    continue
                benchmarks.append(entry)
            except _json.JSONDecodeError as e:
                print(f"Warning: invalid JSONL line in benchmarks.jsonl: {e}", file=sys.stderr)
                skipped += 1
        # An empty result means corruption or no data — never "use old data".
        return benchmarks

    @property
    def transform_graph(self):
        """Cached TransformGraph — rebuilt only when catalog reloads."""
        if not hasattr(self, '_graph_cache') or self._check_mtime_changed():
            from .transform_graph import TransformGraph
            self._load()
            self._graph_cache = TransformGraph(self._models, self)
        return self._graph_cache

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
        return self._models_by_id.get(model_id.lower().strip())

    def get_artifact(self, model_id: str) -> dict | None:
        """Get the artifact record for a model."""
        self._load()
        model = self.get_model(model_id)
        if not model:
            return None
        ref = model.get("artifact_ref", "")
        return self._art_by_id.get(ref)

    def get_benchmarks(self, model_id: str, min_confidence: str | None = None) -> list[dict]:
        """Get benchmark records for a model, optionally filtered by confidence.

        Args:
            model_id: Model ID to look up.
            min_confidence: If set, filter to entries at or above this level.
                Valid values: 'high', 'medium', 'low'.
                None returns all benchmarks (backward compat).
        """
        self._load()
        bms = self._bench_by_model.get(model_id, [])
        if min_confidence is not None:
            confidence_order = {"high": 3, "medium": 2, "low": 1, "needs_review": 0}
            valid_levels = set(confidence_order.keys())
            if min_confidence not in valid_levels:
                raise ValueError(
                    f"Invalid min_confidence '{min_confidence}'. "
                    f"Must be one of: {sorted(valid_levels)}"
                )
            min_val = confidence_order[min_confidence]
            bms = [
                b for b in bms
                if confidence_order.get(b.get("confidence", "low"), 0) >= min_val
            ]
        return bms

    def _known_capabilities(self) -> set[str]:
        """Return the set of all canonical capability names defined in the catalog."""
        self._load()
        return self._known_caps

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
        sw = SCORING_WEIGHTS
        has_bench = bool(self._bench_by_model.get(model.get("id", "")))
        score = 0
        if model.get("artifact", {}).get("availability") == "available":
            score += sw["artifact_available"]
        if model.get("license", {}).get("commercial_use") == "likely":
            score += sw["license_likely"]
        if model.get("device_support", {}).get("iphone") is True:
            score += sw["device_iphone"]
        if model.get("device_support", {}).get("mac") is True:
            score += sw["device_mac"]
        if has_bench:
            score += sw["has_benchmark"]
        rt = model.get("runtime", {})
        if rt.get("stock_runtime") is True:
            score += sw["stock_runtime"]
        if rt.get("custom_kernel") is False:
            score += sw["no_custom_kernel"]
        if rt.get("patch_required") is False:
            score += sw["no_patch_required"]
        if rt.get("aot_required") is False:
            score += sw["no_aot_required"]
        if model.get("status") == "confirmed":
            score += sw["status_confirmed"]
        conf = model.get("confidence", "")
        if conf == "high":
            score += sw["confidence_high"]
        elif conf == "medium":
            score += sw["confidence_medium"]
        elif conf == "low":
            score += sw["confidence_low"]
        if model.get("maturity") in ("stable", "active"):
            score += sw["maturity_stable_active"]

        # Quality-proxy: boost large models for quality-sensitive tasks
        # unless the task explicitly targets on-device/edge/mobile.
        if task and score > 0:
            tl = task.lower()
            is_edge = any(k in tl for k in ("on-device", "edge", "mobile"))
            if not is_edge:
                params = _parse_params(model.get("size", {}).get("parameters"))
                if params != float("inf") and params > 2.0:
                    score += sw["quality_bonus_large_model"]

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
        # Sort for determinism — set iteration order is hash-seed dependent
        caps_sorted = sorted(caps_lower)
        first_cap = caps_sorted[0]
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
                score += SCORING_WEIGHTS["recommend_benchmark_boost"]
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
