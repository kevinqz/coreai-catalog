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


# Any HuggingFace repo URL — owner/repo, tolerating dots/dashes in both.
HF_URL_RE = re.compile(r"https://huggingface\.co/([\w.\-]+/[\w.\-]+)")


def extract_hf_repos(text: str) -> set[str]:
    """Return the bare repo names (owner prefix stripped) for every HuggingFace
    URL anywhere in the text. Decoupled from row parsing so multi-artifact rows
    (e.g. Qwen3-VL 2B/4B/8B on one line) contribute *all* their repos to the
    upstream set, not just the first."""
    return {owner_repo.split("/", 1)[-1] for owner_repo in HF_URL_RE.findall(text)}


def parse_zoo_readme(readme: str) -> dict[str, dict]:
    """Parse the model table rows from the zoo README."""
    models: dict[str, dict] = {}
    # Match table rows. The model name is bold and may itself be a markdown link:
    #   | **Model Name** (description) | [🤗 repo](url) | ... |
    #   | [**Model Name**](zoo/x.md) (description) | [🤗 repo](url) | ... |
    # The optional `\[?` + `(?:\]\([^)]*\))?` accepts the linked-name form; the
    # HF repo is the first huggingface.co URL after the name column.
    for line in readme.splitlines():
        m = re.match(
            r"\|\s*\[?\*\*(.+?)\*\*(?:\]\([^)]*\))?\s*(.*?)\s*\|"
            r"[^|]*?\((https://huggingface\.co/[^)]+?)\)",
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


def hf_repo_live(owner_repo: str, *, _opener=urllib.request.urlopen) -> bool:
    """Whether a HuggingFace repo still exists. Only a definitive 404 counts as
    gone; 401 (gated/private), other HTTP codes, and network errors all count as
    live so a transient failure never false-flags a removal. `_opener` is
    injectable for tests."""
    url = f"https://huggingface.co/api/models/{owner_repo}"
    try:
        with _opener(url, timeout=30):
            return True
    except HTTPError as e:
        return e.code != 404
    except Exception:
        return True


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
    artifact_hf_full_by_id: dict[str, str] = {}
    for a in our_artifacts.get("artifacts", []):
        hf = a.get("huggingface", {}) or {}
        repo = hf.get("repo", "")
        if repo:
            our_hf_repos.add(repo)
            artifact_hf_repo_by_id[a["id"]] = repo
            owner = hf.get("owner", "")
            artifact_hf_full_by_id[a["id"]] = f"{owner}/{repo}" if owner else repo

    report: dict = {
        "missing_from_catalog": [],
        "removed_from_upstream": [],
        "in_catalog_not_in_readme": [],
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

        # Feed the removal-detection set from *every* HF URL in the README, so
        # multi-artifact rows and any format the row parser misses still count.
        upstream_repos |= extract_hf_repos(zoo_readme)

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
        upstream_repos |= extract_hf_repos(official_readme)
        for info in parse_official_readme(official_readme).values():
            upstream_repos.add(info["hf_repo"].split("/", 1)[-1])
    except Exception as e:
        report["official_fetch_error"] = str(e)

    # ── 2. Removed-from-upstream detection (only when the fetch worked) ──
    if zoo_fetch_ok:
        candidates = compute_removed(
            catalog.get("models", []), artifact_hf_repo_by_id, upstream_repos
        )
        # README-absence alone is weak: confirm each candidate's HF artifact is
        # actually gone (404) before calling it a removal. Live-but-untabled
        # models (indexed from a conversion script, Apple's repo, or a prose
        # mention) are reported separately and do NOT trip the regression exit.
        removed, untabled = [], []
        for m in candidates:
            full = artifact_hf_full_by_id.get(m["artifact_id"], m["hf_repo"])
            (removed if not hf_repo_live(full) else untabled).append(m)
        report["removed_from_upstream"] = removed
        report["in_catalog_not_in_readme"] = untabled
        if removed:
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

        if report.get("in_catalog_not_in_readme"):
            print(
                f"\nℹ️  In catalog, not in a README table but HF artifact still live "
                f"({len(report['in_catalog_not_in_readme'])}) — indexed from a conversion "
                f"script / Apple repo / prose mention, not a regression:"
            )
            for m in report["in_catalog_not_in_readme"]:
                print(f"  → {m['model_id']} (HF repo {m['hf_repo']})")

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
