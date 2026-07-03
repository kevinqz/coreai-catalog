#!/usr/bin/env python3
"""
Upstream synchronization scanner.

Fetches the john-rocky/coreai-model-zoo README (zoo + official) and Hugging
Face model list, then diffs them against our catalog to report:
  - Models in upstream but missing from catalog
  - Models in catalog but no longer in upstream (removed_from_upstream)
  - HF CoreAI artifacts without catalog entries
  - Benchmark gaps (models without benchmarks)

Output: a structured report to stdout (JSON if --json flag is passed).

Exit codes:
  0 = no availability regressions (informational gaps may still be listed)
  1 = regression: catalog models vanished from upstream, or the zoo README
      itself is gone (HTTP 4xx)

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
from urllib.error import HTTPError
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

ZOO_README_URL = "https://raw.githubusercontent.com/john-rocky/coreai-model-zoo/main/README.md"
OFFICIAL_README_URL = "https://raw.githubusercontent.com/john-rocky/coreai-model-zoo/main/official/README.md"

# If the upstream READMEs parse to fewer models than this, assume the table
# format changed (or the fetch was truncated) and skip removal detection
# rather than flagging the whole catalog as removed.
MIN_UPSTREAM_PARSE = 5


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


def repo_matches(repo: str, candidates: set[str]) -> bool:
    """Fuzzy repo-name match (substring either way, case-insensitive)."""
    repo_l = repo.lower()
    for cand in candidates:
        cand_l = cand.lower()
        if repo_l in cand_l or cand_l in repo_l:
            return True
    return False


def compute_removed(
    catalog_models: list[dict],
    artifact_hf_repo_by_id: dict[str, str],
    upstream_repos: set[str],
) -> list[dict]:
    """Return catalog models (source_group zoo/official) whose HF artifact
    repo no longer appears in the upstream READMEs.

    upstream_repos are bare repo names (owner prefix stripped). Returns an
    empty list when the parsed upstream set is implausibly small (parse
    failure guard) so a README format change cannot flag the whole catalog.
    """
    if len(upstream_repos) < MIN_UPSTREAM_PARSE:
        return []
    removed: list[dict] = []
    for model in catalog_models:
        if model.get("source_group") not in ("zoo", "official"):
            continue
        artifact_ref = model.get("artifact_ref", "")
        hf_repo = artifact_hf_repo_by_id.get(artifact_ref, "")
        if not hf_repo:
            continue
        if not repo_matches(hf_repo, upstream_repos):
            removed.append(
                {
                    "model_id": model["id"],
                    "artifact_id": artifact_ref,
                    "hf_repo": hf_repo,
                    "reason": "no longer listed in upstream zoo/official README",
                }
            )
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan upstream for catalog gaps")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    # Load our catalog
    catalog = read_yaml(ROOT / "catalog.yaml")
    our_artifacts = read_yaml(ROOT / "artifacts.yaml")

    our_hf_repos: set[str] = set()
    artifact_hf_repo_by_id: dict[str, str] = {}
    for a in our_artifacts.get("artifacts", []):
        repo = (a.get("huggingface", {}) or {}).get("repo", "")
        if repo:
            our_hf_repos.add(repo)
            artifact_hf_repo_by_id[a["id"]] = repo

    report: dict = {
        "missing_from_catalog": [],
        "removed_from_upstream": [],
        "unbenchmarked_models": [],
        "hf_artifacts_without_entries": [],
    }
    regression = False

    # ── 1. Fetch zoo + official READMEs ──
    upstream_repos: set[str] = set()
    zoo_fetch_ok = False
    try:
        zoo_readme = fetch_text(ZOO_README_URL)
        zoo_models = parse_zoo_readme(zoo_readme)
        zoo_fetch_ok = True

        for name, info in zoo_models.items():
            hf_repo = info["hf_repo"].replace("mlboydaisuke/", "")
            upstream_repos.add(hf_repo)
            # Check if this repo is in our catalog (fuzzy match)
            if not repo_matches(hf_repo, our_hf_repos):
                report["missing_from_catalog"].append(
                    {"name": name, "hf_repo": info["hf_repo"], "desc": info.get("desc", "")[:80]}
                )
    except HTTPError as e:
        report["zoo_fetch_error"] = str(e)
        if 400 <= e.code < 500:
            # The zoo README itself is gone/moved — that IS the regression.
            regression = True
    except Exception as e:
        report["zoo_fetch_error"] = str(e)

    try:
        official_readme = fetch_text(OFFICIAL_README_URL)
        for info in parse_official_readme(official_readme).values():
            upstream_repos.add(info["hf_repo"].split("/", 1)[-1])
    except Exception as e:
        report["official_fetch_error"] = str(e)

    # ── 2. Removed-from-upstream detection (only when the fetch worked) ──
    if zoo_fetch_ok:
        report["removed_from_upstream"] = compute_removed(
            catalog.get("models", []), artifact_hf_repo_by_id, upstream_repos
        )
        if report["removed_from_upstream"]:
            regression = True

    # ── 3. Fetch HF CoreAI artifacts (all owners, not just mlboydaisuke) ──
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
            if not repo_matches(repo, our_hf_repos):
                report["hf_artifacts_without_entries"].append(repo)
    except Exception as e:
        report["hf_fetch_error"] = str(e)

    # ── 4. Benchmark coverage ──
    # benchmarks.jsonl is the single benchmark source of truth
    benched_ids: set[str] = set()
    bench_path = ROOT / "benchmarks.jsonl"
    if bench_path.exists():
        for line in bench_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            benched_ids.add(json.loads(line).get("model_id", ""))
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

        if report.get("zoo_fetch_error"):
            print(f"\n⚠️  Zoo README fetch failed: {report['zoo_fetch_error']}")

        if report["removed_from_upstream"]:
            print(f"\n🚨 Catalog models REMOVED from upstream ({len(report['removed_from_upstream'])}):")
            for m in report["removed_from_upstream"]:
                print(f"  → {m['model_id']} (artifact {m['artifact_id']}, HF repo {m['hf_repo']})")
        elif zoo_fetch_ok:
            print("\n✅ No catalog models removed from upstream")

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

        if regression:
            print("\n❌ Availability regression detected (exit 1)")

    return 1 if regression else 0


if __name__ == "__main__":
    sys.exit(main())
