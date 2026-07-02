"""
Core AI Catalog — public Python API.

A clean, stable interface for programmatic access to the catalog.
Works with pip-installed package (no repo clone needed).

Example:
    from coreai_catalog import Catalog

    catalog = Catalog.load()
    catalog.recommend(task="ocr", device="iphone")
    catalog.compare("qwen3-vl-2b", "unlimited-ocr")
    catalog.license_report("qwen3-vl-2b")
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .catalog import Catalog as _Catalog, resolve_task as _resolve_task
from .formatters import (
    build_task_reverse_map,
    count_capabilities,
    get_catalog_version,
)


class Catalog:
    """High-level catalog API for programmatic access.

    Usage:
        from coreai_catalog import Catalog

        # Auto-discovers YAML data (bundled in pip package, or from repo root)
        catalog = Catalog.load()

        # Search and filter
        results = catalog.search(capability="vision-language", device="iphone")

        # Get recommendations
        recs = catalog.recommend(task="ocr", device="iphone", license_filter="likely")

        # Compare models
        diff = catalog.compare("qwen3-vl-2b", "unlimited-ocr")

        # License triage
        report = catalog.license_report("qwen3-vl-2b")

        # Browse tasks
        tasks = catalog.tasks()
    """

    def __init__(self, root: Path | None = None) -> None:
        self._cat = _Catalog(root)

    @classmethod
    def load(cls) -> "Catalog":
        """Create a Catalog instance, auto-discovering the YAML data.

        Search order: CWD → walk up from package → bundled package data.
        """
        return cls()

    @property
    def version(self) -> str:
        """Catalog version string (e.g. '1.6.0')."""
        self._cat._load()
        return get_catalog_version(self._cat.root)

    @property
    def model_count(self) -> int:
        """Total number of models in the catalog."""
        return len(self._cat.models)

    def search(
        self,
        capability: str | None = None,
        device: str | None = None,
        license_filter: str | None = None,
        family: str | None = None,
        source_group: str | None = None,
        modality: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search models by criteria.

        Args:
            capability: Filter by capability (e.g. 'chat', 'vision-language').
            device: Filter by device support (e.g. 'iphone', 'mac').
            license_filter: Filter by commercial use ('likely' or 'check_license').
            family: Filter by model family (e.g. 'Qwen', 'Gemma').
            source_group: Filter by source ('official', 'zoo', 'external').
            modality: Filter by input modality ('text', 'image', 'audio').
            limit: Maximum results.

        Returns:
            List of model dicts with capabilities, devices, license, score.
        """
        results = self._cat.search(
            capability=capability,
            device=device,
            license_type=license_filter,
            family=family,
            source_group=source_group,
            modality=modality,
        )
        return results[:limit]

    def recommend(
        self,
        task: str,
        device: str | None = None,
        license_filter: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """Recommend models for a task.

        Args:
            task: Task description (e.g. 'robot vision', 'private OCR').
                  See ``catalog.tasks()`` for valid keywords.
            device: Target device filter ('iphone', 'mac').
            license_filter: Commercial use filter ('likely' or 'check_license').
            limit: Maximum results.

        Returns:
            Sorted list of recommendations with score, matched capabilities,
            and metadata.
        """
        capabilities = _resolve_task(task)
        return self._cat.recommend_models(
            capabilities=capabilities,
            device=device,
            limit=limit,
            task=task,
            license_type=license_filter,
        )

    def get_model(self, model_id: str) -> dict | None:
        """Get full details for a specific model.

        Args:
            model_id: Model ID (e.g. 'qwen3-vl-2b').

        Returns:
            Model dict with all fields, or None if not found.
        """
        return self._cat.get_model(model_id)

    def compare(self, *model_ids: str) -> dict[str, Any]:
        """Compare two or more models side-by-side.

        Args:
            *model_ids: Two or more model IDs to compare.

        Returns:
            Dict with 'models' list and field-by-field comparison.
        """
        if len(model_ids) < 2:
            raise ValueError("compare() requires at least 2 model IDs")

        models = []
        for mid in model_ids:
            m = self._cat.get_model(mid)
            if m is None:
                raise KeyError(f"Model '{mid}' not found")
            models.append(m)

        result: dict[str, Any] = {"models": []}
        for m in models:
            entry = {
                "id": m["id"],
                "name": m["name"],
                "family": m.get("family"),
                "capabilities": m.get("capabilities", []),
                "parameters": m.get("size", {}).get("parameters"),
                "precision": m.get("size", {}).get("precision"),
                "devices": m.get("device_support", {}),
                "license": m.get("license", {}),
                "source_group": m.get("source_group"),
                "score": self._cat.readiness_score(m),
                "benchmarks": self._cat.get_benchmarks(m["id"]),
            }
            result["models"].append(entry)

        return result

    def license_report(self, model_id: str) -> dict[str, Any]:
        """Generate a license triage report for a model.

        Args:
            model_id: Model ID.

        Returns:
            Dict with license name, commercial_use status, and notes.
        """
        m = self._cat.get_model(model_id)
        if m is None:
            raise KeyError(f"Model '{model_id}' not found")

        lic = m.get("license", {})
        art = self._cat.get_artifact(model_id) or {}
        off = art.get("officiality", {}) if art else {}

        return {
            "model_id": model_id,
            "name": m.get("name", model_id),
            "license_name": lic.get("name", "unknown"),
            "commercial_use": lic.get("commercial_use", "unknown"),
            "officiality": off,
            "artifact_source": art.get("huggingface", {}).get("url", ""),
        }

    def tasks(self) -> dict[str, list[str]]:
        """List all supported task keywords grouped by capability.

        Returns:
            Dict mapping capability name to list of task synonyms.
        """
        return build_task_reverse_map()

    def capabilities(self) -> list[dict[str, Any]]:
        """List all capabilities with model counts.

        Returns:
            List of dicts with capability name, model count, and benchmark count.
        """
        return count_capabilities(self._cat.models, self._cat.get_benchmarks)

    def transforms(self) -> dict[str, list[str]]:
        """Get the full modality transformation reachability matrix.

        Returns:
            Dict mapping each input modality to the list of output
            modalities reachable from it (direct or multi-hop).
        """
        from .transform_graph import TransformGraph
        graph = TransformGraph(self._cat.models, self._cat)
        matrix = graph.reachability_matrix()
        return {k: sorted(v) for k, v in matrix.items()}

    def reachable_outputs(self, input_modality: str) -> list[str]:
        """List all output modalities reachable from a given input.

        Args:
            input_modality: e.g. 'text', 'image', 'audio'.

        Returns:
            Sorted list of reachable output modalities.
        """
        from .transform_graph import TransformGraph
        graph = TransformGraph(self._cat.models, self._cat)
        return sorted(graph.reachable_outputs(input_modality))

    def transform_pipeline(
        self, input_modality: str, output_modality: str,
    ) -> dict | None:
        """Find a transformation pipeline between two modalities.

        Args:
            input_modality: Starting modality (e.g. 'audio').
            output_modality: Target modality (e.g. 'image').

        Returns:
            Pipeline dict with stages, or None if no path exists.
        """
        from .transform_graph import TransformGraph
        graph = TransformGraph(self._cat.models, self._cat)
        pipeline = graph.shortest_path(input_modality, output_modality)
        return pipeline.to_dict() if pipeline else None
