#!/usr/bin/env python3
"""
Core AI Readiness Score — transforms catalog metadata into a 0-100
deployment-readiness score for each model.

Score dimensions (each adds points; max 100):
  Artifact availability       15
  License clarity             10
  iPhone support known        10
  Mac support known           10
  Benchmark available         10
  Stock runtime (no patches)  10
  No custom kernel required    5
  No patch required            5
  AOT status known             5
  Source verified (confirmed) 10
  Confidence bonus             5
  Maturity bonus               5

Negative:
  Confidence low              -10
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def score_model(model: dict, has_benchmark: bool) -> dict:
    """Return score, breakdown, and grade for a single model."""
    score = 0
    breakdown: list[tuple[str, int]] = []

    def add(label: str, points: int, condition: bool) -> None:
        nonlocal score
        score_val = points if condition else 0
        score += score_val
        breakdown.append((label, score_val))

    # Artifact
    add("artifact_available", 15, model.get("artifact", {}).get("availability") == "available")

    # License clarity
    add("license_clear", 10, model.get("license", {}).get("commercial_use") == "likely")

    # Device support known
    ds = model.get("device_support", {})
    add("iphone_support_known", 10, ds.get("iphone") is True)
    add("mac_support_known", 10, ds.get("mac") is True)

    # Benchmark
    add("benchmark_available", 10, has_benchmark)

    # Runtime ease
    rt = model.get("runtime", {})
    add("stock_runtime", 10, rt.get("stock_runtime") is True)
    add("no_custom_kernel", 5, rt.get("custom_kernel") is False)
    add("no_patch_required", 5, rt.get("patch_required") is False)
    add("aot_status_known", 5, rt.get("aot_required") is not False)

    # Trust
    add("status_confirmed", 10, model.get("status") == "confirmed")

    # Confidence bonus
    conf = model.get("confidence", "")
    if conf == "high":
        add("confidence_bonus", 5, True)
    elif conf == "medium":
        add("confidence_bonus", 3, True)
    elif conf == "low":
        add("confidence_penalty", -10, True)
    else:
        add("confidence_bonus", 0, True)

    # Maturity bonus
    maturity = model.get("maturity", "")
    if maturity in ("stable", "active"):
        add("maturity_bonus", 5, True)
    else:
        add("maturity_bonus", 2, True)

    # Clamp
    score = max(0, min(100, score))

    if score >= 85:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 55:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    return {
        "id": model["id"],
        "name": model["name"],
        "score": score,
        "grade": grade,
        "breakdown": {label: pts for label, pts in breakdown},
    }


def main() -> int:
    catalog = read_yaml(ROOT / "catalog.yaml")
    benchmarks = read_yaml(ROOT / "benchmarks.yaml")

    benched_ids = {b["model_id"] for b in benchmarks.get("benchmarks", [])}

    results = []
    for model in catalog.get("models", []):
        results.append(score_model(model, model["id"] in benched_ids))

    results.sort(key=lambda r: r["score"], reverse=True)

    # Print human-readable
    if "--json" not in sys.argv:
        print(f"{'Score':>5}  {'Grade':>5}  {'ID':40s}  Name")
        print("-" * 90)
        for r in results:
            print(f"{r['score']:5d}  {r['grade']:>5}  {r['id']:40s}  {r['name']}")
        print(f"\nTotal: {len(results)} models scored.")

        grade_counts = {}
        for r in results:
            grade_counts[r["grade"]] = grade_counts.get(r["grade"], 0) + 1
        print("Grade distribution: " + ", ".join(
            f"{g}: {c}" for g, c in sorted(grade_counts.items())
        ))

    # Write JSON
    DIST.mkdir(exist_ok=True)
    output = {"readiness_scores": results}
    (DIST / "readiness-scores.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    )

    if "--json" in sys.argv:
        print(json.dumps(output, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
