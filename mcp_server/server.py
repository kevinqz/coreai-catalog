#!/usr/bin/env python3
"""
Core AI Catalog MCP Server — exposes catalog tools to AI agents.

Provides 11 tools for model discovery, comparison, recommendation,
license triage, and terminology explanation via the Model Context Protocol.

Usage (stdio transport — standard for Claude Desktop, Cursor, etc.):
  python mcp_server/server.py

Or after pip install:
  coreai-catalog-mcp

Configure in Claude Desktop / Cursor / MCP client:
  {
    "mcpServers": {
      "coreai-catalog": {
        "command": "python",
        "args": ["mcp_server/server.py"]
      }
    }
  }
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure we can find the coreai_catalog package and catalog YAML
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mcp.server.fastmcp import FastMCP

from coreai_catalog.catalog import Catalog, resolve_task

# Initialize catalog once at startup
catalog = Catalog(_ROOT)

# Create MCP server
mcp = FastMCP(
    "coreai-catalog",
    instructions=(
        "Core AI Catalog — a source-grounded registry of 78+ Apple Core AI models. "
        "Use these tools to discover, compare, and recommend models for on-device "
        "Apple Silicon deployment. All data is grounded in upstream sources "
        "(Hugging Face, GitHub, Apple documentation). Never fabricate model "
        "specifications — if a tool returns 'unknown', report it as unknown."
    ),
)


# ── Tool 1: search_models ──

@mcp.tool()
def search_models(
    capability: str | None = None,
    device: str | None = None,
    license: str | None = None,
    family: str | None = None,
    source_group: str | None = None,
    modality: str | None = None,
    limit: int = 20,
) -> str:
    """Search Apple Core AI models by criteria.

    Args:
        capability: Filter by capability (e.g. 'chat', 'vision-language',
            'speech-to-text', 'object-detection', 'text-to-speech', 'embedding').
        device: Filter by device support ('iphone', 'ipad', 'mac').
        license: Filter by commercial use status ('likely' or 'check_license').
        family: Filter by model family (e.g. 'Qwen', 'Gemma', 'Whisper').
        source_group: Filter by origin ('zoo', 'official', 'external').
        modality: Filter by input/output modality ('text', 'image', 'audio').
        limit: Maximum results to return (default 20).

    Returns:
        JSON array of matching models with id, name, capabilities, devices,
        license, readiness score, and artifact URL.
    """
    results = catalog.search(
        capability=capability,
        device=device,
        license_type=license,
        family=family,
        source_group=source_group,
        modality=modality,
    )
    # Clamp limit to valid range
    limit = max(0, min(limit, 10000))
    total_matches = len(results)
    truncated = total_matches > limit if limit > 0 else False
    output = []
    for m in results[:limit] if limit > 0 else []:
        ds = m.get("device_support", {})
        devices = []
        if ds.get("iphone") is True:
            devices.append("iphone")
        if ds.get("ipad") is True:
            devices.append("ipad")
        if ds.get("mac") is True:
            devices.append("mac")
        # Surface unknown device support explicitly
        devices_unknown = []
        for dev in ("iphone", "ipad", "mac"):
            if ds.get(dev) not in (True, False):
                devices_unknown.append(dev)
        art = catalog.get_artifact(m["id"])
        hf_url = ""
        if art:
            hf_url = art.get("huggingface", {}).get("url", "")
        output.append({
            "id": m["id"],
            "name": m["name"],
            "family": m["family"],
            "capabilities": m.get("capabilities", []),
            "devices": devices,
            "devices_unknown": devices_unknown or None,
            "parameters": m.get("size", {}).get("parameters"),
            "license": m.get("license", {}).get("name"),
            "commercial_use": m.get("license", {}).get("commercial_use"),
            "readiness_score": catalog.readiness_score(m),
            "has_benchmark": bool(catalog.get_benchmarks(m["id"])),
            "artifact_url": hf_url,
            "source_group": m.get("source_group"),
        })
    return json.dumps({
        "count": len(output),
        "total_matches": total_matches,
        "truncated": truncated,
        "models": output,
    }, indent=2)


# ── Tool 2: get_model ──

@mcp.tool()
def get_model(model_id: str) -> str:
    """Get full details for a specific Core AI model by ID.

    Args:
        model_id: The model identifier (e.g. 'qwen3-vl-2b', 'unlimited-ocr').

    Returns:
        JSON object with all model metadata: capabilities, modalities, size,
        runtime flags, device support, license, provenance (Hugging Face +
        GitHub sources), officiality status, and benchmark records.
    """
    model = catalog.get_model(model_id)
    if not model:
        return json.dumps({"error": f"Model '{model_id}' not found"})

    art = catalog.get_artifact(model["id"])
    benchmarks = catalog.get_benchmarks(model["id"])

    result = {
        "id": model["id"],
        "name": model["name"],
        "family": model.get("family"),
        "source_group": model.get("source_group"),
        "capabilities": model.get("capabilities", []),
        "modalities": model.get("modalities", {}),
        "size": model.get("size", {}),
        "runtime": model.get("runtime", {}),
        "device_support": model.get("device_support", {}),
        "license": model.get("license", {}),
        "status": model.get("status"),
        "maturity": model.get("maturity"),
        "confidence": model.get("confidence"),
        "readiness_score": catalog.readiness_score(model),
        "artifact": model.get("artifact", {}),
        "provenance": {},
        "benchmarks": [],
        "notes": model.get("notes"),
        "last_verified": model.get("last_verified"),
    }

    if art:
        result["provenance"] = {
            "github": art.get("github", {}),
            "huggingface": art.get("huggingface", {}),
            "officiality": art.get("officiality", {}),
        }

    for b in benchmarks:
        result["benchmarks"].append({
            "metric": b.get("metric"),
            "unit": b.get("unit"),
            "value": b.get("value"),
            "device": b.get("device"),
            "compute_unit": b.get("compute_unit"),
            "environment": b.get("environment"),
            "observed": b.get("observed"),
            "confidence": b.get("confidence"),
        })

    return json.dumps(result, indent=2)


# ── Tool 3: compare_models ──

@mcp.tool()
def compare_models(model_ids: list[str]) -> str:
    """Compare two or more Core AI models side-by-side.

    Args:
        model_ids: List of 2+ model IDs to compare (e.g. ['qwen3-vl-2b', 'gemma-4-e2b-vision']).

    Returns:
        JSON array with each model's score, capabilities, devices, parameters,
        license, runner, benchmark count, and source.
    """
    if not model_ids or len(model_ids) < 2:
        return json.dumps({"error": "Provide at least 2 model IDs to compare"})

    # Deduplicate while preserving order
    seen = set()
    unique_ids = []
    for mid in model_ids:
        if mid not in seen:
            seen.add(mid)
            unique_ids.append(mid)

    results = []
    for mid in unique_ids:
        m = catalog.get_model(mid)
        if not m:
            results.append({"id": mid, "error": "not found"})
            continue
        results.append({
            "id": m["id"],
            "name": m["name"],
            "score": catalog.readiness_score(m),
            "capabilities": m.get("capabilities", []),
            "parameters": m.get("size", {}).get("parameters"),
            "precision": m.get("size", {}).get("precision"),
            "devices": m.get("device_support", {}),
            "license": m.get("license", {}).get("name"),
            "commercial_use": m.get("license", {}).get("commercial_use"),
            "runner": m.get("runtime", {}).get("runner"),
            "stock_runtime": m.get("runtime", {}).get("stock_runtime"),
            "benchmark_count": len(catalog.get_benchmarks(m["id"])),
            "source_group": m.get("source_group"),
        })
    return json.dumps({"comparison": results}, indent=2)


# ── Tool 4: recommend_model ──

@mcp.tool()
def recommend_model(task: str, device: str | None = None, limit: int = 5) -> str:
    """Recommend Core AI models for a given task.

    Args:
        task: Natural language task description (e.g. 'robot vision',
            'private on-device OCR', 'voice assistant', 'on-device RAG').
        device: Target device constraint ('iphone' or 'mac').
        limit: Maximum recommendations (default 5).

    Returns:
        JSON with resolved capabilities and ranked model recommendations
        with scores, devices, licenses, and notes.
    """
    capabilities = resolve_task(task)
    recommendations = catalog.recommend_models(
        capabilities=capabilities,
        device=device,
        limit=limit,
        task=task,
    )

    return json.dumps({
        "task": task,
        "resolved_capabilities": capabilities,
        "device": device,
        "recommendations": recommendations,
    }, indent=2)


# ── Tool 5: check_license ──

@mcp.tool()
def check_license(model_id: str) -> str:
    """Check license and commercial use status for a model.

    Args:
        model_id: Model identifier.

    Returns:
        JSON with license name, commercial_use triage label, original model
        source, and whether it is an Apple official recipe or community port.
    """
    model = catalog.get_model(model_id)
    if not model:
        return json.dumps({"error": f"Model '{model_id}' not found"})

    art = catalog.get_artifact(model["id"])
    result = {
        "id": model["id"],
        "name": model["name"],
        "license": model.get("license", {}).get("name"),
        "commercial_use": model.get("license", {}).get("commercial_use"),
        "officiality": art.get("officiality", {}) if art else {},
        "source_group": model.get("source_group"),
        "warning": None,
    }

    cu = model.get("license", {}).get("commercial_use")
    if cu == "check_license":
        result["warning"] = (
            "This model's license requires review before commercial use. "
            "Check the upstream model, code, and artifact licenses."
        )

    return json.dumps(result, indent=2)


# ── Tool 6: get_benchmarks ──

@mcp.tool()
def get_benchmarks(model_id: str) -> str:
    """Get all benchmark records for a model.

    Args:
        model_id: Model identifier.

    Returns:
        JSON array of benchmark measurements including metric, value, unit,
        device, compute unit (GPU/ANE/CPU), environment, and observation date.
    """
    model = catalog.get_model(model_id)
    if not model:
        return json.dumps({"error": f"Model '{model_id}' not found"})

    benches = catalog.get_benchmarks(model["id"])
    output = []
    for b in benches:
        output.append({
            "metric": b.get("metric"),
            "unit": b.get("unit"),
            "value": b.get("value"),
            "device": b.get("device"),
            "compute_unit": b.get("compute_unit"),
            "precision": b.get("precision"),
            "environment": b.get("environment"),
            "observed": b.get("observed"),
            "confidence": b.get("confidence"),
            "notes": b.get("notes"),
        })
    return json.dumps({
        "model_id": model_id,
        "count": len(output),
        "benchmarks": output,
    }, indent=2)


# ── Tool 7: get_artifact ──

@mcp.tool()
def get_artifact(model_id: str) -> str:
    """Get artifact provenance and download information for a model.

    Args:
        model_id: Model identifier.

    Returns:
        JSON with Hugging Face repo URL, GitHub conversion source,
        artifact format/availability, and officiality status (Apple recipe
        vs community packaged).
    """
    model = catalog.get_model(model_id)
    if not model:
        return json.dumps({"error": f"Model '{model_id}' not found"})

    art = catalog.get_artifact(model["id"])
    if not art:
        return json.dumps({"error": f"No artifact record for '{model_id}'"})

    return json.dumps({
        "id": art.get("id"),
        "group": art.get("group"),
        "github": art.get("github", {}),
        "huggingface": art.get("huggingface", {}),
        "officiality": art.get("officiality", {}),
        "artifact_format": model.get("artifact", {}).get("format"),
        "artifact_availability": model.get("artifact", {}).get("availability"),
    }, indent=2)


# ── Tool 8: explain_term ──

@mcp.tool()
def explain_term(term: str) -> str:
    """Explain an Apple AI/Core AI term using verified official sources.

    Args:
        term: Term to look up (e.g. 'Core AI', 'Foundation Models',
            'AOT', 'aimodel', 'Core ML', 'MLX', 'App Intents').

    Returns:
        JSON with the term definition, Apple ecosystem layer, official source
        URL, and relations to other terms.
    """
    if not term or not term.strip():
        return json.dumps({"error": "Term parameter is required"})
    lower = term.lower().strip()
    for t in catalog.terms:
        if t["id"].lower() == lower or t.get("label", "").lower() == lower:
            return json.dumps({
                "id": t["id"],
                "label": t.get("label"),
                "definition": t.get("definition"),
                "apple_layer": t.get("apple_layer"),
                "official_source": t.get("official_source"),
                "verification": t.get("verification"),
                "relations": t.get("relations", []),
            }, indent=2)

    # Fuzzy match
    matches = []
    for t in catalog.terms:
        label = t.get("label", "").lower()
        tid = t["id"].lower()
        if lower in label or lower in tid or label in lower:
            matches.append({
                "id": t["id"],
                "label": t.get("label"),
                "definition": t.get("definition", "")[:150],
            })
    if matches:
        return json.dumps({
            "exact_match": False,
            "suggestions": matches[:5],
        }, indent=2)

    return json.dumps({"error": f"Term '{term}' not found in Apple AI terminology"})


# ── Tool 9: get_capabilities ──

@mcp.tool()
def get_capabilities() -> str:
    """List all model capabilities in the catalog with model counts.

    Returns:
        JSON array of capabilities sorted by frequency, each with the
        number of models that have it.
    """
    from collections import Counter
    cap_counts: Counter = Counter()
    for m in catalog.models:
        for c in m.get("capabilities", []):
            cap_counts[c] += 1
    output = [
        {"capability": cap, "model_count": count}
        for cap, count in cap_counts.most_common()
    ]
    return json.dumps({"count": len(output), "capabilities": output}, indent=2)


# ── Tool 10: get_tasks ──

@mcp.tool()
def get_tasks() -> str:
    """List valid task keywords accepted by recommend_model.

    Returns:
        JSON with the list of valid task keywords from TASK_MAP that
        can be passed to the `task` parameter of recommend_model.
    """
    from coreai_catalog.catalog import TASK_MAP
    tasks = sorted(TASK_MAP.keys())
    return json.dumps({
        "count": len(tasks),
        "tasks": tasks,
    }, indent=2)


# ── Tool 11: get_version ──

@mcp.tool()
def get_version() -> str:
    """Get catalog version and content statistics.

    Returns:
        JSON with the catalog version, model count, benchmark count,
        term count, and last_verified date.
    """
    import yaml as _yaml
    cat_path = _ROOT / "catalog.yaml"
    version = "unknown"
    last_verified = None
    if cat_path.exists():
        data = _yaml.safe_load(cat_path.read_text()) or {}
        meta = data.get("metadata", {})
        version = meta.get("version", "unknown")
        last_verified = meta.get("last_verified")

    bench_count = len(catalog.benchmarks)
    term_count = len(catalog.terms)

    return json.dumps({
        "version": version,
        "model_count": len(catalog.models),
        "benchmark_count": bench_count,
        "term_count": term_count,
        "last_verified": last_verified,
    }, indent=2)


# ── Entry point ──

def main() -> None:
    """Run the MCP server via stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
