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

from .catalog import (
    Catalog,
    deployability_facets,
    entry_completeness,
    lifecycle_of,
)
from .formatters import (
    extract_device_list,
    get_catalog_version,
    reshape_benchmark,
)

#: Schema version included in every export so consumers can detect format changes.
EXPORT_SCHEMA_VERSION = "1.0"


def derive_bundle_kind(model: dict[str, Any]) -> str:
    """Derive the task-level bundle kind from a model's capabilities.

    This is the single derivation rule shared by the catalog authoring and
    the export-time validator (redteam C5: the old runner-based heuristic
    mis-bucketed the image-input OCR model as ``llm``). First matching rule
    wins. The vocabulary is the authored ``bundle_kind`` enum in
    schema/model.schema.json — a catalog task taxonomy, distinct from the
    runtime's 4-value BundleKind enum (apple/coreai-models
    swift/Sources/CoreAIShared/Bundle/BundleKind.swift:12-17).

    Raises ValueError when no rule matches, so a new capability cannot
    silently fall into a wrong bucket — extend the mapping instead.
    """
    caps = set(model.get("capabilities", []))
    inputs = set(model.get("modalities", {}).get("input", []))

    rules: list[tuple[set[str], str]] = [
        ({"document-ocr"}, "ocr"),
        ({"reward-modeling"}, "reward-model"),
        ({"vision-language-action", "robotics"}, "action"),
        ({"vision-language", "gui-grounding"}, "vlm"),
        ({"audio-understanding"}, "audio-lm"),
        ({"embedding", "image-text-similarity", "visual-document-retrieval"},
         "embedding"),
        ({"reranking"}, "reranker"),
        ({"token-classification"}, "token-classification"),
        ({"image-feature-extraction"}, "image-feature-extraction"),
        ({"object-detection"}, "object-detection"),
        ({"instance-segmentation", "promptable-segmentation"}, "segmentation"),
        ({"monocular-depth"}, "depth"),
        ({"image-generation"}, "image-generation"),
        ({"super-resolution"}, "super-resolution"),
        ({"text-to-speech"}, "tts"),
        ({"speech-to-text", "transcription"}, "asr"),
        ({"speaker-diarization", "voice-activity-detection"}, "diarization"),
        ({"text-to-audio", "music-generation"}, "audio-generation"),
        ({"text-to-video", "video-classification"}, "video"),
        ({"image-to-3d"}, "3d"),
    ]
    for capset, kind in rules:
        if caps & capset:
            return kind

    text_caps = {
        "chat", "text-generation", "instruction-following", "reasoning",
        "agentic", "speculative-decoding", "diffusion-lm", "hybrid-llm",
        "moe", "mla",
    }
    if caps & text_caps:
        # A language model with image input is a VLM, never a bare llm (C5).
        return "vlm" if "image" in inputs else "llm"

    raise ValueError(
        f"derive_bundle_kind: no rule matches capabilities {sorted(caps)} "
        f"for model '{model.get('id', '<unknown>')}'. Extend the mapping in "
        "coreai_catalog/exports.py before assigning a bundle_kind."
    )


def validate_bundle_kind(model: dict[str, Any]) -> str:
    """Return the model's effective bundle kind, failing on disagreement.

    The authored ``bundle_kind`` (catalog.yaml) is the contract; the
    capability derivation is demoted to a validator (redteam C5). A model
    with an authored kind that disagrees with its capabilities fails the
    export — and with it ``scripts/generate.py`` — instead of silently
    publishing a wrong integration hint.
    """
    derived = derive_bundle_kind(model)
    authored = model.get("bundle_kind")
    if authored is None:
        return derived
    if authored != derived:
        raise ValueError(
            f"bundle_kind disagreement for model '{model.get('id', '<unknown>')}': "
            f"authored '{authored}' but capabilities {sorted(model.get('capabilities', []))} "
            f"derive '{derived}'. Fix bundle_kind in catalog.yaml or extend "
            "derive_bundle_kind in coreai_catalog/exports.py."
        )
    return authored


def read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text()) or {}


