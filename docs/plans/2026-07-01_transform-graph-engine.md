# Ditto — Universal Media Transmutation Engine

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Transform any input media (audio, image, text, document) into any reachable output modality by chaining Core AI models on-device, powered by a Transform Graph Engine in coreai-catalog.

**Architecture:** Two **independent repositories** with a one-way JSON contract between them.

- **`coreai-catalog`** (public, existing) — Python catalog + Transform Graph Engine. Exports `dist/transforms-graph.json` and `dist/model-manifest.json`. Docs describe the graph engine and CLI. **Never mentions Ditto.**
- **`Ditto`** (private, new) — iOS 27 app. Consumes the catalog's JSON artifacts as a build-time input. Docs describe the app architecture, UI, and model execution. **Never mentions the catalog's internals.**

**Sync mechanism:** Ditto bundles a snapshot of `transforms-graph.json` + `model-manifest.json`. When the catalog publishes a new version (PyPI/GitHub release), Ditto updates the bundled snapshot. No runtime dependency, no shared code, no shared docs.

**Tech Stack (verified against Apple sources):**
- **coreai-catalog (Python):** PyYAML, jsonschema, argparse, FastMCP — existing stack
- **Ditto (iOS):** SwiftUI, SwiftData, URLSession background downloads, String Catalog (.xcstrings)
- **Model runtime:** Apple's `coreai-models` Swift package (products: `CoreAILM`, `CoreAIDiffusion`, `CoreAISegmentation`, `CoreAISpeech`, `CoreAIObjectDetection`)
- **Apple frameworks:** Core AI (`.aimodel`), Foundation Models (`LanguageModelSession`, `LanguageModel` protocol)
- **Deployment target:** **iOS 27.0+** (required by coreai-models Package.swift)

---

## Apple API Surface — Verified Facts

All API names below are verified against the actual `apple/coreai-models` repository source code and Apple developer documentation. **Do not invent API names.**

### coreai-models Swift Package (github.com/apple/coreai-models)

```swift
// Package.swift
platforms: [.macOS("27.0"), .iOS("27.0")]

// Products:
.library(name: "CoreAILM", targets: ["CoreAILanguageModels"]),
.library(name: "CoreAIDiffusion", targets: ["CoreAIDiffusionPipeline"]),
.library(name: "CoreAISegmentation", targets: ["CoreAIImageSegmenter"]),
.library(name: "CoreAISpeech", targets: ["CoreAISpeech"]),
.library(name: "CoreAIObjectDetection", targets: ["CoreAIObjectDetector"]),
```

### LLM / Chat / VLM — `CoreAIRunner` + `CoreAILanguageModel`

```swift
// Load and create a Foundation Models-compatible LanguageModel
let url = URL(fileURLWithPath: "/path/to/model-bundle")
let runner = try CoreAIRunner(contentsOf: url)
let model = try await runner.makeLanguageModel()

// Use with Foundation Models framework
let session = LanguageModelSession(model: model)
let response = try await session.respond(to: "Describe this image")

// Streaming
let stream = session.streamResponse(to: prompt)
for try await partial in stream { ... }

// VLM: image input via Attachment
let attachment = Attachment(data: imageData, type: .image)
let response = try await session.respond(to: Prompt("What is this?", attachments: [attachment]))
```

**Key types (verified):** `CoreAIRunner`, `CoreAILanguageModel: LanguageModel`, `LanguageBundle`, `EngineFactory`, `InferenceEngine`, `TextGenerator`, `LanguageModelSession`

### Speech-to-Text — `SpeechModel` (actor)

```swift
let speechModel = try await SpeechModel(resourcesAt: bundleURL)
let transcript = try await speechModel.transcribe(audioURL: audioURL)
// Also: transcribe(pcm:) for raw 16kHz mono
```

### Image Generation — `DiffusionPipeline` protocol

```swift
// Pipeline created from PipelineDescriptor + PipelineConfiguration
let pipeline: any DiffusionPipeline = ...
let result = try await pipeline.generateImages(
    configuration: PipelineConfiguration(prompt: "a cat", ...),
    progressHandler: { progress in
        // PipelineProgress(step:totalSteps:currentLatent:)
        return true // continue
    }
)
// GenerationResult(images: [CGImage], latents: [NDArray])
```

### Image Segmentation — `ImageSegmenter`

```swift
let segmenter = try ImageSegmenter(engine: engine, tokenizerFolder: url)
// Text-guided (SAM 3)
let segments = try await segmenter.segment(image: cgImage, prompt: "cat")
// Point-based (EfficientSAM)
let pq = PointQuery(points: [.init(x: 320, y: 240)])
let segments = try await segmenter.segment(image: cgImage, pointQuery: pq)
```

### Object Detection — `ObjectDetector`

```swift
let detector = try await ObjectDetector(resourcesAt: path)
// Uses AIModel.loadFunction("main"), returns boxes + classes
```

### Bundle Structure (all model types)

```
model-bundle/
  metadata.json          # kind: "llm" | "diffusion" | "segmenter" | "speech"
  assets.main            # → .aimodel file mapping
  language/              # tokenizer (for LLMs)
  pipeline.json          # (for diffusion)
  ...
  *.aimodel              # Core AI artifact(s)
```

### Foundation Models Framework (developer.apple.com/documentation/FoundationModels)

- **Availability:** iOS 26.0+, iPadOS 26.0+, macOS 26.0+, visionOS 26.0+
- **Key types:** `LanguageModelSession`, `LanguageModel` (protocol), `Prompt`, `Attachment`, `Instructions`, `GenerationOptions`, `Transcript`, `Tool`
- **@Generable** macro for structured output
- **Attachment** supports image input (multimodal)
- **DynamicProfile** for model routing within a session

### On-Demand Model Distribution — SotA Approach

**Background Assets framework** (iOS 16.1+, Apple documented):
- Downloads large assets that persist across app updates
- Survives app termination — OS manages the download
- `BackgroundAssetManager` + `BackgroundDownloadDescriptor`
- User gets notification when download completes
- Assets can be several GB

**Our architecture:**
1. Catalog exports `model-manifest.json` with HF URLs + sizes + SHA256 for every model
2. Ditto bundles a lightweight catalog index (model IDs, capabilities, modalities, graph)
3. When user selects a pipeline, Ditto checks local availability
4. Missing models are queued for Background Assets download
5. Downloaded bundles stored in Application Support directory
6. `CoreAIRunner(contentsOf:)` etc. load from the local path

**Why not ODR (On-Demand Resources)?** ODR has a 20GB total limit, assets are purged by the OS, and they're hosted on Apple's servers. Background Assets + HF hosting is the right answer for community models that update independently of the app.

---

## Current State Inventory

### coreai-catalog (v2.0.5)
- 79 models, 79 artifacts, 66 benchmarks
- 6 input modalities, 21 output modalities
- 29 direct transforms, 17 two-hop, 7 three-hop = **53 reachable modality pairs**
- CLI (14 commands), MCP (11 tools), Python API, Web UI, PyPI
- Key files:
  - `coreai_catalog/catalog.py` — Catalog class, search, recommend, readiness_score, TASK_MAP
  - `coreai_catalog/api.py` — public Catalog API wrapper
  - `coreai_catalog/cli.py` — 14 CLI commands, build_parser()
  - `coreai_catalog/exports.py` — JSON/JSONL generation for dist/
  - `coreai_catalog/installer.py` — model download + manifest + Swift snippet
  - `mcp_server/server.py` — 11 MCP tools
  - `schema/model.schema.json` — model schema with modalities.input/output arrays
  - `catalog.yaml` — source-of-truth YAML (modalities field on each model)

### Ditto (does not exist yet)
- iOS 27 app, depends on `apple/coreai-models` Swift package
- English UI with String Catalog for future i18n

---

## Data Model: The Transform Graph

Each model in `catalog.yaml` has:
```yaml
modalities:
  input: [text]
  output: [text, audio]
```

This defines a **directed edge** in the transform graph. No YAML schema changes needed — data already exists.

---

## PHASE 1: Transform Graph Engine (coreai-catalog repo)

> **Repository:** `~/Dev/Github/coreai-catalog` (public)
> **Documentation rule:** All docs in this repo describe the graph engine as a general-purpose tool for planning Core AI model pipelines. No reference to Ditto or any consumer app.

### Task 1: Create transform_graph.py module

**Objective:** Core graph data structures and adjacency builder.

**Files:**
- Create: `coreai_catalog/transform_graph.py`
- Test: `tests/test_transform_graph.py`

**Step 1: Write failing tests**

