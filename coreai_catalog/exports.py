"""
Core AI Catalog exports — single source for JSON/JSONL/score generation.

All export logic lives here. CLI commands, CI scripts, and MCP server
all import from this module. No duplication.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .catalog import Catalog

#: Schema version included in every export so consumers can detect format changes.
EXPORT_SCHEMA_VERSION = "1.0"


def read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text()) or {}


def _get_catalog_version(catalog_root: Path) -> str:
    """Extract the catalog version from catalog.yaml metadata."""
    cat_path = catalog_root / "catalog.yaml"
    if cat_path.exists():
        data = read_yaml(cat_path)
        return data.get("metadata", {}).get("version", "unknown")
    return "unknown"


def export_json(catalog_root: Path, dist: Path | None = None) -> None:
    """Export all YAML files to dist/*.json."""
    dist = dist or catalog_root / "dist"
    dist.mkdir(exist_ok=True)

    inputs = {
        "catalog": catalog_root / "catalog.yaml",
        "artifacts": catalog_root / "artifacts.yaml",
        "sources": catalog_root / "sources.yaml",
        "upstreams": catalog_root / "upstreams.yaml",
        "benchmarks": catalog_root / "benchmarks.yaml",
        "terms": catalog_root / "terms.yaml",
    }

    catalog_version = _get_catalog_version(catalog_root)

    for name, path in inputs.items():
        if path.exists():
            data = read_yaml(path)
            data["export_schema_version"] = EXPORT_SCHEMA_VERSION
            data["export_catalog_version"] = catalog_version
            (dist / f"{name}.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
            )

    # Bundle
    bundle = {name: read_yaml(path) for name, path in inputs.items() if path.exists()}
    bundle["export_schema_version"] = EXPORT_SCHEMA_VERSION
    bundle["export_catalog_version"] = catalog_version
    (dist / "coreai-catalog.json").write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )


def export_search_index(catalog_root: Path, dist: Path | None = None) -> int:
    """
    Generate flattened, denormalized model entries joining catalog +
    artifacts + benchmarks + readiness score.

    Writes:
      dist/search-index.json — full array
      dist/models.jsonl — one model per line
      dist/readiness-scores.json — scores with breakdown

    Returns number of entries.
    """
    dist = dist or catalog_root / "dist"
    dist.mkdir(exist_ok=True)
    cat = Catalog(catalog_root)

    # Benchmark lookup
    bench_by_model: dict[str, list[dict]] = {}
    for b in cat.benchmarks:
        mid = b.get("model_id", "")
        bench_by_model.setdefault(mid, []).append({
            "metric": b.get("metric"),
            "unit": b.get("unit"),
            "value": b.get("value"),
            "device": b.get("device"),
            "compute_unit": b.get("compute_unit"),
            "environment": b.get("environment"),
            "observed": b.get("observed"),
            "confidence": b.get("confidence"),
            "precision": b.get("precision"),
            "notes": b.get("notes"),
        })

    entries = []
    scores = []
    for m in cat.models:
        art = cat.get_artifact(m["id"])
        hf = art.get("huggingface", {}) if art else {}
        gh = art.get("github", {}) if art else {}
        off = art.get("officiality", {}) if art else {}

        ds = m.get("device_support", {})
        devices = []
        if ds.get("iphone") is True:
            devices.append("iphone")
        if ds.get("ipad") is True:
            devices.append("ipad")
        if ds.get("mac") is True:
            devices.append("mac")

        rt = m.get("runtime", {})
        size = m.get("size", {})
        score = cat.readiness_score(m)

        entry = {
            "id": m["id"],
            "name": m["name"],
            "family": m["family"],
            "source_group": m.get("source_group"),
            "capabilities": m.get("capabilities", []),
            "input_modalities": m.get("modalities", {}).get("input", []),
            "output_modalities": m.get("modalities", {}).get("output", []),
            "devices": devices,
            "parameters": size.get("parameters"),
            "precision": size.get("precision"),
            "quantization": size.get("quantization"),
            "artifact_size": size.get("artifact_size"),
            "runtime": rt.get("runtime_name"),
            "runner": rt.get("runner"),
            "stock_runtime": rt.get("stock_runtime"),
            "custom_kernel": rt.get("custom_kernel"),
            "patch_required": rt.get("patch_required"),
            "aot_required": rt.get("aot_required"),
            "license": m.get("license", {}).get("name"),
            "commercial_use": m.get("license", {}).get("commercial_use"),
            "status": m.get("status"),
            "maturity": m.get("maturity"),
            "confidence": m.get("confidence"),
            "readiness_score": score,
            "artifact": {
                "format": m.get("artifact", {}).get("format"),
                "availability": m.get("artifact", {}).get("availability"),
                "huggingface_url": hf.get("url"),
                "huggingface_repo": f"{hf.get('owner', '')}/{hf.get('repo', '')}" if hf.get("owner") else None,
                "github_source": f"{gh.get('owner', '')}/{gh.get('repo', '')}" if gh.get("owner") else None,
                "apple_export_recipe": off.get("apple_export_recipe"),
                "apple_hosted_artifact": off.get("apple_hosted_artifact"),
                "community_packaged": off.get("community_packaged"),
            },
            "benchmarks": bench_by_model.get(m["id"], []),
            "last_verified": m.get("last_verified"),
            "notes": m.get("notes"),
        }
        entries.append(entry)
        scores.append({
            "id": m["id"],
            "name": m["name"],
            "score": score,
        })

    # search-index.json
    catalog_version = _get_catalog_version(catalog_root)
    (dist / "search-index.json").write_text(
        json.dumps({
            "count": len(entries),
            "export_schema_version": EXPORT_SCHEMA_VERSION,
            "export_catalog_version": catalog_version,
            "models": entries,
        }, indent=2, ensure_ascii=False) + "\n"
    )

    # models.jsonl
    with (dist / "models.jsonl").open("w") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # readiness-scores.json
    scores.sort(key=lambda s: (-s["score"], s["id"]))
    (dist / "readiness-scores.json").write_text(
        json.dumps({
            "readiness_scores": scores,
            "export_schema_version": EXPORT_SCHEMA_VERSION,
            "export_catalog_version": catalog_version,
        }, indent=2, ensure_ascii=False) + "\n"
    )

    return len(entries)


def export_transform_graph(catalog_root: Path, dist: Path | None = None) -> dict:
    """Export the transform graph as JSON for programmatic consumption.

    Writes:
      dist/transforms-graph.json

    Structure:
    {
      "input_modalities": [...],
      "output_modalities": [...],
      "direct_edges": [
        {"input": "text", "output": "audio", "model_ids": ["kokoro-82m", ...]},
        ...
      ],
      "reachability_matrix": {
        "text": ["audio", "image", "text", "vector", ...],
        ...
      },
      "pipelines": {
        "text\u2192audio": { "stages": [...], "hop_count": 1 },
        "audio\u2192image": { "stages": [...], "hop_count": 2 },
        ...
      }
    }
    """
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

    Writes:
      dist/model-manifest.json
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
            bundle_kind = "vlm" if "vision-language" in caps else "llm"
        elif runner == "CoreAIDiffusionPipeline":
            bundle_kind = "diffusion"
        elif runner == "CoreAIImageSegmenter":
            bundle_kind = "segmenter"
        elif runner == "CoreAITranscribe":
            bundle_kind = "speech"
        elif runner == "CoreAIVideoPipeline":
            bundle_kind = "video"
        elif runner == "CoreAIKit-GraphModel":
            bundle_kind = "detector" if "object-detection" in caps or "instance-segmentation" in caps else "graph"
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
