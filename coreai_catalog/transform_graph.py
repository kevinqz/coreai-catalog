"""
Core AI Catalog — Transform Graph Engine.

Builds a directed graph of modality transformations from the catalog.
Each model is an edge: input_modality -> output_modality.
Supports BFS shortest-path and multi-hop pipeline queries.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TransformEdge:
    """A single model's capability to transform one modality into another."""
    input_modality: str
    output_modality: str
    model_id: str


@dataclass
class PipelineStage:
    """One step in a multi-hop transformation pipeline."""
    model_id: str
    input_modality: str
    output_modality: str
    model_name: str = ""
    estimated_tokens_per_sec: float = 0.0
    parameters: str = ""
    runner: str = ""
    artifact_size: str = ""
    huggingface_url: str = ""


@dataclass
class Pipeline:
    """A complete multi-hop transformation plan."""
    input_modality: str
    output_modality: str
    stages: list[PipelineStage] = field(default_factory=list)

    @property
    def hop_count(self) -> int:
        return len(self.stages)

    @property
    def model_ids(self) -> list[str]:
        return [s.model_id for s in self.stages]

    @property
    def modality_chain(self) -> list[str]:
        if not self.stages:
            return []
        chain = [self.stages[0].input_modality]
        for s in self.stages:
            chain.append(s.output_modality)
        return chain

    @property
    def total_artifact_size(self) -> str:
        """Rough total download size for all stages."""
        return " + ".join(s.artifact_size for s in self.stages if s.artifact_size) or "unknown"

    def to_dict(self) -> dict:
        return {
            "input_modality": self.input_modality,
            "output_modality": self.output_modality,
            "hop_count": self.hop_count,
            "modality_chain": self.modality_chain,
            "model_ids": self.model_ids,
            "total_artifact_size": self.total_artifact_size,
            "stages": [
                {
                    "model_id": s.model_id,
                    "model_name": s.model_name,
                    "input_modality": s.input_modality,
                    "output_modality": s.output_modality,
                    "estimated_tokens_per_sec": s.estimated_tokens_per_sec,
                    "parameters": s.parameters,
                    "runner": s.runner,
                    "artifact_size": s.artifact_size,
                    "huggingface_url": s.huggingface_url,
                }
                for s in self.stages
            ],
        }