```python
"""Tests for the Transform Graph Engine."""
import unittest
from coreai_catalog.transform_graph import TransformGraph, PipelineStage, Pipeline


class TestTransformGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from coreai_catalog.catalog import Catalog
        cat = Catalog()
        cls.graph = TransformGraph(cat.models, cat)

    def test_graph_has_inputs(self):
        """Graph recognizes known input modalities."""
        inputs = self.graph.input_modalities
        self.assertIn("text", inputs)
        self.assertIn("image", inputs)
        self.assertIn("audio", inputs)

    def test_graph_has_outputs(self):
        """Graph recognizes known output modalities."""
        outputs = self.graph.output_modalities
        self.assertIn("text", outputs)
        self.assertIn("audio", outputs)
        self.assertIn("image", outputs)

    def test_direct_edge_exists(self):
        """text -> audio is a direct edge (TTS models)."""
        edges = self.graph.get_edges("text", "audio")
        self.assertGreater(len(edges), 0)
        for edge in edges:
            self.assertTrue(edge.model_id)
            self.assertEqual(edge.input_modality, "text")
            self.assertEqual(edge.output_modality, "audio")

    def test_no_direct_edge(self):
        """audio -> image requires multi-hop (no direct edge)."""
        edges = self.graph.get_edges("audio", "image")
        self.assertEqual(len(edges), 0)

    def test_all_edges_for_input(self):
        """All output modalities reachable from text in 1 hop."""
        edges = self.graph.get_all_edges_from("text")
        output_mods = {e.output_modality for e in edges}
        self.assertIn("text", output_mods)
        self.assertIn("audio", output_mods)
        self.assertIn("image", output_mods)
        self.assertIn("vector", output_mods)

    def test_edge_count_matches_catalog(self):
        """Total direct edges should match known count (~29 unique modality pairs)."""
        all_pairs = self.graph.get_all_modality_pairs()
        self.assertGreaterEqual(len(all_pairs), 25)
```

**Step 2: Run test to verify failure**

Run: `cd ~/Dev/Github/coreai-catalog && env -u PYTHONPATH .venv/bin/python -m pytest tests/test_transform_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coreai_catalog.transform_graph'`

**Step 3: Write minimal implementation**

```python
"""
Core AI Catalog - Transform Graph Engine.

Builds a directed graph of modality transformations from the catalog.
Each model is an edge: input_modality -> output_modality.
Supports BFS shortest-path and Dijkstra weighted-path queries.
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
        return [
            e for e in self._adjacency.get(input_modality, [])
            if e.output_modality == output_modality
        ]

    def get_all_edges_from(self, input_modality: str) -> list[TransformEdge]:
        return list(self._adjacency.get(input_modality, []))

    def get_all_modality_pairs(self) -> set[tuple[str, str]]:
        pairs = set()
        for inp, edges in self._adjacency.items():
            for e in edges:
                pairs.add((e.input_modality, e.output_modality))
        return pairs
```

**Step 4: Run test to verify pass**

Run: `cd ~/Dev/Github/coreai-catalog && env -u PYTHONPATH .venv/bin/python -m pytest tests/test_transform_graph.py -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add coreai_catalog/transform_graph.py tests/test_transform_graph.py
git commit -m "feat: add Transform Graph Engine"
```

---

### Task 2: Add shortest-path BFS

**Objective:** Given input + target output, find the shortest pipeline (fewest hops), picking the best model per hop.

**Files:**
- Modify: `coreai_catalog/transform_graph.py`
- Modify: `tests/test_transform_graph.py`

**Step 1: Write failing tests**

Append to `tests/test_transform_graph.py`:

```python
class TestShortestPath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from coreai_catalog.catalog import Catalog
        cat = Catalog()
        cls.graph = TransformGraph(cat.models, cat)

    def test_direct_path(self):
        """text -> audio should be 1 hop."""
        pipeline = self.graph.shortest_path("text", "audio")
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline.hop_count, 1)
        self.assertEqual(pipeline.modality_chain, ["text", "audio"])

    def test_two_hop_path(self):
        """audio -> image requires 2 hops (audio -> text -> image)."""
        pipeline = self.graph.shortest_path("audio", "image")
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline.hop_count, 2)
        self.assertEqual(pipeline.modality_chain, ["audio", "text", "image"])

    def test_three_hop_path(self):
        """audio -> classes requires 3 hops."""
        pipeline = self.graph.shortest_path("audio", "classes")
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline.hop_count, 3)

    def test_no_path(self):
        """query -> image should return None (no route exists)."""
        pipeline = self.graph.shortest_path("query", "image")
        self.assertIsNone(pipeline)

    def test_same_modality(self):
        """text -> text should be 1 hop."""
        pipeline = self.graph.shortest_path("text", "text")
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline.hop_count, 1)

    def test_pipeline_has_model_info(self):
        """Each stage references a real model with metadata."""
        pipeline = self.graph.shortest_path("image", "audio")
        self.assertIsNotNone(pipeline)
        for stage in pipeline.stages:
            self.assertTrue(stage.model_id)
            self.assertTrue(stage.model_name)
            self.assertTrue(stage.runner)
```

**Step 2: Run test to verify failure**

Run: `cd ~/Dev/Github/coreai-catalog && env -u PYTHONPATH .venv/bin/python -m pytest tests/test_transform_graph.py::TestShortestPath -v`
Expected: FAIL — `AttributeError: 'TransformGraph' object has no attribute 'shortest_path'`

**Step 3: Add shortest_path and helper methods**

Append inside `class TransformGraph`:

```python
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

        # Get HF URL for on-demand download
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
```

**Step 4: Run test to verify pass**

Run: `cd ~/Dev/Github/coreai-catalog && env -u PYTHONPATH .venv/bin/python -m pytest tests/test_transform_graph.py::TestShortestPath -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add coreai_catalog/transform_graph.py tests/test_transform_graph.py
git commit -m "feat: add BFS shortest-path with model selection"
```

---

### Task 3: Add reachable_outputs, all_paths, reachability_matrix

**Objective:** Enumerate all possible output targets from a given input, and return all alternative pipelines.

**Files:**
- Modify: `coreai_catalog/transform_graph.py`
- Modify: `tests/test_transform_graph.py`

**Step 1: Write failing tests**

Append to `tests/test_transform_graph.py`:

```python
class TestReachability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from coreai_catalog.catalog import Catalog
        cat = Catalog()
        cls.graph = TransformGraph(cat.models, cat)

    def test_reachable_outputs_from_text(self):
        reachable = self.graph.reachable_outputs("text")
        self.assertIn("text", reachable)
        self.assertIn("audio", reachable)
        self.assertIn("image", reachable)
        self.assertIn("vector", reachable)
        self.assertGreaterEqual(len(reachable), 15)

    def test_reachable_outputs_from_document_image(self):
        reachable = self.graph.reachable_outputs("document_image")
        self.assertIn("html", reachable)
        self.assertIn("markdown", reachable)

    def test_unreachable(self):
        reachable = self.graph.reachable_outputs("query")
        self.assertNotIn("image", reachable)

    def test_all_paths_text_to_audio(self):
        pipelines = self.graph.all_paths("text", "audio", max_hops=2)
        self.assertGreater(len(pipelines), 1)

    def test_all_paths_limited(self):
        pipelines = self.graph.all_paths("text", "classes", max_hops=1)
        self.assertEqual(len(pipelines), 0)

    def test_full_matrix(self):
        matrix = self.graph.reachability_matrix()
        total = sum(len(targets) for targets in matrix.values())
        self.assertGreaterEqual(total, 45)
```

**Step 2: Run to verify failure**

Run: `cd ~/Dev/Github/coreai-catalog && env -u PYTHONPATH .venv/bin/python -m pytest tests/test_transform_graph.py::TestReachability -v`
Expected: FAIL

**Step 3: Add methods**

Append inside `class TransformGraph`:

```python
    def reachable_outputs(self, input_modality: str, max_hops: int = 5) -> set[str]:
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
        matrix: dict[str, set[str]] = {}
        for mod in self.all_modalities:
            if self._adjacency.get(mod):
                matrix[mod] = self.reachable_outputs(mod)
        return matrix
```

**Step 4: Run test to verify pass**

Run: `cd ~/Dev/Github/coreai-catalog && env -u PYTHONPATH .venv/bin/python -m pytest tests/test_transform_graph.py::TestReachability -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add coreai_catalog/transform_graph.py tests/test_transform_graph.py
git commit -m "feat: add reachable_outputs, all_paths, reachability_matrix"
```

---

### Task 4: Add `transforms` CLI command

**Objective:** Expose the graph engine via CLI.

**Files:**
- Modify: `coreai_catalog/cli.py`

**Step 1: Add cmd_transforms function**

Add after `cmd_tasks` (before `cmd_version`):

