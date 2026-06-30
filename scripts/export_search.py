#!/usr/bin/env python3
"""
Export search-optimized artifacts for agent/human consumption.

Generates:
  dist/search-index.json — flattened, denormalized model entries
                           with joined artifacts, benchmarks, readiness score
  dist/models.jsonl      — one model per line (streaming-friendly)
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def main() -> None:
    catalog = read_yaml(ROOT / "catalog.yaml")
    artifacts = read_yaml(ROOT / "artifacts.yaml")
    benchmarks = read_yaml(ROOT / "benchmarks.yaml")
    sources = read_yaml(ROOT / "sources.yaml")

    art_by_id = {a["id"]: a for a in artifacts.get("artifacts", [])}

    # Build benchmark lookup: model_id → list of benchmarks
    bench_by_model: dict[str, list[dict]] = {}
    for b in benchmarks.get("benchmarks", []):
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
        })

    # Build denormalized entries
    entries = []
    for m in catalog.get("models", []):
        art = art_by_id.get(m.get("artifact_ref"), {})
        hf = art.get("huggingface", {}) or {}
        gh = art.get("github", {}) or {}
        off = art.get("officiality", {}) or {}

        ds = m.get("device_support", {})
        devices = []
        if ds.get("iphone") is True:
            devices.append("iphone")
        if ds.get("ipad") is True:
            devices.append("ipad")
        if ds.get("mac") is True:
            devices.append("mac")
        if ds.get("mac_only") is True:
            devices.append("mac_only")

        rt = m.get("runtime", {})
        size = m.get("size", {})

        # Quick readiness score
        has_bench = m["id"] in bench_by_model
        score = 0
        if m.get("artifact", {}).get("availability") == "available":
            score += 15
        if m.get("license", {}).get("commercial_use") == "likely":
            score += 10
        if ds.get("iphone") is True:
            score += 10
        if ds.get("mac") is True:
            score += 10
        if has_bench:
            score += 10
        if rt.get("stock_runtime") is True:
            score += 10
        if rt.get("custom_kernel") is False:
            score += 5
        if rt.get("patch_required") is False:
            score += 5
        if rt.get("aot_required") is not False:
            score += 5
        if m.get("status") == "confirmed":
            score += 10
        conf = m.get("confidence", "")
        if conf == "high":
            score += 5
        elif conf == "medium":
            score += 3
        elif conf == "low":
            score -= 10
        if m.get("maturity") in ("stable", "active"):
            score += 5
        score = max(0, min(100, score))

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

    DIST.mkdir(exist_ok=True)

    # search-index.json
    (DIST / "search-index.json").write_text(
        json.dumps({"count": len(entries), "models": entries}, indent=2, ensure_ascii=False) + "\n"
    )

    # models.jsonl (one per line)
    with (DIST / "models.jsonl").open("w") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Generated {len(entries)} entries:")
    print(f"  dist/search-index.json ({(DIST / 'search-index.json').stat().st_size:,} bytes)")
    print(f"  dist/models.jsonl ({(DIST / 'models.jsonl').stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
