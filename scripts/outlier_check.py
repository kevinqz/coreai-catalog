"""Outlier detection for benchmark submissions using MAD (Median Absolute Deviation).

Usage:
    python scripts/outlier_check.py --input new_lines.jsonl --existing benchmarks/benchmarks.jsonl
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    entries = []
    if not path.exists():
        return entries
    for line in path.read_text().strip().split("\n"):
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def check_outlier(
    new_value: float,
    existing: list[dict],
    model_id: str,
    device_class: str | None,
    engine: str | None,
) -> str:
    """Returns: 'pass' | 'outlier' | 'insufficient-data'"""

    # Filter to same cohort (model + device_class + engine)
    cohort_values = []
    for entry in existing:
        if entry.get("model_id") != model_id:
            continue

        entry_device = entry.get("device_info", {}).get("device_class") or entry.get("device", "")
        if device_class and entry_device != device_class:
            continue

        entry_engine = entry.get("runtime_config", {}).get("engine", "")
        if engine and entry_engine and entry_engine != engine:
            continue

        val = entry.get("value")
        if val is not None:
            try:
                cohort_values.append(float(val))
            except (ValueError, TypeError):
                pass

    if len(cohort_values) < 5:
        return "insufficient-data"

    median = statistics.median(cohort_values)
    deviations = [abs(v - median) for v in cohort_values]
    mad = statistics.median(deviations)

    if mad == 0:
        # All values identical — accept if within 10%
        ratio = abs(new_value - median) / median if median != 0 else 1.0
        return "pass" if ratio < 0.1 else "outlier"

    # Modified Z-score (Iglewicz & Hoaglin 1993)
    modified_z = 0.6745 * (new_value - median) / mad

    if abs(modified_z) > 3.5:
        return "outlier"
    return "pass"


def main() -> int:
    parser = argparse.ArgumentParser(description="Outlier detection for benchmark submissions")
    parser.add_argument("--input", required=True, help="New benchmark JSONL lines")
    parser.add_argument("--existing", default="benchmarks/benchmarks.jsonl",
                        help="Existing benchmarks")
    args = parser.parse_args()

    existing = load_jsonl(Path(args.existing))
    new_entries = load_jsonl(Path(args.input))

    if not new_entries:
        print("pass")
        print("  (no new entries to check)")
        return 0

    results = {"pass": 0, "outlier": 0, "insufficient-data": 0}

    for entry in new_entries:
        model_id = entry.get("model_id", "")
        device_class = entry.get("device_info", {}).get("device_class") or entry.get("device")

        # Extract engine from runtime_config or environment string
        engine = entry.get("runtime_config", {}).get("engine")
        if not engine:
            env = entry.get("environment", "")
            if "pipelined" in env:
                engine = "coreai-pipelined"
            elif "sequential" in env:
                engine = "coreai-sequential"
            else:
                engine = None

        value = entry.get("value")
        try:
            value = float(value)
        except (ValueError, TypeError):
            print(f"  SKIP {model_id}: non-numeric value")
            continue

        result = check_outlier(value, existing, model_id, device_class, engine)
        results[result] += 1

        print(f"  {result:20s} {model_id:40s} value={value} (cohort={model_id}+{device_class}+{engine})")

    # Final decision
    if results["outlier"] > 0:
        print("outlier")
        print(f"\n  {results['outlier']} outlier(s), {results['pass']} pass, {results['insufficient-data']} insufficient-data")
        return 0  # Don't fail the Action — label for review instead
    else:
        print("pass")
        print(f"\n  All {sum(results.values())} entries passed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
