#!/usr/bin/env python3
"""
Generate docs/index.md from YAML sources so counts are always accurate.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def count_upstream_layers(upstreams: dict) -> int:
    UPSTREAM_GROUPS = [
        "framework_sources",
        "conversion_sources",
        "artifact_hosts",
        "benchmark_sources",
        "sample_sources",
        "original_model_sources",
        "license_sources",
    ]
    return sum(len(upstreams.get(g, []) or []) for g in UPSTREAM_GROUPS)


def main() -> None:
    catalog = read_yaml(ROOT / "catalog.yaml")
    artifacts = read_yaml(ROOT / "artifacts.yaml")
    benchmarks = read_yaml(ROOT / "benchmarks.yaml")
    terms = read_yaml(ROOT / "terms.yaml")
    sources = read_yaml(ROOT / "sources.yaml")
    upstreams = read_yaml(ROOT / "upstreams.yaml")

    model_count = len(catalog.get("models", []))
    artifact_count = len(artifacts.get("artifacts", []))
    benchmark_count = len(benchmarks.get("benchmarks", []))
    term_count = len(terms.get("terms", []))
    source_count = len(sources.get("sources", []))
    upstream_count = count_upstream_layers(upstreams)

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
        f"- Models: {model_count}",
        f"- Artifacts: {artifact_count}",
        f"- Sources: {source_count}",
        f"- Upstream taxonomy entries: {upstream_count}",
        f"- Benchmark records: {benchmark_count}",
        f"- Terminology records: {term_count}",
        "",
        "> Counts are generated automatically by `scripts/generate_index.py`. "
        "Never edit this section manually.",
        "",
        "## Source of truth",
        "",
        "- `../catalog.yaml`",
        "- `../artifacts.yaml`",
        "- `../sources.yaml`",
        "- `../upstreams.yaml`",
        "- `../benchmarks.yaml`",
        "- `../terms.yaml`",
        "- `../CREDITS.md`",
        "",
        "## Generated exports",
        "",
        "Run:",
        "",
        "```bash",
        "python scripts/export_json.py",
        "```",
        "",
        "This generates JSON views under `dist/`.",
        "",
    ]

    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