def read_benchmarks_jsonl(catalog_root: Path) -> dict[str, Any]:
    """Read benchmarks.jsonl into the legacy top-level export shape.

    benchmarks.jsonl is the single benchmark source of truth (the YAML
    store is retired). Returns ``{"metadata": {...}, "benchmarks": [...]}``
    so dist/benchmarks.json keeps its historical top-level keys.
    """
    path = Path(catalog_root) / "benchmarks.jsonl"
    benchmarks: list[dict] = []
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            benchmarks.append(json.loads(line))
    return {
        "metadata": {
            "source": "benchmarks.jsonl",
            "count": len(benchmarks),
        },
        "benchmarks": benchmarks,
    }


def _get_catalog_version(catalog_root: Path) -> str:
    """Extract the catalog version from catalog.yaml metadata."""
    return get_catalog_version(catalog_root)


def export_json(catalog_root: Path, dist: Path | None = None) -> None:
    """Export all YAML files to dist/*.json."""
    dist = dist or catalog_root / "dist"
    dist.mkdir(exist_ok=True)

    inputs = {
        "catalog": catalog_root / "catalog.yaml",
        "artifacts": catalog_root / "artifacts.yaml",
        "sources": catalog_root / "sources.yaml",
        "upstreams": catalog_root / "upstreams.yaml",
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

    # Benchmarks come from benchmarks.jsonl (single source of truth)
    bench_data = read_benchmarks_jsonl(catalog_root)
    bench_export = dict(bench_data)
    bench_export["export_schema_version"] = EXPORT_SCHEMA_VERSION
    bench_export["export_catalog_version"] = catalog_version
    (dist / "benchmarks.json").write_text(
        json.dumps(bench_export, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )

    # Bundle
    bundle = {name: read_yaml(path) for name, path in inputs.items() if path.exists()}
    bundle["benchmarks"] = bench_data
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
        bench_by_model.setdefault(mid, []).append(reshape_benchmark(b))

    entries = []
    scores = []
    for m in cat.models:
        art = cat.get_artifact(m["id"])
        hf = art.get("huggingface", {}) if art else {}
        gh = art.get("github", {}) if art else {}
        off = art.get("officiality", {}) if art else {}

        ds = m.get("device_support", {})
        devices = extract_device_list(ds)

        rt = m.get("runtime", {})
        size = m.get("size", {})
        # DEPRECATED headline: readiness_score is a curation/deployability
        # composite that is blind to model quality. Prefer the decomposed
        # deployability/lifecycle/entry_completeness facets attached below.
        score = cat.readiness_score(m)
        has_bench = bool(bench_by_model.get(m["id"]))

        entry = {
            "id": m["id"],
            "name": m["name"],
            "family": m["family"],
            "source_group": m.get("source_group"),
            "bundle_kind": validate_bundle_kind(m),
            "min_os": m.get("min_os"),
            "upstream_repo": m.get("upstream_repo"),
            "io_contract": m.get("io_contract"),
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
            "engine_variant": rt.get("engine_variant"),
            "evaluation": m.get("evaluation"),
            "framework_contract": m.get("framework_contract"),
            "license": m.get("license", {}).get("name"),
            "commercial_use": m.get("license", {}).get("commercial_use"),
            "status": m.get("status"),
            "maturity": m.get("maturity"),
            "confidence": m.get("confidence"),
            "readiness_score": score,
            "deployability": deployability_facets(m, has_bench),
            "lifecycle": lifecycle_of(m),
            "entry_completeness": entry_completeness(m, has_bench),
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
    parameters, precision, bundle_kind (authored in catalog.yaml and
    validated against the capability derivation — see
    ``validate_bundle_kind``), min_os, upstream_repo and io_contract
    (when authored).

    Writes:
      dist/model-manifest.json

    Raises ValueError when an authored bundle_kind disagrees with the
    capability derivation (redteam C5) — generate.py fails instead of
    exporting a wrong integration hint.
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
        bundle_kind = validate_bundle_kind(m)

        entry = {
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
            "min_os": m.get("min_os"),
            "upstream_repo": m.get("upstream_repo"),
            "io_contract": m.get("io_contract"),
        }
        entries.append(entry)

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


def export_lerobot_coreai(catalog_root: Path, dist: Path | None = None) -> dict:
    """Export a LeRobot-specific compatibility index for lerobot-coreai.

    Filters to models with bundle_kind=action and family=LeRobot, emitting a
    compact policy list with the fields lerobot-coreai needs for inspect/doctor.

    Writes:
      dist/lerobot-coreai.json

    Shape (spec §18.3)::

        {
          "schema_version": "lerobot-coreai.catalog.v0",
          "generated_at": "...",
          "policies": [
            {
              "repo_id": "kevinqz/EVO1-SO100-CoreAI",
              "catalog_model_id": "evo1-so100",
              "policy_type": "evo1",
              "robot_type": "so100",
              "runtime": "coreai",
              "status": "action_parity_passed",
              "default_mode": "dry_run",
              ...
            }
          ]
        }
    """
    dist = dist or catalog_root / "dist"
    dist.mkdir(exist_ok=True)
    cat = Catalog(catalog_root)

    policies: list[dict] = []
    for m in cat.models:
        bundle_kind = validate_bundle_kind(m)
        if bundle_kind != "action":
            continue
        fc = m.get("framework_contract") or {}
        if fc.get("framework") != "lerobot" and m.get("family") != "LeRobot":
            continue

        eval_block = m.get("evaluation", {})
        eval_status = eval_block.get("status", "unknown")
        policy_entry = {
            "repo_id": m["id"],
            "catalog_model_id": m["id"],
            "policy_type": fc.get("policy_type", _infer_policy_type(m["id"])),
            "robot_type": fc.get("robot_type", _infer_robot_type(m["id"])),
            "runtime": "coreai",
            "status": f"action_parity_{eval_status}" if eval_status != "unknown" else "indexed",
            "default_mode": "dry_run",
            "framework_contract": fc if fc else None,
            "evaluation": eval_block if eval_block else None,
        }
        policies.append(policy_entry)

    catalog_version = _get_catalog_version(catalog_root)
    output = {
        "schema_version": "lerobot-coreai.catalog.v0",
        "generated_at": _utc_now_iso(),
        "export_catalog_version": catalog_version,
        "policy_count": len(policies),
        "policies": policies,
    }

    # Deterministic timestamp: preserve the existing `generated_at` when nothing
    # else changed, so `generate.py` is idempotent and CI's
    # `git diff --exit-code dist/` guard doesn't fail on a wall-clock-only churn
    # (the non-deterministic timestamp made that guard fail on every PR).
    out_path = dist / "lerobot-coreai.json"
    if out_path.is_file():
        try:
            prev = json.loads(out_path.read_text())
            if prev.get("generated_at") and \
                    {**prev, "generated_at": None} == {**output, "generated_at": None}:
                output["generated_at"] = prev["generated_at"]
        except (ValueError, OSError):
            pass
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    return output


def _infer_policy_type(model_id: str) -> str:
    ml = model_id.lower()
    for t in ("pi0fast", "pi05", "pi0", "smolvla", "vqbet", "diffusion", "evo1", "act", "fastwam", "bitvla"):
        if t in ml:
            return t
    return "unknown"


def _infer_robot_type(model_id: str) -> str:
    ml = model_id.lower()
    for r in ("so100", "so101", "aloha", "libero"):
        if r in ml:
            return r
    return "unknown"


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def export_leaderboard(catalog_root: Path, dist: Path | None = None) -> dict:
    """Export a ranked leaderboard joining readiness scores with best benchmarks.

    Writes:
      dist/leaderboard.json

    Each entry: id, name, capabilities, parameters, readiness_score,
    benchmark_count, best_metrics (dict of metric → {value, device, unit}).
    """
    dist = dist or catalog_root / "dist"
    dist.mkdir(exist_ok=True)
    cat = Catalog(catalog_root)

    # Group benchmarks by model
    bench_by_model: dict[str, list[dict]] = {}
    for b in cat.benchmarks:
        mid = b.get("model_id", "")
        bench_by_model.setdefault(mid, []).append(reshape_benchmark(b))

    entries = []
    for m in cat.models:
        mid = m["id"]
        score = cat.readiness_score(m)
        model_benchmarks = bench_by_model.get(mid, [])

        # Extract best metric per metric type
        best_metrics: dict[str, dict] = {}
        for b in model_benchmarks:
            metric = b.get("metric", "")
            if not metric:
                continue
            val = b.get("value")
            if val is None:
                continue
            existing = best_metrics.get(metric)
            # For latency/RTF lower is better; for throughput/accuracy higher is better.
            # Simple heuristic: keep the first value per metric (benchmarks are append-only,
            # latest = most relevant). A more sophisticated comparison would need metric
            # direction metadata.
            if existing is None:
                best_metrics[metric] = {
                    "value": val,
                    "device": b.get("device", "unknown"),
                    "unit": b.get("unit", ""),
                }

        entries.append({
            "id": mid,
            "name": m["name"],
            "capabilities": m.get("capabilities", []),
            "parameters": m.get("size", {}).get("parameters", "unknown"),
            "readiness_score": score,
            "lifecycle": lifecycle_of(m),
            "entry_completeness": entry_completeness(m, bool(model_benchmarks)),
            "benchmark_count": len(model_benchmarks),
            "best_metrics": best_metrics,
        })

    # Sort by readiness score descending, then by id for stability
    entries.sort(key=lambda e: (-e["readiness_score"], e["id"]))

    catalog_version = _get_catalog_version(catalog_root)
    output = {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "export_catalog_version": catalog_version,
        "description": "Ranked by the DEPRECATED readiness_score (a curation/deployability composite, NOT model quality). Prefer per-entry deployability/lifecycle/entry_completeness facets plus benchmark VALUES. Each entry includes best-known benchmarks per metric.",
        "total_models": len(entries),
        "leaderboard": entries,
    }

    (dist / "leaderboard.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    )
    return output


def export_aliases(catalog_root: Path, dist: Path | None = None) -> dict:
    """Export alias mappings resolving naming mismatches across ecosystems.

    Maps catalog model IDs to lists of alternative names found in:
    - Hugging Face repo names (from artifact provenance)
    - Source paths (URL-derived)
    - Common formatting variants (dots vs dashes, version normalisation)

    Writes:
      dist/aliases.json
    """
    dist = dist or catalog_root / "dist"
    dist.mkdir(exist_ok=True)
    cat = Catalog(catalog_root)

    aliases: dict[str, list[str]] = {}

    for m in cat.models:
        mid = m["id"]
        alts: set[str] = set()

        # From HuggingFace repo name
        art = cat.get_artifact(mid)
        if art:
            hf = art.get("huggingface", {})
            repo = hf.get("repo", "")
            if repo:
                alts.add(repo)
                # Normalised variant: lowercase, dots→dashes
                normalised = repo.lower().replace(".", "-")
                if normalised != repo:
                    alts.add(normalised)

        # From source path URL
        source_path = m.get("source_path", "")
        if source_path and "/" in source_path:
            # Last path segment often contains model name variant
            last_segment = source_path.rstrip("/").split("/")[-1]
            if last_segment and last_segment != mid:
                alts.add(last_segment)

        # Generate common format variants from the model ID itself
        # e.g. "qwen3-5-0-8b" → "qwen3.5-0.8b", "qwen3.5-0-8b"
        parts = mid.split("-")
        # Try dot-joining version-like segments
        dotted = mid.replace("-", ".", 2)  # qwen3.5.0-8b style
        if dotted != mid:
            alts.add(dotted)

        if alts:
            aliases[mid] = sorted(alts)

    catalog_version = _get_catalog_version(catalog_root)
    output = {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "export_catalog_version": catalog_version,
        "description": "Alias mappings resolving catalog IDs to Zoo card names, CoreAIKit strings, and HF repo names.",
        "total_models": len(aliases),
        "aliases": aliases,
    }

    (dist / "aliases.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    )
    return output