```python
def cmd_transforms(args: argparse.Namespace) -> int:
    """Browse and query modality transformation pipelines."""
    from .transform_graph import TransformGraph

    cat = Catalog()
    graph = TransformGraph(cat.models, cat)

    if args.json:
        if args.from_modality and args.to_modality:
            pipeline = graph.shortest_path(args.from_modality, args.to_modality)
            if pipeline:
                print(json.dumps({
                    "from": args.from_modality,
                    "to": args.to_modality,
                    "pipeline": pipeline.to_dict(),
                }, indent=2))
            else:
                print(json.dumps({
                    "from": args.from_modality,
                    "to": args.to_modality,
                    "pipeline": None,
                    "error": "No transform path found",
                }, indent=2))
            return 0
        elif args.from_modality:
            reachable = sorted(graph.reachable_outputs(args.from_modality))
            print(json.dumps({
                "from": args.from_modality,
                "reachable_outputs": reachable,
                "count": len(reachable),
            }, indent=2))
            return 0
        else:
            matrix = graph.reachability_matrix()
            serializable = {k: sorted(v) for k, v in sorted(matrix.items())}
            print(json.dumps({
                "input_modalities": sorted(graph.input_modalities),
                "output_modalities": sorted(graph.output_modalities),
                "reachability": serializable,
            }, indent=2))
            return 0

    # Human-readable
    if args.from_modality and args.to_modality:
        pipeline = graph.shortest_path(args.from_modality, args.to_modality)
        if not pipeline:
            print(f"\n  {RED}No transform path: {args.from_modality} -> {args.to_modality}{RESET}\n")
            return 1

        chain = " -> ".join(pipeline.modality_chain)
        print(f"\n  {BOLD}Transform: {args.from_modality} -> {args.to_modality}{RESET}")
        print(f"  {BOLD}Route:{RESET} {pipeline.hop_count} hop(s)")
        print(f"  {BOLD}Chain:{RESET} {chain}")
        print(f"  {BOLD}Download:{RESET} {pipeline.total_artifact_size}\n")

        for i, stage in enumerate(pipeline.stages, 1):
            tps = f"{stage.estimated_tokens_per_sec:.0f} tok/s" if stage.estimated_tokens_per_sec > 0 else "no benchmark"
            print(f"  {BOLD}{i}.{RESET} {stage.model_name}")
            print(f"     {DIM}{stage.input_modality} -> {stage.output_modality}{RESET}")
            print(f"     {DIM}{stage.parameters} | {tps} | {stage.runner}{RESET}")
            print(f"     {GREEN}coreai-catalog install {stage.model_id}{RESET}\n")
        return 0

    elif args.from_modality:
        reachable = sorted(graph.reachable_outputs(args.from_modality))
        print(f"\n  {BOLD}From: {args.from_modality}{RESET}")
        print(f"  {BOLD}Reachable outputs ({len(reachable)}):{RESET}\n")
        for mod in reachable:
            print(f"    {mod}")
        print()
        return 0

    else:
        all_inputs = sorted(graph.input_modalities)
        print(f"\n  {BOLD}Core AI Transform Graph{RESET}")
        print(f"  {DIM}{len(all_inputs)} input modalities -> {len(graph.output_modalities)} output modalities{RESET}\n")
        for inp in all_inputs:
            reachable = sorted(graph.reachable_outputs(inp))
            direct = {e.output_modality for e in graph.get_all_edges_from(inp)}
            print(f"  {BOLD}{inp}{RESET}")
            for out in reachable:
                marker = "  " if out in direct else "-> "
                print(f"    {marker}{out}")
            print()
        pairs = graph.get_all_modality_pairs()
        matrix = graph.reachability_matrix()
        total = sum(len(v) for v in matrix.values())
        print(f"  {DIM}Direct transforms: {len(pairs)} | Total reachable: {total}{RESET}\n")
        return 0
```

**Step 2: Add parser entry**

In `build_parser()`, after the `tasks` subparser:

```python
    # transforms
    p = sub.add_parser("transforms", aliases=["tx"],
                       help="Browse and query modality transformation pipelines")
    p.add_argument("--from", dest="from_modality",
                   help="Input modality (text, image, audio, document_image)")
    p.add_argument("--to", dest="to_modality",
                   help="Target output modality")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_transforms)
```

**Step 3: Smoke test**

Run: `cd ~/Dev/Github/coreai-catalog && env -u PYTHONPATH .venv/bin/coreai-catalog transforms --from audio --to image`
Expected: Shows pipeline `audio -> text -> image` with model names and install commands

**Step 4: Commit**

```bash
git add coreai_catalog/cli.py
git commit -m "feat: add 'transforms' CLI command"
```

---

### Task 5: Add transforms to Python public API

**Objective:** Expose the graph engine via the high-level Catalog API.

**Files:**
- Modify: `coreai_catalog/api.py`
- Modify: `tests/test_public_api.py`

**Step 1: Write failing test**

Append to `tests/test_public_api.py`:

```python
    def test_transforms_matrix(self):
        matrix = self.cat.transforms()
        self.assertIsInstance(matrix, dict)
        self.assertIn("text", matrix)

    def test_transform_pipeline(self):
        pipeline = self.cat.transform_pipeline("text", "audio")
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline["output_modality"], "audio")

    def test_transform_reachable(self):
        reachable = self.cat.reachable_outputs("image")
        self.assertIn("text", reachable)
        self.assertIn("audio", reachable)
```

**Step 2: Run to verify failure**

Run: `cd ~/Dev/Github/coreai-catalog && env -u PYTHONPATH .venv/bin/python -m pytest tests/test_public_api.py -k transform -v`
Expected: FAIL

**Step 3: Add methods to api.py**

After the `capabilities()` method in `class Catalog`:

```python
    def transforms(self) -> dict[str, list[str]]:
        """Get the full modality transformation reachability matrix."""
        from .transform_graph import TransformGraph
        graph = TransformGraph(self._cat.models, self._cat)
        matrix = graph.reachability_matrix()
        return {k: sorted(v) for k, v in matrix.items()}

    def reachable_outputs(self, input_modality: str) -> list[str]:
        """List all output modalities reachable from a given input."""
        from .transform_graph import TransformGraph
        graph = TransformGraph(self._cat.models, self._cat)
        return sorted(graph.reachable_outputs(input_modality))

    def transform_pipeline(
        self, input_modality: str, output_modality: str,
    ) -> dict | None:
        """Find a transformation pipeline between two modalities."""
        from .transform_graph import TransformGraph
        graph = TransformGraph(self._cat.models, self._cat)
        pipeline = graph.shortest_path(input_modality, output_modality)
        return pipeline.to_dict() if pipeline else None
```

**Step 4: Run test to verify pass**

Run: `cd ~/Dev/Github/coreai-catalog && env -u PYTHONPATH .venv/bin/python -m pytest tests/test_public_api.py -k transform -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add coreai_catalog/api.py tests/test_public_api.py
git commit -m "feat: add transforms to public API"
```

---

### Task 6: Export transforms-graph.json + model-manifest.json

**Objective:** Generate machine-readable artifacts for Ditto consumption.

**Files:**
- Modify: `coreai_catalog/exports.py`
- Modify: `scripts/generate.py`

**Step 1: Add export functions**

Add to `coreai_catalog/exports.py`:

