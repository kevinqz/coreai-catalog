#!/usr/bin/env python3
"""
Core AI Catalog query tool — search models by capability, device, license,
family, and more.

Usage:
  python scripts/query.py --capability vision-language --device iphone
  python scripts/query.py --capability speech-to-text --license likely
  python scripts/query.py --family Qwen --device mac
  python scripts/query.py --capability chat --min-score 70
  python scripts/query.py --source-group official
  python scripts/query.py --json --capability object-detection
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Query the Core AI Catalog")
    parser.add_argument("--capability", "-c", help="Filter by capability")
    parser.add_argument("--device", "-d", help="Filter by device (iphone, ipad, mac)")
    parser.add_argument("--license", "-l", help="Filter by commercial_use (likely, check_license)")
    parser.add_argument("--family", "-f", help="Filter by model family")
    parser.add_argument("--source-group", "-g", help="Filter by source_group (zoo, official, external)")
    parser.add_argument("--modality", "-m", help="Filter by input/output modality (text, image, audio)")
    parser.add_argument("--min-score", type=int, help="Minimum readiness score")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--full", action="store_true", help="Show full model details")
    args = parser.parse_args()

    catalog = read_yaml(ROOT / "catalog.yaml")
    benchmarks = read_yaml(ROOT / "benchmarks.yaml")
    artifacts = read_yaml(ROOT / "artifacts.yaml")

    models = catalog.get("models", [])
    benched_ids = {b["model_id"] for b in benchmarks.get("benchmarks", [])}
    art_by_id = {a["id"]: a for a in artifacts.get("artifacts", [])}

    results = []
    for m in models:
        # Capability filter
        if args.capability:
            caps = [c.lower() for c in m.get("capabilities", [])]
            if args.capability.lower() not in caps:
                continue

        # Device filter
        if args.device:
            ds = m.get("device_support", {})
            if args.device.lower() not in ("iphone", "ipad", "mac", "mac_only"):
                continue
            val = ds.get(args.device.lower())
            if val is not True:
                continue

        # License filter
        if args.license:
            if m.get("license", {}).get("commercial_use") != args.license:
                continue

        # Family filter
        if args.family:
            if m.get("family", "").lower() != args.family.lower():
                continue

        # Source group filter
        if args.source_group:
            if m.get("source_group") != args.source_group:
                continue

        # Modality filter
        if args.modality:
            inp = [x.lower() for x in m.get("modalities", {}).get("input", [])]
            out = [x.lower() for x in m.get("modalities", {}).get("output", [])]
            if args.modality.lower() not in inp and args.modality.lower() not in out:
                continue

        # Min score (simple version: count trues in key fields)
        if args.min_score:
            score = _quick_score(m, m["id"] in benched_ids)
            if score < args.min_score:
                continue

        entry = {
            "id": m["id"],
            "name": m["name"],
            "family": m["family"],
            "capabilities": m.get("capabilities", []),
            "device_support": m.get("device_support", {}),
            "license": m.get("license", {}),
            "source_group": m.get("source_group"),
            "status": m.get("status"),
            "has_benchmark": m["id"] in benched_ids,
            "artifact_url": art_by_id.get(m.get("artifact_ref"), {}).get("huggingface", {}).get("url", ""),
        }

        if args.full:
            entry["size"] = m.get("size", {})
            entry["runtime"] = m.get("runtime", {})
            entry["maturity"] = m.get("maturity")
            entry["confidence"] = m.get("confidence")
            entry["notes"] = m.get("notes")

        results.append(entry)

    if args.json:
        print(json.dumps({"count": len(results), "models": results}, indent=2, ensure_ascii=False))
    else:
        if not results:
            print("No models match the given filters.")
            return 0

        print(f"Found {len(results)} model(s):\n")
        for r in results:
            ds = r["device_support"]
            devices = []
            if ds.get("iphone") is True:
                devices.append("📱")
            if ds.get("mac") is True:
                devices.append("💻")
            bench = "📊" if r["has_benchmark"] else "  "
            lic = "✅" if r["license"].get("commercial_use") == "likely" else "⚠️"
            print(f"  {r['id']:40s}  {''.join(devices)} {bench} {lic}  {r['name']}")

        print(f"\nFilters: ", end="")
        parts = []
        if args.capability:
            parts.append(f"capability={args.capability}")
        if args.device:
            parts.append(f"device={args.device}")
        if args.license:
            parts.append(f"license={args.license}")
        if args.family:
            parts.append(f"family={args.family}")
        if args.source_group:
            parts.append(f"source_group={args.source_group}")
        if args.modality:
            parts.append(f"modality={args.modality}")
        print(", ".join(parts) if parts else "(none)")

    return 0


def _quick_score(model: dict, has_benchmark: bool) -> int:
    """Quick readiness estimate for filtering."""
    score = 0
    if model.get("artifact", {}).get("availability") == "available":
        score += 15
    if model.get("license", {}).get("commercial_use") == "likely":
        score += 10
    if model.get("device_support", {}).get("iphone") is True:
        score += 10
    if model.get("device_support", {}).get("mac") is True:
        score += 10
    if has_benchmark:
        score += 10
    if model.get("runtime", {}).get("stock_runtime") is True:
        score += 10
    if model.get("status") == "confirmed":
        score += 10
    if model.get("confidence") == "high":
        score += 5
    return score


if __name__ == "__main__":
    sys.exit(main())