class TransformGraph:
    """Directed graph of modality transformations from catalog models."""

    def __init__(self, models: list[dict], catalog: Any = None) -> None:
        self._catalog = catalog
        self._adjacency: dict[str, list[TransformEdge]] = defaultdict(list)
        self._input_modalities: set[str] = set()
        self._output_modalities: set[str] = set()
        self._models_by_id: dict[str, dict] = {m["id"]: m for m in models}
        self._build(models)

    def _build(self, models: list[dict]) -> None:
        """Build adjacency list from model modality data."""
        for m in models:
            mid = m["id"]
            modalities = m.get("modalities", {})
            inputs = modalities.get("input", [])
            outputs = modalities.get("output", [])
            if isinstance(inputs, str):
                inputs = [inputs]
            if isinstance(outputs, str):
                outputs = [outputs]
            for inp in inputs:
                self._input_modalities.add(inp)
                for out in outputs:
                    self._output_modalities.add(out)
                    self._adjacency[inp].append(TransformEdge(inp, out, mid))

    # ── Graph inspection ──

    @property
    def input_modalities(self) -> set[str]:
        return self._input_modalities

    @property
    def output_modalities(self) -> set[str]:
        return self._output_modalities

    @property
    def all_modalities(self) -> set[str]:
        return self._input_modalities | self._output_modalities

    def get_edges(self, input_modality: str, output_modality: str) -> list[TransformEdge]:
        """Get all direct edges (models) between two modalities."""
        return [
            e for e in self._adjacency.get(input_modality, [])
            if e.output_modality == output_modality
        ]

    def get_all_edges_from(self, input_modality: str) -> list[TransformEdge]:
        """Get all outgoing edges from a modality."""
        return list(self._adjacency.get(input_modality, []))

    def get_all_modality_pairs(self) -> set[tuple[str, str]]:
        """Get all unique (input, output) pairs with at least one direct edge."""
        pairs = set()
        for inp, edges in self._adjacency.items():
            for e in edges:
                pairs.add((e.input_modality, e.output_modality))
        return pairs

    # ── Shortest path (BFS) ──

    def shortest_path(self, input_modality: str, target_modality: str) -> Pipeline | None:
        """Find the shortest pipeline (fewest hops) between two modalities.

        Uses BFS. For each hop, picks the highest-scoring model.
        Returns None if no path exists.
        """
        if input_modality == target_modality:
            edges = self.get_edges(input_modality, input_modality)
            if edges:
                return Pipeline(
                    input_modality=input_modality,
                    output_modality=target_modality,
                    stages=[self._pick_best_model(edges[0])],
                )
            return None

        visited: set[str] = {input_modality}
        queue: deque[tuple[str, list[tuple[str, str]]]] = deque()
        queue.append((input_modality, []))

        modality_path: list[tuple[str, str]] | None = None

        while queue:
            current, path = queue.popleft()
            if len(path) > 5:
                break
            for edge in self._adjacency.get(current, []):
                next_mod = edge.output_modality
                if next_mod == target_modality:
                    modality_path = path + [(current, next_mod)]
                    break
                if next_mod not in visited:
                    visited.add(next_mod)
                    queue.append((next_mod, path + [(current, next_mod)]))
            if modality_path:
                break

        if not modality_path:
            return None

        stages: list[PipelineStage] = []
        for inp, out in modality_path:
            edges = self.get_edges(inp, out)
            if not edges:
                return None
            stages.append(self._pick_best_model(edges[0]))

        return Pipeline(
            input_modality=input_modality,
            output_modality=target_modality,
            stages=stages,
        )

    # ── Reachability ──

    def reachable_outputs(self, input_modality: str, max_hops: int = 5) -> set[str]:
        """All output modalities reachable from input_modality within max_hops."""
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(input_modality, 0)])
        while queue:
            current, depth = queue.popleft()
            if depth >= max_hops:
                continue
            for edge in self._adjacency.get(current, []):
                next_mod = edge.output_modality
                if next_mod not in visited:
                    visited.add(next_mod)
                    queue.append((next_mod, depth + 1))
        if not self.get_edges(input_modality, input_modality):
            visited.discard(input_modality)
        return visited

    def all_paths(
        self, input_modality: str, target_modality: str, max_hops: int = 3
    ) -> list[Pipeline]:
        """Find all unique modality paths up to max_hops.

        Returns one Pipeline per unique modality route, using the best model
        for each hop. Sorted by hop_count ascending, then by total estimated speed.
        """
        if input_modality == target_modality:
            edges = self.get_edges(input_modality, input_modality)
            if edges:
                return [Pipeline(
                    input_modality=input_modality,
                    output_modality=target_modality,
                    stages=[self._pick_best_model(edges[0])],
                )]
            return []

        modality_paths: list[list[tuple[str, str]]] = []

        def _dfs(current: str, path: list[tuple[str, str]], visited: set[str]) -> None:
            if len(path) >= max_hops:
                return
            for edge in self._adjacency.get(current, []):
                next_mod = edge.output_modality
                if next_mod == target_modality:
                    modality_paths.append(path + [(current, next_mod)])
                elif next_mod not in visited:
                    _dfs(next_mod, path + [(current, next_mod)], visited | {next_mod})

        _dfs(input_modality, [], {input_modality})

        pipelines: list[Pipeline] = []
        for mod_path in modality_paths:
            stages: list[PipelineStage] = []
            valid = True
            for inp, out in mod_path:
                edges = self.get_edges(inp, out)
                if not edges:
                    valid = False
                    break
                stages.append(self._pick_best_model(edges[0]))
            if valid and stages:
                pipelines.append(Pipeline(
                    input_modality=input_modality,
                    output_modality=target_modality,
                    stages=stages,
                ))

        pipelines.sort(
            key=lambda p: (p.hop_count, -sum(s.estimated_tokens_per_sec for s in p.stages))
        )
        return pipelines

    def reachability_matrix(self) -> dict[str, set[str]]:
        """Build full reachability matrix: {input: {reachable_outputs}}."""
        matrix: dict[str, set[str]] = {}
        for mod in self.all_modalities:
            if self._adjacency.get(mod):
                matrix[mod] = self.reachable_outputs(mod)
        return matrix

    # ── Internal helpers ──

    def _pick_best_model(self, edge: TransformEdge) -> PipelineStage:
        """Pick the best model for a given edge by readiness score."""
        edges = self.get_edges(edge.input_modality, edge.output_modality)
        if not edges:
            return PipelineStage(
                model_id=edge.model_id,
                input_modality=edge.input_modality,
                output_modality=edge.output_modality,
            )

        best_edge = edges[0]
        best_score = -1
        for e in edges:
            score = self._model_score(e.model_id)
            if score > best_score:
                best_score = score
                best_edge = e

        return self._edge_to_stage(best_edge)

    def _model_score(self, model_id: str) -> float:
        """Compute a composite score for model selection."""
        model = self._models_by_id.get(model_id, {})
        score = 0.0
        if self._catalog and hasattr(self._catalog, "readiness_score"):
            score = self._catalog.readiness_score(model)
        else:
            if model.get("source_group") == "official":
                score += 30
            if model.get("license", {}).get("commercial_use") == "likely":
                score += 10
            if model.get("status") == "confirmed":
                score += 10
        return score

    def _edge_to_stage(self, edge: TransformEdge) -> PipelineStage:
        """Convert an edge + model data into a PipelineStage."""
        model = self._models_by_id.get(edge.model_id, {})
        tps = 0.0
        if self._catalog and hasattr(self._catalog, "get_benchmarks"):
            bms = self._catalog.get_benchmarks(edge.model_id)
            for b in bms:
                metric = b.get("metric", "").lower()
                if "throughput" in metric or "token" in metric:
                    try:
                        tps = max(tps, float(b.get("value", 0)))
                    except (ValueError, TypeError):
                        pass

        hf_url = ""
        if self._catalog and hasattr(self._catalog, "get_artifact"):
            art = self._catalog.get_artifact(edge.model_id)
            if art:
                hf_url = art.get("huggingface", {}).get("url", "")

        return PipelineStage(
            model_id=edge.model_id,
            model_name=model.get("name", edge.model_id),
            input_modality=edge.input_modality,
            output_modality=edge.output_modality,
            estimated_tokens_per_sec=tps,
            parameters=model.get("size", {}).get("parameters", ""),
            runner=model.get("runtime", {}).get("runner", ""),
            artifact_size=model.get("size", {}).get("artifact_size", ""),
            huggingface_url=hf_url,
        )