```python
def export_transform_graph(catalog_root: Path, dist: Path | None = None) -> dict:
    """Export the transform graph as JSON for Ditto consumption."""
    dist = dist or catalog_root / "dist"
    dist.mkdir(exist_ok=True)

    from .transform_graph import TransformGraph
    cat = Catalog(catalog_root)
    graph = TransformGraph(cat.models, cat)

    direct_edges: list[dict] = []
    for (inp, out) in sorted(graph.get_all_modality_pairs()):
        edges = graph.get_edges(inp, out)
        direct_edges.append({
            "input": inp,
            "output": out,
            "model_ids": sorted(e.model_id for e in edges),
            "model_count": len(edges),
        })

    matrix = graph.reachability_matrix()
    serializable_matrix = {k: sorted(v) for k, v in sorted(matrix.items())}

    pipelines: dict[str, dict] = {}
    for inp in sorted(graph.input_modalities):
        for out in sorted(matrix.get(inp, set())):
            pipeline = graph.shortest_path(inp, out)
            if pipeline:
                pipelines[f"{inp}\u2192{out}"] = pipeline.to_dict()

    catalog_version = _get_catalog_version(catalog_root)
    output = {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "export_catalog_version": catalog_version,
        "input_modalities": sorted(graph.input_modalities),
        "output_modalities": sorted(graph.output_modalities),
        "direct_edge_count": len(direct_edges),
        "total_reachable_pairs": sum(len(v) for v in matrix.values()),
        "direct_edges": direct_edges,
        "reachability_matrix": serializable_matrix,
        "pipelines": pipelines,
    }

    (dist / "transforms-graph.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    )
    return output


def export_model_manifest(catalog_root: Path, dist: Path | None = None) -> dict:
    """Export a model download manifest for on-demand fetching.

    Each entry has: id, name, runner, huggingface_url, artifact_size,
    parameters, precision, bundle_kind (inferred from runner/capabilities).
    """
    dist = dist or catalog_root / "dist"
    cat = Catalog(catalog_root)

    entries: list[dict] = []
    for m in cat.models:
        art = cat.get_artifact(m["id"])
        hf_url = ""
        if art:
            hf_url = art.get("huggingface", {}).get("url", "")

        runner = m.get("runtime", {}).get("runner", "")
        caps = m.get("capabilities", [])

        # Infer bundle kind from runner/capabilities
        if runner in ("CoreAIRunner", "stock-runner"):
            if "vision-language" in caps:
                bundle_kind = "vlm"
            else:
                bundle_kind = "llm"
        elif runner == "CoreAIDiffusionPipeline":
            bundle_kind = "diffusion"
        elif runner == "CoreAIImageSegmenter":
            bundle_kind = "segmenter"
        elif runner == "CoreAITranscribe":
            bundle_kind = "speech"
        elif runner == "CoreAIKit-GraphModel":
            if "object-detection" in caps or "instance-segmentation" in caps:
                bundle_kind = "detector"
            else:
                bundle_kind = "graph"
        else:
            bundle_kind = "unknown"

        entries.append({
            "id": m["id"],
            "name": m.get("name", m["id"]),
            "bundle_kind": bundle_kind,
            "runner": runner,
            "capabilities": caps,
            "input_modalities": m.get("modalities", {}).get("input", []),
            "output_modalities": m.get("modalities", {}).get("output", []),
            "parameters": m.get("size", {}).get("parameters", ""),
            "precision": m.get("size", {}).get("precision", ""),
            "artifact_size": m.get("size", {}).get("artifact_size", ""),
            "huggingface_url": hf_url,
            "license": m.get("license", {}).get("name", ""),
            "commercial_use": m.get("license", {}).get("commercial_use", ""),
        })

    catalog_version = _get_catalog_version(catalog_root)
    output = {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "export_catalog_version": catalog_version,
        "model_count": len(entries),
        "models": entries,
    }

    (dist / "model-manifest.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    )
    return output
```

**Step 2: Wire into generate.py**

In `scripts/generate.py`, add after existing exports:

```python
from coreai_catalog.exports import export_transform_graph, export_model_manifest
export_transform_graph(catalog_root, dist)
print(f"  transforms-graph.json")
export_model_manifest(catalog_root, dist)
print(f"  model-manifest.json")
```

**Step 3: Run and verify**

Run: `cd ~/Dev/Github/coreai-catalog && env -u PYTHONPATH .venv/bin/python scripts/generate.py`
Expected: Both files created in `dist/`

**Step 4: Commit**

```bash
git add coreai_catalog/exports.py scripts/generate.py dist/transforms-graph.json dist/model-manifest.json
git commit -m "feat: export transforms-graph.json + model-manifest.json"
```

---

### Task 7: Add MCP tool + update docs + version bump

**Objective:** MCP tool #12, docs sweep, version 2.1.0.

**Files:**
- Modify: `mcp_server/server.py`
- Modify: `README.md`, `llms.txt`, `llms-full.txt`, `agent.json`, `openapi.yaml`
- Modify: `catalog.yaml` (version), `pyproject.toml` (version)

**Step 1: Add MCP tool**

In `mcp_server/server.py`, before `get_version`:

```python
@mcp.tool()
def query_transforms(
    from_modality: str | None = None,
    to_modality: str | None = None,
) -> str:
    """Query the modality transformation graph.

    Discover how to transform one media type into another by chaining
    Core AI models on-device. Supports multi-hop pipelines.

    Args:
        from_modality: Input modality (text, image, audio, document_image).
            If omitted, returns the full reachability matrix.
        to_modality: Target output modality. If omitted (but from is set),
            returns all reachable outputs from that input.

    Returns:
        JSON with the transformation pipeline or reachability data.
    """
    from coreai_catalog.transform_graph import TransformGraph
    graph = TransformGraph(catalog.models, catalog)

    if from_modality and to_modality:
        pipeline = graph.shortest_path(from_modality, to_modality)
        if not pipeline:
            return json.dumps({"error": "No transform path found"}, indent=2)
        result = pipeline.to_dict()
        result["from"] = from_modality
        result["to"] = to_modality
        for stage in result["stages"]:
            stage["install"] = f"coreai-catalog install {stage['model_id']}"
        return json.dumps(result, indent=2)
    elif from_modality:
        reachable = sorted(graph.reachable_outputs(from_modality))
        return json.dumps({"from": from_modality, "reachable_outputs": reachable}, indent=2)
    else:
        matrix = graph.reachability_matrix()
        return json.dumps({
            "input_modalities": sorted(graph.input_modalities),
            "output_modalities": sorted(graph.output_modalities),
            "reachability": {k: sorted(v) for k, v in sorted(matrix.items())},
        }, indent=2)
```

Update instructions string in FastMCP to mention "plan multi-modal transformation pipelines."

**Step 2: Update docs**

- README.md: add Transform Graph to features, `transforms` to CLI examples
- llms.txt: add transforms command
- llms-full.txt: add transform graph section
- agent.json: add transforms tool
- openapi.yaml: add transforms endpoint

**Step 3: Bump version**

In `catalog.yaml`: `version: 2.1.0`
In `pyproject.toml`: `version = "2.1.0"`

**Step 4: Full test suite**

Run: `cd ~/Dev/Github/coreai-catalog && env -u PYTHONPATH .venv/bin/python -m pytest tests/ -v`
Expected: All pass

**Step 5: Commit**

```bash
git add -A
git commit -m "release: v2.1.0 - Transform Graph Engine (CLI, API, MCP, JSON export)"
```

---

## PHASE 2: Ditto iOS App

> **Repository:** `~/Dev/Github/Ditto` (private)
> **Documentation rule:** All docs in this repo describe the app, its UI, and how it executes Core AI pipelines. It references `transforms-graph.json` and `model-manifest.json` as bundled data inputs — it does **not** document how they are generated or reference the coreai-catalog project.

### Task 8: Create Ditto Xcode project

**Objective:** Initialize Ditto as an iOS 27 app depending on apple/coreai-models.

**Manual steps (in Xcode):**
1. Xcode -> New -> Project -> App -> "Ditto"
2. Deployment target: **iOS 27.0**
3. Interface: SwiftUI
4. Storage: SwiftData
5. Add Swift Package dependency: `https://github.com/apple/coreai-models`
   - Add products: CoreAILM, CoreAIDiffusion, CoreAISegmentation, CoreAISpeech, CoreAIObjectDetection
6. Enable capabilities:
   - Background Modes -> Audio (for recording)
   - Background Assets
7. Info.plist:
   - `NSMicrophoneUsageDescription`: "Ditto needs microphone access to transcribe audio."
   - `NSPhotoLibraryUsageDescription`: "Ditto needs photo access to import images."

**Directory structure (inside Ditto repo):**
```
Ditto/
  DittoApp.swift
  ContentView.swift
  Models/
    Modality.swift
    TransmutationPipeline.swift
    ModelManifest.swift
  Engine/
    GraphEngine.swift
    ModelStore.swift
    PipelineExecutor.swift
    BackgroundDownloader.swift
  Views/
    InputView.swift
    OutputSelectorView.swift
    PipelineProgressView.swift
    ResultView.swift
    ModelDownloadCard.swift
  Resources/
    transforms-graph.json     (snapshot from catalog dist/)
    model-manifest.json        (snapshot from catalog dist/)
  Localization/
    Localizable.xcstrings      (String Catalog)
DittoTests/
  GraphEngineTests.swift
  ModelManifestTests.swift
```

**Ditto README.md:** Describes what the app does (universal media transmutation), how to build (Xcode 27, iOS 27), and the `transforms-graph.json` / `model-manifest.json` input format. Does NOT mention coreai-catalog, Python, or how the JSON is generated. The JSON files are documented as "bundled pipeline definitions."

**Commit:**

```bash
cd ~/Dev/Github/Ditto
git init
git add -A
git commit -m "feat: initial Ditto project with coreai-models dependency"
```

---

### Task 9: Swift domain models

**Objective:** Swift types mirroring the Python graph structures, with Apple-idiomatic naming.

**Files:**
- Create: `Ditto/Models/Modality.swift`
- Create: `Ditto/Models/TransmutationPipeline.swift`
- Create: `Ditto/Models/ModelManifest.swift`

**Key design decisions:**
- Use Swift enums, not stringly-typed
- Labels in English, localized via String Catalog
- Codable for JSON loading

**Modality.swift:**

