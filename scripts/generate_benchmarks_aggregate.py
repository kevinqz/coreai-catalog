#!/usr/bin/env python3
"""Generate aggregate benchmark statistics with minimum-k=3 privacy suppression.

Groups benchmarks by (model_id, device_class, metric) and computes medians,
percentiles, and sample counts. Combos with <3 samples are suppressed
to prevent k=1 de-anonymization.

Usage:
    python scripts/generate_benchmarks_aggregate.py
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _get_catalog_version_safe(jsonl_path: Path) -> str:
    """Try to read catalog version from catalog.yaml."""
    import yaml
    catalog_path = jsonl_path.parent / "catalog.yaml"
    if catalog_path.exists():
        try:
            data = yaml.safe_load(catalog_path.read_text()) or {}
            return data.get("metadata", {}).get("version", "unknown")
        except Exception:
            pass
    return "unknown"


def generate_aggregate(jsonl_path: Path | None = None, dist: Path | None = None) -> dict:
    """Generate aggregate statistics from benchmarks.jsonl.

    Returns the aggregate dict and writes it to dist/benchmarks-aggregate.json.
    """
    jsonl_path = jsonl_path or ROOT / "benchmarks.jsonl"
    dist = dist or ROOT / "dist"
    dist.mkdir(exist_ok=True)

    # Group by (model_id, device_class, metric)
    groups: dict[tuple[str, str, str], list[float]] = defaultdict(list)

    if not jsonl_path.exists():
        output = {"aggregates": [], "suppressed_count": 0, "total_count": 0}
        (dist / "benchmarks-aggregate.json").write_text(
            json.dumps(output, indent=2, ensure_ascii=False) + "\n"
        )
        return output

    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Filter: only high/medium confidence for aggregate
        confidence = entry.get("confidence", "low")
        if confidence not in ("high", "medium"):
            continue

        key = (
            entry.get("model_id", ""),
            entry.get("device_class", ""),
            entry.get("metric", ""),
        )
        try:
            groups[key].append(float(entry["value"]))
        except (ValueError, TypeError, KeyError):
            pass

    aggregates: list[dict] = []
    suppressed_count = 0

    for (model_id, device_class, metric), values in sorted(groups.items()):
        n = len(values)

        # Minimum-k=3 suppression
        if n < 3:
            aggregates.append({
                "model_id": model_id,
                "device_class": device_class,
                "metric": metric,
                "sample_count": n,
                "suppressed": True,
            })
            suppressed_count += 1
            continue

        sorted_vals = sorted(values)
        aggregates.append({
            "model_id": model_id,
            "device_class": device_class,
            "metric": metric,
            "sample_count": n,
            "suppressed": False,
            "median": round(statistics.median(values), 2),
            "p25": round(sorted_vals[max(0, n // 4 - 1)], 2),
            "p75": round(sorted_vals[min(n - 1, 3 * n // 4)], 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
        })

    output = {
        "export_schema_version": "1.0",
        "export_catalog_version": _get_catalog_version_safe(jsonl_path),
        "description": "Aggregate benchmark statistics grouped by model_id + device_class + metric. Entries with sample_count < 3 are suppressed (suppressed: true) to protect privacy. Only high/medium confidence entries are included.",
        "aggregates": aggregates,
        "suppressed_count": suppressed_count,
        "total_count": len(aggregates),
        "published_count": len(aggregates) - suppressed_count,
    }

    (dist / "benchmarks-aggregate.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    )
    return output


if __name__ == "__main__":
    result = generate_aggregate()
    print(f"Aggregate: {result['published_count']} published, "
          f"{result['suppressed_count']} suppressed (k<3), "
          f"{result['total_count']} total groups")
