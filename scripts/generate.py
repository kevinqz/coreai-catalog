#!/usr/bin/env python3
"""
Unified doc + export generator.

Replaces: generate_docs.py, generate_artifact_docs.py,
generate_terms_docs.py, generate_index.py, generate_compare.py,
export_json.py, export_search.py, readiness_score.py

Usage:
  python scripts/generate.py           # generate everything
  python scripts/generate.py --docs    # only markdown docs
  python scripts/generate.py --json    # only JSON exports + scores
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

sys.path.insert(0, str(ROOT))
from coreai_catalog.exports import export_json, export_search_index, export_transform_graph, export_model_manifest


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def read_benchmarks() -> dict:
    """Read benchmarks.jsonl (single source of truth) as {"benchmarks": [...]}."""
    from coreai_catalog.exports import read_benchmarks_jsonl
    return read_benchmarks_jsonl(ROOT)


# ── Markdown doc generators ──


def gen_model_registry(catalog: dict) -> None:
    """Generate docs/model-registry.md"""
    lines = [
        "# Model Registry",
        "",
        "| ID | Model | Group | Family | Capabilities | Input | Output | Size | Device | License | Status |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    def fmt(v):
        return ", ".join(str(x) for x in (v or []))

    def dev(ds):
        out = []
        if ds.get("iphone") is True:
            out.append("iPhone")
        if ds.get("ipad") is True:
            out.append("iPad")
        if ds.get("mac") is True:
            out.append("Mac")
        return "/".join(out) or "unknown"

    for m in catalog.get("models", []):
        lines.append(
            f"| {m['id']} | {m['name']} | {m['source_group']} | {m['family']} | "
            f"{fmt(m['capabilities'])} | {fmt(m['modalities']['input'])} | "
            f"{fmt(m['modalities']['output'])} | {m['size'].get('parameters', 'unknown')} | "
            f"{dev(m['device_support'])} | {m['license'].get('name', 'unknown')} | {m['status']} |"
        )
    (DOCS / "model-registry.md").write_text("\n".join(lines) + "\n")


def gen_artifact_provenance(artifacts: dict) -> None:
    """Generate docs/artifact-provenance.md"""
    lines = [
        "# Artifact Provenance",
        "",
        "Generated from `artifacts.yaml`.",
        "",
        "| ID | Group | GitHub | Hugging Face | Apple recipe | Apple-hosted |",
        "|---|---|---|---|---|---|",
    ]
    for a in artifacts.get("artifacts", []):
        gh = a.get("github", {})
        hf = a.get("huggingface", {})
        off = a.get("officiality", {})
        lines.append(
            f"| {a['id']} | {a['group']} | {gh.get('owner', '')}/{gh.get('repo', '')} | "
            f"{hf.get('owner', '')}/{hf.get('repo', '')} | "
            f"{off.get('apple_export_recipe', '')} | {off.get('apple_hosted_artifact', '')} |"
        )
    (DOCS / "artifact-provenance.md").write_text("\n".join(lines) + "\n")


def gen_terms(terms_data: dict) -> None:
    """Generate docs/apple-terminology-map.md"""
    LAYER_ORDER = [
        "system_surface", "developer_framework", "model_provider",
        "provider_protocol", "ai_primitive", "artifact_format",
        "developer_tool", "model",
    ]
    LAYER_LABEL = {
        "system_surface": "System surfaces",
        "developer_framework": "Developer frameworks",
        "model_provider": "Model providers",
        "provider_protocol": "Provider protocols",
        "ai_primitive": "AI primitives",
        "artifact_format": "Artifact formats",
        "developer_tool": "Developer tools",
        "model": "Models",
    }

    by_layer: dict[str, list] = defaultdict(list)
    for t in terms_data.get("terms", []):
        layer = t.get("apple_layer", "model")
        by_layer[layer].append(t)

    lines = ["# Apple AI Terminology Map", "", "Generated from `terms.yaml`.", ""]
    for layer in LAYER_ORDER:
        items = by_layer.get(layer, [])
        if not items:
            continue
        lines.append(f"## {LAYER_LABEL.get(layer, layer)}")
        lines.append("")
        for t in items:
            lines.append(f"### {t['label']}")
            lines.append("")
            lines.append(f"{t['definition']}")
            lines.append("")
            lines.append(f"**Source:** {t.get('official_source', 'N/A')}")
            lines.append("")
    (DOCS / "apple-terminology-map.md").write_text("\n".join(lines) + "\n")


def gen_index(catalog: dict, artifacts: dict, benchmarks: dict, terms_data: dict,
              sources: dict, upstreams: dict) -> None:
    """Generate docs/index.md with live counts"""
    UPSTREAM_GROUPS = [
        "framework_sources", "conversion_sources", "artifact_hosts",
        "benchmark_sources", "sample_sources", "original_model_sources",
        "license_sources",
    ]
    upstream_count = sum(len(upstreams.get(g, []) or []) for g in UPSTREAM_GROUPS)

    lines = [
        "# Core AI Catalog Docs",
        "",
        "## Core views",
        "",
        "- [Model Registry](./model-registry.md)",
        "- [Capability Matrix](./capability-matrix.md)",
        "- [Runtime Matrix](./runtime-matrix.md)",
        "- [Artifact Provenance](./artifact-provenance.md)",
        "- [Upstream Map](./upstream-map.md)",
        "- [Benchmark Map](./benchmark-map.md)",
        "- [Source Map](./source-map.md)",
        "- [Apple Terminology Map](./apple-terminology-map.md)",
        "- [Data Model](./data-model.md)",
        "- [Generated Files Policy](./generated-files.md)",
        "- [v0.3 Verification Checklist](./v0.3-verification.md)",
        "- [SotA Maintenance Plan](./sota-maintenance.md)",
        "",
        "## Counts",
        "",
        f"- Models: {len(catalog.get('models', []))}",
        f"- Artifacts: {len(artifacts.get('artifacts', []))}",
        f"- Sources: {len(sources.get('sources', []))}",
        f"- Upstream taxonomy entries: {upstream_count}",
        f"- Benchmark records: {len(benchmarks.get('benchmarks', []))}",
        f"- Terminology records: {len(terms_data.get('terms', []))}",
        "",
        "> Counts are generated automatically by `scripts/generate.py`. "
        "Never edit this section manually.",
        "",
        "## Source of truth",
        "",
        "- `../catalog.yaml`",
        "- `../artifacts.yaml`",
        "- `../sources.yaml`",
        "- `../upstreams.yaml`",
        "- `../benchmarks.jsonl`",
        "- `../terms.yaml`",
        "- `../CREDITS.md`",
        "",
        "## Generated exports",
        "",
        "Run:",
        "",
        "```bash",
        "python scripts/generate.py --json",
        "```",
        "",
        "This generates JSON views under `dist/`.",
        "",
    ]
    (DOCS / "index.md").write_text("\n".join(lines) + "\n")


def gen_compare(catalog: dict, benchmarks: dict, artifacts: dict) -> None:
    """Generate docs/compare/*.md — one per capability"""
    bench_by_model: dict[str, list[dict]] = defaultdict(list)
    for b in benchmarks.get("benchmarks", []):
        bench_by_model[b.get("model_id", "")].append(b)

    by_cap: dict[str, list[dict]] = defaultdict(list)
    for m in catalog.get("models", []):
        for cap in m.get("capabilities", []):
            by_cap[cap].append(m)

    compare_dir = DOCS / "compare"
    compare_dir.mkdir(exist_ok=True)

    # Clean old files
    for f in compare_dir.glob("*.md"):
        f.unlink()

    for cap, cap_models in sorted(by_cap.items()):
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
                best = benches[0]
                for b in benches:
                    if b.get("metric") == "decode_throughput" and b.get("value"):
                        if not best.get("value") or b["value"] > best["value"]:
                            best = b
                if best.get("value"):
                    bench_text = f"{best['value']} {best['unit']}"
                    device = best.get("device_class") or best.get("device")
                    if device:
                        bench_text += f" ({device})"

            art = next((a for a in artifacts.get("artifacts", []) if a["id"] == m.get("artifact_ref")), {})
            off = art.get("officiality", {}) if art else {}
            if off.get("apple_export_recipe"):
                source = "🍎 Apple recipe"
            elif m.get("source_group") == "external":
                source = "🔗 Independent"
            else:
                source = "🐼 Zoo"

            ds = m.get("device_support", {})
            devices = []
            if ds.get("iphone") is True:
                devices.append("iPhone")
            if ds.get("ipad") is True:
                devices.append("iPad")
            if ds.get("mac") is True:
                devices.append("Mac")

            size = m.get("size", {})
            lines.append(
                f"| {m['name']} | {m['family']} | {size.get('parameters', '?')} | "
                f"{size.get('precision', '?')} | {'/'.join(devices) or 'unknown'} | "
                f"{m.get('license', {}).get('name', '?')} | {m.get('runtime', {}).get('runner', '?')} | "
                f"{bench_text} | {source} |"
            )
        lines.append("")
        lines.append("> Generated automatically by `scripts/generate.py` from `catalog.yaml` + `benchmarks.jsonl`.")
        lines.append("")
        filename = cap.replace(" ", "-") + ".md"
        (compare_dir / filename).write_text("\n".join(lines) + "\n")

    print(f"  compare/: {len(by_cap)} capability tables")


# ── Main ──


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate docs and JSON exports")
    parser.add_argument("--docs", action="store_true", help="Only generate markdown docs")
    parser.add_argument("--json", action="store_true", help="Only generate JSON exports + scores")
    args = parser.parse_args()

    do_docs = args.docs or (not args.docs and not args.json)
    do_json = args.json or (not args.docs and not args.json)

    catalog = read_yaml(ROOT / "catalog.yaml")
    artifacts = read_yaml(ROOT / "artifacts.yaml")
    benchmarks = read_benchmarks()
    terms_data = read_yaml(ROOT / "terms.yaml")
    sources = read_yaml(ROOT / "sources.yaml")
    upstreams = read_yaml(ROOT / "upstreams.yaml")

    if do_docs:
        print("Generating docs...")
        gen_model_registry(catalog)
        gen_artifact_provenance(artifacts)
        gen_terms(terms_data)
        gen_index(catalog, artifacts, benchmarks, terms_data, sources, upstreams)
        gen_compare(catalog, benchmarks, artifacts)
        print(f"  model-registry.md, artifact-provenance.md, apple-terminology-map.md, index.md")

    if do_json:
        print("Generating JSON exports...")
        export_json(ROOT)
        count = export_search_index(ROOT)
        print(f"  {count} entries -> search-index.json, models.jsonl, readiness-scores.json")
        export_transform_graph(ROOT)
        print(f"  transforms-graph.json")
        export_model_manifest(ROOT)
        print(f"  model-manifest.json")

        # Phase 3: Generate aggregate benchmarks with minimum-k=3 suppression
        from scripts.generate_benchmarks_aggregate import generate_aggregate as gen_agg
        agg = gen_agg(ROOT / "benchmarks.jsonl", ROOT / "dist")
        print(f"  benchmarks-aggregate.json ({agg['published_count']} published, {agg['suppressed_count']} suppressed)")

        from coreai_catalog.exports import export_leaderboard, export_aliases
        lb = export_leaderboard(ROOT)
        print(f"  leaderboard.json ({lb['total_models']} models ranked)")
        al = export_aliases(ROOT)
        print(f"  aliases.json ({al['total_models']} entries)")

    # Sync YAML data into package for pip distribution
    print("Syncing package data...")
    import subprocess, sys
    subprocess.run([sys.executable, str(ROOT / "scripts" / "sync_package_data.py")],
                   capture_output=True)

    # Generate task pages
    print("Generating task pages...")
    from coreai_catalog.task_pages import generate_task_pages, export_task_json
    pages = generate_task_pages(ROOT)
    tasks_exported = export_task_json(ROOT)
    print(f"  {pages} capability pages, {tasks_exported} task JSONs")

    return 0


if __name__ == "__main__":
    sys.exit(main())