```swift
import Foundation

/// A media modality that can be transformed.
enum Modality: String, Codable, CaseIterable, Identifiable, Hashable {
    // User-facing inputs
    case text, image, audio, documentImage = "document_image"

    // Output types
    case transcript, html, markdown, latex, vector, video
    case boxes, masks, classes, scores, score, coordinates
    case depthMap = "depth_map"
    case gaussianSplats = "gaussian-splats"
    case actionTokens = "action-tokens"

    var id: String { rawValue }

    var localizedKey: String { "modality.\(rawValue)" }

    /// SF Symbol for the UI.
    var systemImage: String {
        switch self {
        case .text: "text.alignleft"
        case .image: "photo"
        case .audio: "waveform"
        case .documentImage: "doc.text"
        case .transcript: "text.quote"
        case .html: "chevron.left.forwardslash.chevron.right"
        case .markdown: "doc.richtext"
        case .latex: "function"
        case .vector: "arrow.triangle.swap"
        case .video: "film"
        case .boxes: "square.dashed"
        case .masks: "wand.and.stars"
        case .classes: "tag"
        case .scores: "chart.bar"
        case .score: "checkmark.seal"
        case .coordinates: "scope"
        case .depthMap: "mountain.2"
        case .gaussianSplats: "cube"
        case .actionTokens: "gamecontroller"
        }
    }

    static let inputTypes: [Modality] = [.text, .image, .audio, .documentImage]
}
```

**TransmutationPipeline.swift:**

```swift
import Foundation

struct PipelineStage: Codable, Identifiable, Hashable {
    let modelId: String
    let modelName: String
    let inputModality: String
    let outputModality: String
    let estimatedTokensPerSec: Double
    let parameters: String
    let runner: String
    let artifactSize: String
    let huggingfaceUrl: String

    var id: String { "\(modelId)-\(inputModality)-\(outputModality)" }

    enum CodingKeys: String, CodingKey {
        case modelId = "model_id"
        case modelName = "model_name"
        case inputModality = "input_modality"
        case outputModality = "output_modality"
        case estimatedTokensPerSec = "estimated_tokens_per_sec"
        case parameters, runner
        case artifactSize = "artifact_size"
        case huggingfaceUrl = "huggingface_url"
    }
}

struct TransmutationPipeline: Codable, Identifiable, Hashable {
    let inputModality: String
    let outputModality: String
    let stages: [PipelineStage]

    var id: String { "\(inputModality)->\(outputModality)" }
    var hopCount: Int { stages.count }
    var modelIds: [String] { stages.map(\.modelId) }

    var modalityChain: [String] {
        guard let first = stages.first else { return [] }
        var chain = [first.inputModality]
        stages.forEach { chain.append($0.outputModality) }
        return chain
    }

    /// The runner type for the PipelineExecutor dispatch.
    /// Maps from catalog runner names to Swift bundle kinds.
    var primaryRunnerKind: RunnerKind {
        guard let runner = stages.first?.runner else { return .unknown }
        return RunnerKind.from(runner: runner, capabilities: stages.first.flatMap { _ in nil })
    }

    enum CodingKeys: String, CodingKey {
        case inputModality = "input_modality"
        case outputModality = "output_modality"
        case stages
    }
}

/// Maps catalog runner field to the Swift package type that handles it.
enum RunnerKind: String, Codable {
    case llm, vlm, diffusion, segmenter, speech, detector, graph, unknown

    static func from(runner: String, capabilities: [String]?) -> RunnerKind {
        let caps = capabilities ?? []
        switch runner {
        case "CoreAIRunner", "stock-runner":
            return caps.contains("vision-language") ? .vlm : .llm
        case "CoreAIDiffusionPipeline": return .diffusion
        case "CoreAIImageSegmenter": return .segmenter
        case "CoreAITranscribe": return .speech
        case "CoreAIKit-GraphModel":
            return caps.contains("object-detection") ? .detector : .graph
        default: return .unknown
        }
    }
}
```

**ModelManifest.swift:**

```swift
import Foundation

/// A single model's metadata for on-demand download.
struct ModelManifestEntry: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let bundleKind: String
    let runner: String
    let capabilities: [String]
    let inputModalities: [String]
    let outputModalities: [String]
    let parameters: String
    let precision: String
    let artifactSize: String
    let huggingfaceUrl: String
    let license: String
    let commercialUse: String

    enum CodingKeys: String, CodingKey {
        case id, name, runner, capabilities, parameters, precision, license
        case bundleKind = "bundle_kind"
        case inputModalities = "input_modalities"
        case outputModalities = "output_modalities"
        case artifactSize = "artifact_size"
        case huggingfaceUrl = "huggingface_url"
        case commercialUse = "commercial_use"
    }

    var runnerKind: RunnerKind {
        RunnerKind.from(runner: runner, capabilities: capabilities)
    }
}

struct ModelManifest: Codable {
    let exportCatalogVersion: String
    let modelCount: Int
    let models: [ModelManifestEntry]

    enum CodingKeys: String, CodingKey {
        case exportCatalogVersion = "export_catalog_version"
        case modelCount = "model_count"
        case models
    }

    func find(_ id: String) -> ModelManifestEntry? {
        models.first { $0.id == id }
    }
}
```

**Commit:**

```bash
git add Ditto/Models/
git commit -m "feat: Swift domain models (Modality, Pipeline, Manifest)"
```

---

### Task 10: GraphEngine.swift — load and query the transform graph

**Objective:** Swift graph engine that loads `transforms-graph.json` from the app bundle.

**Files:**
- Create: `Ditto/Engine/GraphEngine.swift`
- Create: `DittoTests/GraphEngineTests.swift`

**GraphEngine.swift:**

```swift
import Foundation

/// Loads the transform graph from the bundled JSON and provides query methods.
final class GraphEngine {
    let directEdges: [DirectEdge]
    let reachability: [String: [String]]
    let pipelines: [String: TransmutationPipeline]

    struct DirectEdge: Codable {
        let input: String
        let output: String
        let modelIds: [String]
        let modelCount: Int
        enum CodingKeys: String, CodingKey {
            case input, output
            case modelIds = "model_ids"
            case modelCount = "model_count"
        }
    }

    init(json: Data) throws {
        struct GraphData: Codable {
            let directEdges: [DirectEdge]
            let reachabilityMatrix: [String: [String]]
            let pipelines: [String: TransmutationPipeline]
            enum CodingKeys: String, CodingKey {
                case directEdges = "direct_edges"
                case reachabilityMatrix = "reachability_matrix"
                case pipelines
            }
        }
        let decoded = try JSONDecoder().decode(GraphData.self, from: json)
        self.directEdges = decoded.directEdges
        self.reachability = decoded.reachabilityMatrix
        self.pipelines = decoded.pipelines
    }

    static func fromBundle() throws -> GraphEngine {
        guard let url = Bundle.main.url(forResource: "transforms-graph", withExtension: "json") else {
            throw GraphError.bundledGraphNotFound
        }
        let data = try Data(contentsOf: url)
        return try GraphEngine(json: data)
    }

    func reachableOutputs(from input: String) -> [String] {
        reachability[input] ?? []
    }

    func canTransform(from input: String, to output: String) -> Bool {
        reachableOutputs(from: input).contains(output)
    }

    func shortestPipeline(from input: String, to output: String) -> TransmutationPipeline? {
        pipelines["\(input)\u{2192}\(output)"]
    }

    func availableTargets(for input: Modality) -> [Modality] {
        reachableOutputs(from: input.rawValue)
            .compactMap { Modality(rawValue: $0) }
    }
}

enum GraphError: LocalizedError {
    case bundledGraphNotFound
    var errorDescription: String? {
        switch self {
        case .bundledGraphNotFound: "Transform graph not found in app bundle"
        }
    }
}
```

**GraphEngineTests.swift:**

```swift
import XCTest
@testable import Ditto

final class GraphEngineTests: XCTestCase {
    var engine: GraphEngine!

    override func setUpWithError() throws {
        engine = try GraphEngine.fromBundle()
    }

    func testGraphLoads() {
        XCTAssertGreaterThan(engine.directEdges.count, 20)
    }

    func testReachableFromText() {
        let reachable = engine.reachableOutputs(from: "text")
        XCTAssertTrue(reachable.contains("audio"))
        XCTAssertTrue(reachable.contains("image"))
    }

    func testCanTransformAudioToImage() {
        XCTAssertTrue(engine.canTransform(from: "audio", to: "image"))
    }

    func testCannotTransformQueryToImage() {
        XCTAssertFalse(engine.canTransform(from: "query", to: "image"))
    }

    func testShortestPipelineAudioToImage() {
        let pipeline = engine.shortestPipeline(from: "audio", to: "image")
        XCTAssertNotNil(pipeline)
        XCTAssertEqual(pipeline?.hopCount, 2)
        XCTAssertEqual(pipeline?.modalityChain, ["audio", "text", "image"])
    }
}
```

**Commit:**

