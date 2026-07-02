#!/usr/bin/env python3
"""Migrate benchmarks.yaml to benchmarks.jsonl (append-only format).

Handles the actual data shapes in the existing YAML — including free-text
environment strings, human-readable device names, and unstructured notes.

Usage:
    python scripts/migrate_benchmarks_to_jsonl.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def parse_os_major(environment: str | None) -> str:
    """Extract major OS version from free-text environment string.

    Handles: 'iOS 27 beta, coreai-pipelined engine', 'macOS 27 beta',
             'iOS 27 beta, Release, AOT h18p encoder', etc.
    """
    if not environment:
        return "unknown"
    m = re.search(r'(?:iOS|macOS)\s+(\d+)', environment)
    return m.group(1) if m else "unknown"


def parse_device_class(device: str | None) -> str:
    """Normalize device strings to hardware chip class.

    Already-class strings pass through. Human-readable names map to chips.
    """
    if not device:
        return "unknown"
    # Already a chip class
    if any(x in device for x in ["A18", "A17", "M4", "M3", "M2", "A16"]):
        return device
    # Human-readable device names → chip class
    mapping = {
        "iPhone 17 Pro": "A18 Pro",
        "iPhone 17 Pro Max": "A18 Pro",
        "iPhone 17": "A18",
        "iPhone 16 Pro": "A18 Pro",
        "iPhone 16 Pro Max": "A18 Pro",
        "iPhone 16": "A18",
        "MacBook Pro (M4 Max)": "M4 Max",
        "MacBook Pro (M3 Max)": "M3 Max",
        "Mac Studio (M2 Ultra)": "M2 Ultra",
    }
    return mapping.get(device, device)


def parse_engine(environment: str | None) -> str:
    """Extract engine variant from environment string."""
    if not environment:
        return "unknown"
    env = environment.lower()
    if "pipelined" in env:
        return "coreai-pipelined"
    if "sequential" in env:
        return "coreai-sequential"
    if "aot" in env:
        return "coreai-aot"
    return "coreai"


def detect_low_power(environment: str | None) -> bool:
    """Check for low power mode mentions."""
    if not environment:
        return False
    return "low power" in environment.lower()


def determine_extraction_method(notes: str | None) -> str:
    """Infer extraction method from benchmark notes."""
    if not notes:
        return "upstream_readme_manual"
    n = notes.lower()
    if "readme" in n or "table" in n or "upstream" in n:
        return "upstream_readme_manual"
    if "script" in n or "automated" in n or "benchmark" in n and "run" in n:
        return "upstream_readme_scripted"
    return "upstream_readme_manual"


def migrate() -> int:
    bench_path = ROOT / "benchmarks.yaml"
    if not bench_path.exists():
        print("Error: benchmarks.yaml not found", file=sys.stderr)
        return 1

    with open(bench_path) as f:
        data = yaml.safe_load(f)

    entries = data.get("benchmarks", [])
    output_path = ROOT / "benchmarks.jsonl"

    migrated = 0
    skipped = 0

    with output_path.open("w") as out:
        for b in entries:
            # Build v2 entry from v1 fields
            entry = {
                "id": b.get("id", f"bm-migrated-{migrated:04d}"),
                "model_id": b.get("model_id", ""),
                "metric": b.get("metric", ""),
                "value": b.get("value", 0),
                "unit": b.get("unit", ""),
                "device_class": parse_device_class(b.get("device")),
                "os_major": parse_os_major(b.get("environment")),
                "compute_unit": b.get("compute_unit", "unknown"),
                "precision": b.get("precision", "unknown"),
                "extraction_method": determine_extraction_method(b.get("notes")),
                "confidence": b.get("confidence", "medium"),
                "observed_date": b.get("observed", ""),
                "source": b.get("source", "migration"),
                "device_verified": False,
                "model_verified": False,
                "higher_is_better": b.get("higher_is_better", True),
                "environment": {
                    "protocol_version": "0",
                    "engine": parse_engine(b.get("environment")),
                    "thermal_state": "unknown",
                    "battery_state": "unknown",
                    "low_power_mode": detect_low_power(b.get("environment")),
                },
            }

            # Preserve original notes
            if b.get("notes"):
                entry["notes"] = b["notes"]

            # Validate required fields
            if not entry["model_id"] or not entry["metric"]:
                print(f"  SKIP: {entry['id']} — missing model_id or metric", file=sys.stderr)
                skipped += 1
                continue

            out.write(json.dumps(entry, ensure_ascii=False) + "\n")
            migrated += 1

    print(f"Migrated {migrated} benchmarks to {output_path}")
    if skipped:
        print(f"Skipped {skipped} entries with missing fields")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
