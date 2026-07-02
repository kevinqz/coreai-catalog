#!/usr/bin/env python3
"""Outlier check for benchmark submissions using MAD (Median Absolute Deviation).

Reads a submitted JSONL line and compares the value against the existing cohort
in benchmarks.jsonl. Exits non-zero on outliers to prevent auto-merge.

Usage:
    python scripts/outlier_check.py --input <file_with_jsonl_line> [--catalog benchmarks.jsonl]

Exit codes:
    0 — pass (value is within expected range, or insufficient data)
    1 — outlier (value is >3.5 modified-z from median)
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_cohort(
    catalog_path: Path, model_id: str, metric: str, device_class: str
) -> list[float]:
    """Load existing benchmark values for the same model+device+metric."""
    values: list[float] = []
    if not catalog_path.exists():
        return values
    for line in catalog_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            entry.get("model_id") == model_id
            and entry.get("metric") == metric
            and entry.get("device_class") == device_class
        ):
            try:
                values.append(float(entry["value"]))
            except (ValueError, TypeError):
                pass
    return values


def compute_mad_zscore(value: float, cohort: list[float]) -> tuple[float, str]:
    """Compute modified z-score using MAD.

    Returns (z_score, status) where status is 'pass', 'outlier', or 'insufficient-data'.
    """
    if len(cohort) < 5:
        return 0.0, "insufficient-data"

    median = statistics.median(cohort)
    deviations = [abs(v - median) for v in cohort]
    mad = statistics.median(deviations)

    if mad == 0:
        return 0.0, "pass"  # All identical values

    modified_z = 0.6745 * (value - median) / mad
    if abs(modified_z) >= 3.5:
        return modified_z, "outlier"
    return modified_z, "pass"


def main() -> int:
    parser = argparse.ArgumentParser(description="Outlier check for benchmark submissions")
    parser.add_argument("--input", required=True, help="File containing the new JSONL line(s)")
    parser.add_argument("--catalog", default=str(ROOT / "benchmarks.jsonl"),
                        help="Path to existing benchmarks JSONL")
    args = parser.parse_args()

    # Read submission
    input_path = Path(args.input)
    raw = input_path.read_text().strip()
    lines = [l for l in raw.splitlines() if l.strip() and not l.strip().startswith("#")]

    if not lines:
        print("No valid lines to check", file=sys.stderr)
        return 1

    catalog_path = Path(args.catalog)
    all_pass = True
    results: list[str] = []

    for i, line in enumerate(lines):
        line = line.strip().lstrip("+")
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            results.append(f"Line {i+1}: INVALID JSON: {e}")
            all_pass = False
            continue

        entry.pop("_signature", None)  # Don't include signature in analysis

        model_id = entry.get("model_id", "")
        metric = entry.get("metric", "")
        device_class = entry.get("device_class", "")
        value = float(entry.get("value", 0))

        cohort = load_cohort(catalog_path, model_id, metric, device_class)
        z, status = compute_mad_zscore(value, cohort)

        if status == "outlier":
            all_pass = False
            results.append(
                f"Line {i+1}: OUTLIER (z={z:.2f}, cohort N={len(cohort)}, "
                f"median={statistics.median(cohort):.1f}, value={value})"
            )
        elif status == "insufficient-data":
            results.append(
                f"Line {i+1}: INSUFFICIENT DATA (cohort N={len(cohort)}, need >=5)"
            )
        else:
            results.append(
                f"Line {i+1}: PASS (z={z:.2f}, cohort N={len(cohort)}, "
                f"median={statistics.median(cohort):.1f})"
            )

    # Write comment file for GitHub Action
    comment = "## Outlier Check Results\n\n| Line | Result |\n|---|---|\n"
    for r in results:
        comment += f"| {r.split(':', 1)[0]} | {r.split(':', 1)[1].strip()} |\n"

    comment_path = Path("/tmp/outlier-comment.md")
    try:
        comment_path.write_text(comment)
    except OSError:
        pass  # /tmp might not be writable

    for r in results:
        print(r)

    if not all_pass:
        print("\n::error::Outlier detected — prevents auto-merge", file=sys.stderr)
        return 1

    print("\nAll checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