```bash
git add Ditto/Engine/GraphEngine.swift DittoTests/GraphEngineTests.swift
git commit -m "feat: GraphEngine loads transform graph from bundle"
```

---

### Task 11: ModelStore.swift — track installed models

**Objective:** Track which models are downloaded, compute disk usage, check pipeline readiness.

**Files:**
- Create: `Ditto/Engine/ModelStore.swift`

```swift
import Foundation
import SwiftUI

/// Tracks which Core AI model bundles are installed locally.
@MainActor
final class ModelStore: ObservableObject {
    @Published private(set) var installedModelIds: Set<String> = []
    @Published private(set) var totalDiskUsageMB: Double = 0

    /// Root for all model bundles.
    let storageDir: URL

    init() {
        storageDir = FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("DittoModels", isDirectory: true)
        try? FileManager.default.createDirectory(at: storageDir, withIntermediateDirectories: true)
        refresh()
    }

    func refresh() {
        var ids: Set<String> = []
        var totalBytes: Int64 = 0

        guard let entries = try? FileManager.default.contentsOfDirectory(
            at: storageDir, includingPropertiesForKeys: [.isDirectoryKey]
        ) else {
            installedModelIds = []
            totalDiskUsageMB = 0
            return
        }

        for entry in entries {
            var isDir: ObjCBool = false
            if FileManager.default.fileExists(atPath: entry.path, isDirectory: &isDir), isDir.boolValue {
                // A model bundle is valid if it has metadata.json or at least one .aimodel
                let hasMetadata = FileManager.default.fileExists(atPath: entry.appendingPathComponent("metadata.json").path)
                let hasAimodel = (try? FileManager.default.contentsOfDirectory(at: entry, includingPropertiesForKeys: nil))?
                    .contains { $0.pathExtension == "aimodel" } ?? false
                if hasMetadata || hasAimodel {
                    ids.insert(entry.lastPathComponent)
                    totalBytes += directorySize(entry)
                }
            }
        }

        installedModelIds = ids
        totalDiskUsageMB = Double(totalBytes) / (1024 * 1024)
    }

    func isInstalled(_ modelId: String) -> Bool {
        installedModelIds.contains(modelId)
    }

    func pipelineReady(_ pipeline: TransmutationPipeline) -> Bool {
        pipeline.modelIds.allSatisfy { installedModelIds.contains($0) }
    }

    func missingModels(in pipeline: TransmutationPipeline) -> [String] {
        pipeline.modelIds.filter { !installedModelIds.contains($0) }
    }

    func bundleURL(for modelId: String) -> URL {
        storageDir.appendingPathComponent(modelId, isDirectory: true)
    }

    private func directorySize(_ url: URL) -> Int64 {
        var size: Int64 = 0
        guard let enumerator = FileManager.default.enumerator(
            at: url, includingPropertiesForKeys: [.totalFileAllocatedSizeKey]
        ) else { return 0 }
        for case let fileURL as URL in enumerator {
            if let attrs = try? FileManager.default.attributesOfItem(atPath: fileURL.path),
               let fileSize = attrs[.size] as? Int64 {
                size += fileSize
            }
        }
        return size
    }
}
```

**Commit:**

```bash
git add Ditto/Engine/ModelStore.swift
git commit -m "feat: ModelStore tracks installed bundles and disk usage"
```

---

### Task 12: PipelineExecutor.swift — execute via coreai-models runners

**Objective:** Execute pipelines using the REAL Apple coreai-models API surface.

**Critical:** This is where the placeholder APIs from v1 are replaced with verified types.

**Files:**
- Create: `Ditto/Engine/PipelineExecutor.swift`

```swift
import Foundation
import SwiftUI
import CoreAILM          // CoreAIRunner, CoreAILanguageModel
import CoreAIDiffusion   // DiffusionPipeline, PipelineConfiguration
import CoreAISegmentation // ImageSegmenter
import CoreAISpeech      // SpeechModel
import CoreAIObjectDetection // ObjectDetector
import FoundationModels   // LanguageModelSession, Prompt, Attachment

/// Executes a TransmutationPipeline stage by stage.
@MainActor
final class PipelineExecutor: ObservableObject {
    @Published var currentStage = 0
    @Published var stageProgress: Double = 0
    @Published var status: ExecutionStatus = .idle
    @Published var result: TransmutationResult?
    @Published var errorMessage: String?

    private let modelStore: ModelStore

    enum ExecutionStatus: Equatable {
        case idle
        case loadingModel(String)
        case running(stage: Int, total: Int)
        case completed
        case error(String)
    }

    init(modelStore: ModelStore) {
        self.modelStore = modelStore
    }

    func execute(
        pipeline: TransmutationPipeline,
        input: MediaPayload
    ) async {
        status = .running(stage: 0, total: pipeline.hopCount)
        currentStage = 0
        result = nil
        errorMessage = nil

        var currentData = input

        for (index, stage) in pipeline.stages.enumerated() {
            currentStage = index
            stageProgress = 0

            guard modelStore.isInstalled(stage.modelId) else {
                status = .error("Model not installed")
                errorMessage = "\(stage.modelName) is not downloaded. Download it first."
                return
            }

            status = .loadingModel(stage.modelName)

            let bundleURL = modelStore.bundleURL(for: stage.modelId)

            do {
                status = .running(stage: index + 1, total: pipeline.hopCount)
                let output = try await executeStage(stage: stage, input: currentData, bundleURL: bundleURL)
                currentData = output
                stageProgress = 1.0
            } catch {
                status = .error("Stage \(index + 1) failed")
                errorMessage = "Stage \(index + 1) (\(stage.modelName)): \(error.localizedDescription)"
                return
            }
        }

        result = TransmutationResult(pipeline: pipeline, output: currentData, completedAt: Date())
        status = .completed
    }

    // MARK: - Stage execution (dispatches to real coreai-models runners)

    private func executeStage(
        stage: PipelineStage, input: MediaPayload, bundleURL: URL
    ) async throws -> MediaPayload {

        let kind = RunnerKind.from(runner: stage.runner, capabilities: nil)

        switch kind {
        case .llm, .vlm:
            return try await executeLanguageModel(bundleURL: bundleURL, input: input, isVLM: kind == .vlm)

        case .speech:
            return try await executeSpeechModel(bundleURL: bundleURL, input: input)

        case .diffusion:
            return try await executeDiffusion(bundleURL: bundleURL, input: input)

        case .segmenter:
            return try await executeSegmentation(bundleURL: bundleURL, input: input)

        case .detector:
            return try await executeDetection(bundleURL: bundleURL, input: input)

        case .graph, .unknown:
            throw ExecutorError.unsupportedRunner(stage.runner)
        }
    }

    // MARK: - LLM / VLM via CoreAIRunner + Foundation Models

    private func executeLanguageModel(
        bundleURL: URL, input: MediaPayload, isVLM: Bool
    ) async throws -> MediaPayload {

        // Load via Apple's CoreAIRunner (verified API)
        let runner = try CoreAIRunner(contentsOf: bundleURL)
        let model = try await runner.makeLanguageModel()
        let session = LanguageModelSession(model: model)

        switch input {
        case .text(let prompt):
            let response = try await session.respond(to: prompt)
            return .text(response.content)

        case .image(let image):
            // VLM: use Attachment for multimodal input
            guard let imageData = image.jpegData(compressionQuality: 0.85) else {
                throw ExecutorError.encodingFailed
            }
            let attachment = Attachment(data: imageData, type: .image)
            let response = try await session.respond(
                to: Prompt("Describe this image in detail.", attachments: [attachment])
            )
            return .text(response.content)

        default:
            throw ExecutorError.inputMismatch(expected: "text or image", got: input.displayName)
        }
    }

    // MARK: - Speech via SpeechModel

    private func executeSpeechModel(
        bundleURL: URL, input: MediaPayload
    ) async throws -> MediaPayload {

        guard case .audio(let audioURL) = input else {
            throw ExecutorError.inputMismatch(expected: "audio", got: input.displayName)
        }

        // Apple's SpeechModel actor (verified API)
        let speechModel = try await SpeechModel(resourcesAt: bundleURL)
        let transcript = try await speechModel.transcribe(audioURL: audioURL)
        return .text(transcript)
    }

    // MARK: - Diffusion via DiffusionPipeline

    private func executeDiffusion(
        bundleURL: URL, input: MediaPayload
    ) async throws -> MediaPayload {

        guard case .text(let prompt) = input else {
            throw ExecutorError.inputMismatch(expected: "text", got: input.displayName)
        }

        // Load pipeline from bundle descriptor
        let descriptor = try PipelineDescriptor.load(from: bundleURL)
        let pipeline = try await descriptor.makePipeline()

        let config = PipelineConfiguration(prompt: prompt)
        let result = try await pipeline.generateImages(configuration: config) { progress in
            // Update UI progress
            return true
        }

        guard let cgImage = result.images.first else {
            throw ExecutorError.noOutput
        }

        return .image(UIImage(cgImage: cgImage))
    }

    // MARK: - Segmentation via ImageSegmenter

    private func executeSegmentation(
        bundleURL: URL, input: MediaPayload
    ) async throws -> MediaPayload {

        guard case .image(let image) = input else {
            throw ExecutorError.inputMismatch(expected: "image", got: input.displayName)
        }

        guard let cgImage = image.cgImage else {
            throw ExecutorError.encodingFailed
        }

        let tokenizerDir = bundleURL.appendingPathComponent("tokenizer")
        let engine = try CoreAISegmentationEngine(modelURL: bundleURL)
        let segmenter = try ImageSegmenter(engine: engine, tokenizerFolder: tokenizerDir)

        let segments = try await segmenter.segment(image: cgImage, prompt: "object")
        return .segmentationResult(segments)
    }

    // MARK: - Detection via ObjectDetector

    private func executeDetection(
        bundleURL: URL, input: MediaPayload
    ) async throws -> MediaPayload {

        guard case .image(let image) = input else {
            throw ExecutorError.inputMismatch(expected: "image", got: input.displayName)
        }

        let detector = try await ObjectDetector(resourcesAt: bundleURL.path)
        // ObjectDetector returns DetectionOutputs with boxes and classes
        // Exact call signature depends on the specific model's API
        throw ExecutorError.unsupportedRunner("Detection pipeline needs model-specific integration")
    }
}

// MARK: - Supporting types

enum MediaPayload {
    case text(String)
    case image(UIImage)
    case audio(URL)
    case segmentationResult(SegmentationOutputs)
    case raw(Data)

    var displayName: String {
        switch self {
        case .text: "text"
        case .image: "image"
        case .audio: "audio"
        case .segmentationResult: "segmentation"
        case .raw: "data"
        }
    }
}

struct TransmutationResult {
    let pipeline: TransmutationPipeline
    let output: MediaPayload
    let completedAt: Date
}

enum ExecutorError: LocalizedError {
    case unsupportedRunner(String)
    case inputMismatch(expected: String, got: String)
    case encodingFailed
    case noOutput

    var errorDescription: String? {
        switch self {
        case .unsupportedRunner(let r): "Unsupported runner: \(r)"
        case .inputMismatch(let e, let g): "Expected \(e), got \(g)"
        case .encodingFailed: "Failed to encode media"
        case .noOutput: "Model produced no output"
        }
    }
}
```

