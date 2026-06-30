#!/usr/bin/env python3
"""
Generate a model comparison table — side-by-side comparison of key
specifications across models, grouped by capability.

Usage:
  python scripts/generate_compare.py                # generates all comparisons
  python scripts/generate_compare.py --capability vision-language
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def fmt_list(items: list) -> str:
    return ", ".join(str(x) for x in (items or []))


def fmt_devices(ds: dict) -> str:
    parts = []
    if ds.get("iphone") is True:
        parts.append("iPhone")
    if ds.get("ipad") is True:
        parts.append("iPad")
    if ds.get("mac") is True:
        parts.append("Mac")
    return "/".join(parts) or "unknown"


def fmt_runtime(rt: dict) -> str:
    flags = []
    if rt.get("stock_runtime") is True:
        flags.append("stock")
    if rt.get("custom_kernel") is True:
        flags.append("custom-kernel")
    if rt.get("patch_required") is True:
        flags.append("patch")
    if rt.get("aot_required") is True:
        flags.append("AOT")
    return f"{rt.get('runner', '?')} ({', '.join(flags)})" if flags else rt.get("runner", "?")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate model comparison docs")
    parser.add_argument("--capability", "-c", help="Generate comparison for a single capability")
    args = parser.parse_args()

    catalog = read_yaml(ROOT / "catalog.yaml")
    benchmarks = read_yaml(ROOT / "benchmarks.yaml")
    artifacts = read_yaml(ROOT / "artifacts.yaml")

    models = catalog.get("models", [])
    art_by_id = {a["id"]: a for a in artifacts.get("artifacts", [])}
    bench_by_model: dict[str, list[dict]] = {}
    for b in benchmarks.get("benchmarks", []):
        bench_by_model.setdefault(b.get("model_id", ""), []).append(b)

    # Group models by capability
    from collections import defaultdict
    by_cap: dict[str, list[dict]] = defaultdict(list)
    for m in models:
        for cap in m.get("capabilities", []):
            by_cap[cap].append(m)

    caps_to_generate = [args.capability] if args.capability else sorted(by_cap.keys())

    for cap in caps_to_generate:
        cap_models = by_cap.get(cap, [])
        if not cap_models:
            print(f"No models for capability: {cap}")
            continue

        lines = [
            f"# Comparison: {cap}",
            "",
            f"Side-by-side comparison of all {len(cap_models)} model(s) with the `{cap}` capability.",
            "",
            "| Model | Family | Parameters | Precision | Devices | License | Runtime | Benchmark | Source |",
            "|---|---|---|---|---|---|---|---|---|",
        ]

        for m in sorted(cap_models, key=lambda x: x["name"]):
            bench_text = "—"
            benches = bench_by_model.get(m["id"], [])
            if benches:
                # Show best throughput or first benchmark
                best = benches[0]
                for b in benches:
                    if b.get("metric") == "decode_throughput" and b.get("value"):
                        if not best.get("value") or (
                            b["value"] and best.get("value") and b["value"] > best["value"]
                        ):
                            best = b
                if best.get("value"):
                    bench_text = f"{best['value']} {best['unit']}"
                    if best.get("device"):
                        bench_text += f" ({best['device']})"

            art = art_by_id.get(m.get("artifact_ref"), {})
            off = art.get("officiality", {}) or {}
            if off.get("apple_export_recipe"):
                source = "🍎 Apple recipe"
            elif m.get("source_group") == "external":
                source = "🔗 Independent"
            else:
                source = "🐼 Zoo"

            size = m.get("size", {})
            lines.append(
                f"| {m['name']} | {m['family']} | {size.get('parameters', '?')} | "
                f"{size.get('precision', '?')} | {fmt_devices(m.get('device_support', {}))} | "
                f"{m.get('license', {}).get('name', '?')} | {fmt_runtime(m.get('runtime', {}))} | "
                f"{bench_text} | {source} |"
            )

        lines.append("")
        lines.append("> Generated automatically by `scripts/generate_compare.py` from `catalog.yaml` + `benchmarks.yaml`.")
        lines.append("")

        filename = cap.replace(" ", "-") + ".md"
        output_dir = DOCS / "compare"
        output_dir.mkdir(exist_ok=True)
        (output_dir / filename).write_text("\n".join(lines) + "\n")
        print(f"Generated: docs/compare/{filename} ({len(cap_models)} models)")

    print(f"\nDone. {len(caps_to_generate)} comparison doc(s) generated.")


if __name__ == "__main__":
    main()
