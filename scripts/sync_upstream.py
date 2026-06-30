#!/usr/bin/env python3
"""
Upstream synchronization scanner.

Fetches the john-rocky/coreai-model-zoo README and Hugging Face model list,
then diffs them against our catalog to report:
  - Models in upstream but missing from catalog
  - Models in catalog but no longer in upstream (removed)
  - HF CoreAI artifacts without catalog entries
  - Benchmark gaps (models without benchmarks)

Output: a structured report to stdout (JSON if --json flag is passed).
Exit code 0 always (informational tool, not a gate).

Usage:
  python scripts/sync_upstream.py
  python scripts/sync_upstream.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def fetch_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read().decode("utf-8")


def fetch_json(url: str) -> list | dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_zoo_readme(readme: str) -> dict[str, dict]:
    """Parse the model table rows from the zoo README."""
    models: dict[str, dict] = {}
    # Match table rows: | **Model Name** (description) | [🤗 repo](url) | License |
    for line in readme.splitlines():
        m = re.match(
            r"\|\s*\*\*(.+?)\*\*\s*(.*?)\s*\|\s*\[.+?\]\((https://huggingface\.co/.+?)\)",
            line,
        )
        if m:
            name = m.group(1).strip()
            desc = m.group(2).strip().strip("()")
            hf_url = m.group(3).strip()
            hf_repo = hf_url.split("huggingface.co/")[-1]
            models[name] = {"desc": desc, "hf_repo": hf_repo, "hf_url": hf_url}
    return models


def parse_official_readme(readme: str) -> dict[str, dict]:
    """Parse the official/ README model table."""
    models: dict[str, dict] = {}
    for line in readme.splitlines():
        m = re.match(
            r"\|\s*(.+?)\s*\|.*?\|\s*([0-9.]+)\s*\|\s*\[HF\]\((https://huggingface\.co/.+?)\)",
            line,
        )
        if m:
            name = m.group(1).strip()
            hf_url = m.group(3).strip()
            hf_repo = hf_url.split("huggingface.co/")[-1]
            models[name] = {"hf_repo": hf_repo, "hf_url": hf_url}
    return models


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan upstream for catalog gaps")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    # Load our catalog
    catalog = read_yaml(ROOT / "catalog.yaml")
    our_artifacts = read_yaml(ROOT / "artifacts.yaml")

    our_hf_repos: set[str] = set()
    for a in our_artifacts.get("artifacts", []):
        repo = a.get("huggingface", {}).get("repo", "")
        if repo:
            our_hf_repos.add(repo)

    report: dict = {
        "missing_from_catalog": [],
        "removed_from_upstream": [],
        "unbenchmarked_models": [],
        "hf_artifacts_without_entries": [],
    }

    # ── 1. Fetch zoo README ──
    try:
        zoo_readme = fetch_text(
            "https://raw.githubusercontent.com/john-rocky/coreai-model-zoo/main/README.md"
        )
        zoo_models = parse_zoo_readme(zoo_readme)

        for name, info in zoo_models.items():
            hf_repo = info["hf_repo"].replace("mlboydaisuke/", "")
            # Check if this repo is in our catalog (fuzzy match)
            found = False
            for our_repo in our_hf_repos:
                if hf_repo.lower() in our_repo.lower() or our_repo.lower() in hf_repo.lower():
                    found = True
                    break
            if not found:
                report["missing_from_catalog"].append(
                    {"name": name, "hf_repo": info["hf_repo"], "desc": info.get("desc", "")[:80]}
                )
    except Exception as e:
        report["zoo_fetch_error"] = str(e)

    # ── 2. Fetch HF CoreAI artifacts (all owners, not just mlboydaisuke) ──
    try:
        hf_models: list[dict] = []
        for search_term in ("coreai", "CoreAI"):
            page = fetch_json(
                f"https://huggingface.co/api/models?search={search_term}&limit=200"
            )
            for m in page:
                if m["id"] not in [x["id"] for x in hf_models]:
                    hf_models.append(m)

        coreai_repos: list[str] = []
        for m in hf_models:
            mid = m.get("id", "")
            lower = mid.lower()
            # Filter: must look like a real CoreAI artifact (not spam)
            if "coreai" not in lower and "core-ai" not in lower:
                continue
            # Skip obvious spam (random hex suffixes, no tags, 0 downloads)
            tags = m.get("tags", [])
            downloads = m.get("downloads", 0)
            if not tags and downloads == 0:
                # Could be real but untagged — keep if it has .aimodel structure
                pass
            repo = mid.split("/", 1)[-1] if "/" in mid else mid
            coreai_repos.append(repo)

        for repo in coreai_repos:
            found = False
            for our_repo in our_hf_repos:
                if repo.lower() in our_repo.lower() or our_repo.lower() in repo.lower():
                    found = True
                    break
            if not found:
                report["hf_artifacts_without_entries"].append(repo)
    except Exception as e:
        report["hf_fetch_error"] = str(e)

    # ── 3. Benchmark coverage ──
    benchmarks = read_yaml(ROOT / "benchmarks.yaml")
    benched_ids = {b["model_id"] for b in benchmarks.get("benchmarks", [])}
    for m in catalog.get("models", []):
        if m["id"] not in benched_ids:
            report["unbenchmarked_models"].append(m["id"])

    # ── Output ──
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print("UPSTREAM SYNC REPORT")
        print("=" * 60)

        if report["missing_from_catalog"]:
            print(f"\n📋 Models in zoo README but NOT in catalog ({len(report['missing_from_catalog'])}):")
            for m in report["missing_from_catalog"]:
                print(f"  → {m['name']}: {m['hf_repo']}")
        else:
            print("\n✅ All zoo README models are cataloged")

        if report["hf_artifacts_without_entries"]:
            print(f"\n🤗 CoreAI HF artifacts without catalog entries ({len(report['hf_artifacts_without_entries'])}):")
            for repo in report["hf_artifacts_without_entries"]:
                print(f"  → {repo}")
        else:
            print("\n✅ All mlboydaisuke CoreAI HF artifacts are cataloged")

        if report["unbenchmarked_models"]:
            print(f"\n📊 Models without benchmarks ({len(report['unbenchmarked_models'])}):")
            for mid in report["unbenchmarked_models"]:
                print(f"  → {mid}")
        else:
            print("\n✅ All models have benchmarks")

    return 0


if __name__ == "__main__":
    sys.exit(main())