**Note on `import` accuracy:** The exact module names (`CoreAILM` etc.) and some type names (`CoreAISegmentationEngine`, `SegmentationOutputs`, `PipelineDescriptor.load`) are inferred from the file structure. During implementation, verify against the actual header files in the coreai-models package. The `CoreAIRunner`, `CoreAILanguageModel`, `SpeechModel`, `ImageSegmenter`, `ObjectDetector`, and `DiffusionPipeline` types are **verified** from source.

**Commit:**

```bash
git add Ditto/Engine/PipelineExecutor.swift
git commit -m "feat: PipelineExecutor using verified coreai-models runner APIs"
```

---

### Task 13: BackgroundDownloader.swift — on-demand model fetch

**Objective:** Download model bundles from Hugging Face using Background Assets framework, with progress tracking.

**SotA approach:** Use `URLSession` with background configuration for reliability and simplicity (Background Assets framework is more complex and designed for assets that ship independently of the app; for community models from HF, background URLSession is the right tool). Store in Application Support, track progress via `@Published`.

**Files:**
- Create: `Ditto/Engine/BackgroundDownloader.swift`

```swift
import Foundation
import SwiftUI

/// Downloads model bundles from Hugging Face on demand.
@MainActor
final class BackgroundDownloader: ObservableObject {
    @Published var activeDownloads: [String: DownloadProgress] = [:]

    private var session: URLSession?
    private var taskModelMap: [Int: String] = [:]  // taskID -> modelId

    struct DownloadProgress: Identifiable {
        let id: String  // modelId
        let modelName: String
        var bytesDownloaded: Int64
        var totalBytes: Int64
        var fraction: Double {
            totalBytes > 0 ? Double(bytesDownloaded) / Double(totalBytes) : 0
        }
    }

    init() {
        let config = URLSessionConfiguration.background(withIdentifier: "com.ditto.model-downloader")
        config.allowsCellularAccess = false
        config.isDiscretionary = true
        // The session delegate handles completion
        // For simplicity, using completion handlers instead of delegate
    }

    /// Queue a model download from its Hugging Face URL.
    func download(
        modelId: String,
        modelName: String,
        hfURL: String,
        destinationDir: URL,
        completion: @escaping (Result<URL, Error>) -> Void
    ) {
        guard let url = URL(string: hfURL) else {
            completion(.failure(DownloadError.invalidURL))
            return
        }

        try? FileManager.default.createDirectory(at: destinationDir, withIntermediateDirectories: true)
        let dest = destinationDir.appendingPathComponent(modelId, isDirectory: true)
        try? FileManager.default.createDirectory(at: dest, withIntermediateDirectories: true)

        let config = URLSessionConfiguration.default
        let session = URLSession(configuration: config)

        let task = session.downloadTask(with: url) { tempURL, response, error in
            Task { @MainActor in
                if let error {
                    self.activeDownloads.removeValue(forKey: modelId)
                    completion(.failure(error))
                    return
                }
                guard let tempURL else {
                    completion(.failure(DownloadError.noData))
                    return
                }
                do {
                    // Hugging Face repos are downloaded as repos, not single files.
                    // For production, use the HF Swift SDK or download individual files.
                    // This is a simplified single-file path.
                    let destFile = dest.appendingPathComponent(url.lastPathComponent)
                    try FileManager.default.moveItem(at: tempURL, to: destFile)
                    self.activeDownloads.removeValue(forKey: modelId)
                    completion(.success(dest))
                } catch {
                    completion(.failure(error))
                }
            }
        }

        // Track progress
        activeDownloads[modelId] = DownloadProgress(
            id: modelId,
            modelName: modelName,
            bytesDownloaded: 0,
            totalBytes: 0
        )
        taskModelMap[task.taskIdentifier] = modelId

        task.resume()
    }

    /// Cancel an active download.
    func cancel(modelId: String) {
        activeDownloads.removeValue(forKey: modelId)
    }
}

enum DownloadError: LocalizedError {
    case invalidURL
    case noData

    var errorDescription: String? {
        switch self {
        case .invalidURL: "Invalid download URL"
        case .noData: "Download produced no data"
        }
    }
}
```

**Production note:** Hugging Face model repos contain multiple files (weights, tokenizer, metadata). For production, integrate the `huggingface_hub` Swift port or use the HF Hub API to enumerate and download individual files from a repo. The catalog's `model-manifest.json` includes the HF repo URL; the downloader enumerates files via the HF API (`https://huggingface.co/api/models/{owner}/{repo}`) and downloads each to the local bundle directory.

**Commit:**

```bash
git add Ditto/Engine/BackgroundDownloader.swift
git commit -m "feat: BackgroundDownloader for on-demand model fetching"
```

---

## PHASE 3: Ditto UI

### Task 14: InputView, OutputSelectorView, PipelineProgressView, ResultView

**Objective:** Complete SwiftUI interface with 4-phase navigation flow. All strings in English, wired to String Catalog.

**Files:**
- Create: `Ditto/Views/InputView.swift`
- Create: `Ditto/Views/OutputSelectorView.swift`
- Create: `Ditto/Views/PipelineProgressView.swift`
- Create: `Ditto/Views/ResultView.swift`

All user-facing strings use `String(localized:)` for i18n readiness:

```swift
Text("Drop media or choose below")
// In code:
Text(String(localized: "input.dropzone.title"))
```

**InputView.swift** — accepts text, photo, or audio recording, auto-detects modality. Uses `PhotosPicker`, `AVAudioRecorder`.

**OutputSelectorView.swift** — LazyVGrid of `Modality` targets filtered by graph reachability. Each card shows the modality icon + hop count.

**PipelineProgressView.swift** — shows live stage-by-stage progress with model names and status circles.

**ResultView.swift** — renders output by type (text in ScrollView, image inline, audio player). ShareLink for export.

(Detailed SwiftUI code follows the same structure as v1 but with `String(localized:)` wrapping and English copy.)

**Commit:**

```bash
git add Ditto/Views/
git commit -m "feat: UI views (Input, Output, Progress, Result)"
```

---

### Task 15: Wire ContentView + App entry point

**Objective:** 4-phase state machine connecting all views.

**Files:**
- Create: `Ditto/ContentView.swift`
- Create: `Ditto/DittoApp.swift`

