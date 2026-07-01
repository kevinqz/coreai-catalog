"""
Core AI Catalog task page generation.

Generates:
  - docs/tasks/{capability}.md — per-capability markdown with model tables
  - dist/tasks/index.json — task index
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from .catalog import Catalog, TASK_MAP
from .exports import EXPORT_SCHEMA_VERSION, _get_catalog_version


def _capability_slug(cap: str) -> str:
    """Convert capability name to URL-friendly slug."""
    return cap.replace("/", "-").replace(" ", "-")


def generate_task_pages(catalog_root: Path) -> int:
    """Generate docs/tasks/{capability}.md for each capability.

    Returns number of pages generated.
    """
    docs_tasks = catalog_root / "docs" / "tasks"
    docs_tasks.mkdir(parents=True, exist_ok=True)

    cat = Catalog(catalog_root)
    pages = 0

    # Build reverse map: capability → list of task synonyms
    cap_to_tasks: dict[str, list[str]] = {}
    for task_syn, caps in TASK_MAP.items():
        for cap in caps:
            cap_to_tasks.setdefault(cap, []).append(task_syn)

    # Group models by capability
    cap_models: dict[str, list[dict]] = {}
    for m in cat.models:
        for cap in m.get("capabilities", []):
            cap_models.setdefault(cap, []).append(m)

    # Generate a page per capability
    for cap in sorted(cap_models.keys()):
        models = cap_models[cap]
        # Sort by readiness score descending, then by name
        scored = [(m, cat.readiness_score(m)) for m in models]
        scored.sort(key=lambda x: (-x[1], x[0]["name"]))

        tasks = sorted(cap_to_tasks.get(cap, []))
        slug = _capability_slug(cap)

        md = f"# {cap.replace('-', ' ').title()}\n\n"
        md += f"**{len(models)} models** in the catalog with this capability.\n\n"

        if tasks:
            md += "## Task synonyms\n\n"
            md += ", ".join(f"`{t}`" for t in tasks)
            md += "\n\n"

        md += "## Models\n\n"
        md += "| Model | Score | Parameters | Devices | License | Commercial | Benchmark | Source |\n"
        md += "|---|---|---|---|---|---|---|---|\n"
        for m, score in scored:
            ds = m.get("device_support", {})
            devices = []
            if ds.get("iphone") is True:
                devices.append("📱")
            if ds.get("ipad") is True:
                devices.append("📐")
            if ds.get("mac") is True:
                devices.append("💻")
            params = m.get("size", {}).get("parameters", "?")
            lic = m.get("license", {})
            lic_name = lic.get("name", "?")
            cu = lic.get("commercial_use", "?")
            cu_icon = "✅" if cu == "likely" else "⚠️"
            has_bench = bool(cat.get_benchmarks(m["id"]))
            bench_icon = "📊" if has_bench else "—"
            sg = m.get("source_group", "?")
            sg_icon = {"official": "🍎", "zoo": "🐼", "external": "🔗"}.get(sg, sg)

            md += f"| [{m['name']}](../../catalog.yaml#L{1}) | {score} | {params} | {''.join(devices)} | {lic_name} | {cu_icon} {cu} | {bench_icon} | {sg_icon} |\n"

        md += "\n## Install\n\n"
        if scored:
            best = scored[0][0]
            md += f"```bash\ncoreai-catalog install {best['id']}\n```\n"

        md += "\n## Related\n\n"
        md += f"- [Compare all {cap.replace('-', ' ')} models](../compare/{slug}.md)\n"
        md += f"- [Search by this capability](../../catalog.yaml) — `coreai-catalog search --capability {cap}`\n"

        (docs_tasks / f"{slug}.md").write_text(md)
        pages += 1

    # Generate index
    index_lines = ["# Task Pages\n", "Browse models by capability.\n"]
    for cap in sorted(cap_models.keys()):
        slug = _capability_slug(cap)
        count = len(cap_models[cap])
        index_lines.append(f"- [{cap.replace('-', ' ').title()}](./{slug}.md) — {count} models")
    (docs_tasks / "README.md").write_text("\n".join(index_lines) + "\n")

    return pages


def export_task_json(catalog_root: Path, dist: Path | None = None) -> int:
    """Generate dist/tasks/{task}.json for each TASK_MAP entry.

    Returns number of task JSONs generated.
    """
    dist = dist or catalog_root / "dist"
    tasks_dir = dist / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    cat = Catalog(catalog_root)
    catalog_version = _get_catalog_version(catalog_root)

    # Build task → models mapping
    task_index = []
    for task_syn, caps in sorted(TASK_MAP.items()):
        slug = task_syn.replace(" ", "-").replace("/", "-")
        matching = []
        for m in cat.models:
            model_caps = {c.lower() for c in m.get("capabilities", [])}
            if model_caps & {c.lower() for c in caps}:
                matching.append(m)

        scored = [(m, cat.readiness_score(m)) for m in matching]
        scored.sort(key=lambda x: (-x[1], x[0]["id"]))

        models_data = []
        for m, score in scored:
            ds = m.get("device_support", {})
            models_data.append({
                "id": m["id"],
                "name": m["name"],
                "score": score,
                "parameters": m.get("size", {}).get("parameters"),
                "devices": {
                    "iphone": ds.get("iphone") is True,
                    "ipad": ds.get("ipad") is True,
                    "mac": ds.get("mac") is True,
                },
                "license": m.get("license", {}).get("name"),
                "commercial_use": m.get("license", {}).get("commercial_use"),
                "has_benchmark": bool(cat.get_benchmarks(m["id"])),
            })

        task_data = {
            "task": task_syn,
            "capabilities": caps,
            "model_count": len(matching),
            "models": models_data,
            "export_schema_version": EXPORT_SCHEMA_VERSION,
            "export_catalog_version": catalog_version,
        }

        # Add "best" picks
        if models_data:
            task_data["best_overall"] = models_data[0]["id"]
            iphone = [m for m in models_data if m["devices"]["iphone"]]
            task_data["best_iphone"] = iphone[0]["id"] if iphone else None
            commercial = [m for m in models_data if m["commercial_use"] == "likely"]
            task_data["best_commercial"] = commercial[0]["id"] if commercial else None

        (tasks_dir / f"{slug}.json").write_text(
            json.dumps(task_data, indent=2, ensure_ascii=False) + "\n"
        )

        task_index.append({
            "task": task_syn,
            "slug": slug,
            "capabilities": caps,
            "model_count": len(matching),
        })

    # Write index
    (tasks_dir / "index.json").write_text(
        json.dumps({
            "task_count": len(task_index),
            "tasks": task_index,
            "export_schema_version": EXPORT_SCHEMA_VERSION,
            "export_catalog_version": catalog_version,
        }, indent=2, ensure_ascii=False) + "\n"
    )

    return len(task_index)