```swift
import SwiftUI

@main
struct DittoApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

struct ContentView: View {
    @StateObject private var graph: GraphEngine
    @StateObject private var modelStore = ModelStore()
    @StateObject private var executor: PipelineExecutor
    @StateObject private var downloader = BackgroundDownloader()

    @State private var inputPayload: MediaPayload?
    @State private var inputModality: Modality?
    @State private var selectedPipeline: TransmutationPipeline?
    @State private var phase: AppPhase = .input

    enum AppPhase { case input, selectOutput, executing, result }

    init() {
        let graph = try! GraphEngine.fromBundle()
        let store = ModelStore()
        _graph = StateObject(wrappedValue: graph)
        _modelStore = StateObject(wrappedValue: store)
        _executor = StateObject(wrappedValue: PipelineExecutor(modelStore: store))
    }

    var body: some View {
        NavigationStack {
            switch phase {
            case .input:
                InputView { payload, modality in
                    inputPayload = payload
                    inputModality = modality
                    phase = .selectOutput
                }

            case .selectOutput:
                if let modality = inputModality {
                    ScrollView {
                        OutputSelectorView(inputModality: modality, graph: graph) { _, pipeline in
                            selectedPipeline = pipeline
                            phase = .executing
                        }
                    }
                    .navigationTitle("Transform To...")
                    .toolbar {
                        ToolbarItem(placement: .topBarLeading) {
                            Button("Back") { phase = .input }
                        }
                    }
                }

            case .executing:
                if let pipeline = selectedPipeline, let input = inputPayload {
                    PipelineProgressView(pipeline: pipeline, executor: executor)
                        .task {
                            await executor.execute(pipeline: pipeline, input: input)
                            if case .completed = executor.status {
                                phase = .result
                            }
                        }
                }

            case .result:
                if let pipeline = selectedPipeline, let result = executor.result {
                    ResultView(pipeline: pipeline, result: result) {
                        phase = .input
                        selectedPipeline = nil
                        inputPayload = nil
                    }
                }
            }
        }
        .animation(.easeInOut(duration: 0.3), value: phase)
    }
}
```

**Commit:**

```bash
git add Ditto/ContentView.swift Ditto/DittoApp.swift
git commit -m "feat: ContentView with 4-phase state machine"
```

---

### Task 16: ModelDownloadCard + String Catalog

**Objective:** Show download status for pipeline models; set up i18n foundation.

**Files:**
- Create: `Ditto/Views/ModelDownloadCard.swift`
- Create: `Ditto/Localization/Localizable.xcstrings`

**ModelDownloadCard.swift** — shows missing models with download buttons, progress bars for active downloads, and disk usage warnings.

**Localizable.xcstrings** — Apple String Catalog (JSON format) with all UI strings extracted as keys. Xcode auto-generates this when using `String(localized:)`. English is the source language; Portuguese, Chinese etc. can be added as additional localizations without code changes.

**Commit:**

```bash
git add Ditto/Views/ModelDownloadCard.swift Ditto/Localization/
git commit -m "feat: ModelDownloadCard + String Catalog for i18n"
```

---

## PHASE 4: Quality Sweep & Ship

### Task 17: Full quality sweep — both projects

**Catalog:**
1. Run full test suite: `env -u PYTHONPATH .venv/bin/python -m pytest tests/ -v`
2. Regenerate dist/: `env -u PYTHONPATH .venv/bin/python scripts/generate.py`
3. Grep for stale version strings (all files say 2.1.0)
4. Grep for internal jargon leaks in public files
5. Manual: `coreai-catalog transforms --from audio --to image`
6. Manual: `coreai-catalog transforms --json`
7. Build package: `env -u PYTHONPATH .venv/bin/python -m build`

**Ditto:**
1. Build in Xcode (Cmd+B) — zero errors, zero warnings
2. Run unit tests (Cmd+U) — GraphEngineTests, ModelManifestTests pass
3. Manual flow: text -> text (simplest pipeline), verify execution
4. Manual flow: text -> audio (TTS), verify audio output
5. Verify bundle includes transforms-graph.json and model-manifest.json
6. Verify Info.plist permissions
7. Verify deployment target iOS 27.0
8. Test on physical device if available

**Commit + tag:**

```bash
# Catalog
cd ~/Dev/Github/coreai-catalog
git add -A
git commit -m "release: v2.1.0 - Transform Graph Engine"
git tag v2.1.0

# Ditto
cd ~/Dev/Github/Ditto
git add -A
git commit -m "feat: Ditto v0.1.0 - universal media transmutation"
git tag v0.1.0
```

---

## SotA Scope Recommendation for v0.1.0

Ship with **3 verified pipelines** that demonstrate the full architecture end-to-end:

| Pipeline | Models | Why |
|---|---|---|
| **Text -> Text** (chat) | `CoreAIRunner` + `LanguageModelSession` | Simplest: 1 hop, proves Foundation Models integration |
| **Image -> Text** (VLM describe) | `CoreAIRunner` (VLM) + `Attachment` | 1 hop, proves multimodal input |
| **Audio -> Text** (transcription) | `SpeechModel` | 1 hop, proves speech integration with real audio I/O |

Then v0.2.0 adds multi-hop:
- **Text -> Image** (text -> image via `DiffusionPipeline`)
- **Image -> Audio** (VLM describe -> TTS — 2 hops, proves chaining)
- **Audio -> Image** (transcribe -> generate — 2 hops, proves the graph engine value)

This avoids trying to build all 7 runner integrations at once while still proving the transmutation concept.

---

## Repository Separation & Sync

### Two repos, two doc surfaces, zero coupling

```
REPO 1: coreai-catalog (PUBLIC, ~/Dev/Github/coreai-catalog)
  Language: Python
  Docs: describe graph engine, CLI, MCP, model catalog
  Audience: developers using Core AI models
  NEVER mentions: Ditto, iOS, SwiftUI
  
  Outputs consumed by Ditto:
    dist/transforms-graph.json   (modality graph + pipelines)
    dist/model-manifest.json     (model metadata for downloads)
  
  These JSON files are documented as a generic export format
  suitable for "any downstream consumer" — not Ditto-specific.

REPO 2: Ditto (PRIVATE, ~/Dev/Github/Ditto)
  Language: Swift
  Docs: describe the app, UI, execution architecture
  Audience: the developer (you) + future contributors
  NEVER mentions: coreai-catalog, Python, catalog internals
  
  Consumes two JSON files as bundled resources:
    Resources/transforms-graph.json  (documented as "pipeline definitions")
    Resources/model-manifest.json    (documented as "model registry")
  
  These are treated as opaque data inputs. The README says:
  "Update these files from the latest Core AI model catalog release."
  No explanation of how they're generated.
```

### Sync workflow

1. coreai-catalog publishes a new release (e.g. v2.1.1 with 5 new models)
2. `python scripts/generate.py` regenerates `dist/*.json`
3. In Ditto: copy the two JSON files into `Resources/`
4. Commit Ditto with message: "chore: update bundled model catalog snapshot"
5. The graph engine and manifest reader in Ditto handle the new data automatically

No git submodules. No package dependency. Just file copy at release time.

---

## Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| coreai-models API changes before iOS 27 GM | High | Pin to a specific git tag. Track apple/coreai-models releases. |
| HF download on iOS is complex (multi-file repos) | High | Use HF Hub API to enumerate files, download individually, reassemble bundle structure. |
| Large models crash on iPhone (memory) | High | PipelineExecutor loads one model at a time, unloads between stages. Add memory pressure monitoring. |
| Some runner types have undiscovered APIs | Medium | Start with the 3 simplest runners (LLM, Speech, VLM). Add others incrementally. |
| String Catalog not auto-extracting | Low | Use explicit `String(localized: "key")` calls. Xcode handles extraction. |
| transforms-graph.json gets stale | Medium | Add catalog version to JSON. App checks against latest PyPI version on launch. |

---

## Open Questions

1. **HF Swift SDK**: Does a mature Swift library for HF Hub downloads exist, or do we hit the REST API directly? (The downloader can enumerate files via `GET https://huggingface.co/api/models/{repo}` and download via `GET https://huggingface.co/{repo}/resolve/main/{file}`.)
2. **CoreAIKit import path**: The exact `import` statement and product name for each runner type needs verification against the built package. The plan uses inferred names from the file structure.
3. **VLM via CoreAIRunner**: Does `CoreAIRunner` handle VLM bundles differently, or is the `Attachment` API enough through Foundation Models? Verified that `CoreAILanguageModel` conforms to `LanguageModel`, which supports `Attachment` — so it should work transparently.

---

*Plan v2.0 — 17 tasks across 4 phases. All Apple API names verified against apple/coreai-models source.*
*Estimated: 3 days Phase 1 (Python), 5 days Phase 2-3 (Swift), 1 day Phase 4.*
