#!/usr/bin/env python3
"""Source Monitor: detect new Core AI models from upstream sources.

Checks Hugging Face accounts and GitHub repos for new Core AI artifacts
not yet in the catalog. Outputs a structured report for human review.

Usage:
    python scripts/source_monitor.py                    # full scan
    python scripts/source_monitor.py --json             # JSON output
    python scripts/source_monitor.py --since 24h        # lookback period

This script is designed to run via GitHub Actions (source-monitor.yml)
every 3 hours. It creates a GitHub Issue when new models are detected.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ── Config ──

HF_ACCOUNTS = [
    "mlboydaisuke",
    "CarstenL",
    "Intiser",
    "warshanks",
    "bryanbblewis11",
    "lenitas",
]

GH_REPOS = [
    "john-rocky/coreai-model-zoo",
    "apple/coreai-models",
]

HF_UPSTREAM_ORGS = [
    "Qwen", "google", "openai", "mistralai",
    "ibm-granite", "LiquidAI", "openbmb",
    "black-forest-labs",
]


def load_catalog_ids() -> set[str]:
    """Load existing model IDs from catalog.yaml."""
    import yaml
    catalog_path = ROOT / "catalog.yaml"
    if not catalog_path.exists():
        return set()
    data = yaml.safe_load(catalog_path.read_text()) or {}
    return {m["id"] for m in data.get("models", []) if "id" in m}


def load_catalog_hf_repos() -> set[str]:
    """Load known HF repo names from artifacts.yaml."""
    import yaml
    artifacts_path = ROOT / "artifacts.yaml"
    if not artifacts_path.exists():
        return set()
    data = yaml.safe_load(artifacts_path.read_text()) or {}
    repos = set()
    for a in data.get("artifacts", []):
        hf = a.get("huggingface", {})
        owner = hf.get("owner", "")
        repo = hf.get("repo", "")
        if owner and repo:
            repos.add(f"{owner}/{repo}".lower())
            repos.add(repo.lower())
    return repos


def fetch_json(url: str, timeout: int = 15) -> list | dict | None:
    """Fetch JSON from a URL with error handling."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def check_hf_account(account: str, known_repos: set[str], since: str | None = None) -> list[dict]:
    """Check a HuggingFace account for new models.

    Returns list of {repo, name, lastModified, is_new} dicts.
    """
    url = f"https://huggingface.co/api/models?author={account}&sort=lastModified&direction=-1&limit=50"
    data = fetch_json(url)
    if not data or not isinstance(data, list):
        return []

    results = []
    for m in data:
        repo_full = m.get("id", "")  # e.g. "mlboydaisuke/qwen3-4b-CoreAI-official"
        repo_short = repo_full.replace(f"{account}/", "")
        last_mod = m.get("lastModified", "")[:10]

        # Filter by date if specified
        if since and last_mod < since:
            continue

        is_new = repo_short.lower() not in known_repos and repo_full.lower() not in known_repos

        results.append({
            "account": account,
            "repo": repo_full,
            "repo_short": repo_short,
            "last_modified": last_mod,
            "is_new": is_new,
            "url": f"https://huggingface.co/{repo_full}",
        })

    return results


def check_zoo_tree(known_ids: set[str]) -> dict:
    """Check coreai-model-zoo tree for new model directories."""
    tree_data = fetch_json(
        "https://api.github.com/repos/john-rocky/coreai-model-zoo/git/trees/main?recursive=1"
    )
    if not tree_data or "tree" not in tree_data:
        return {"count": 0, "new": []}

    paths = [t["path"] for t in tree_data.get("tree", [])]
    
    # Zoo models are in zoo/ directories with .md files
    # Official models are in official/ directories
    zoo_dirs = set()
    for p in paths:
        if p.startswith("zoo/") and p.endswith(".md") and "/" not in p[4:]:
            zoo_dirs.add(p[4:-3])  # Remove "zoo/" prefix and ".md" suffix
        elif p.startswith("official/") and p.endswith("/"):
            zoo_dirs.add(p[9:-1])  # Remove "official/" prefix and trailing "/"

    # Try to match against known IDs (fuzzy — names differ between zoo and catalog)
    new_dirs = []
    for d in sorted(zoo_dirs):
        # Normalize for comparison
        d_lower = d.lower().replace("-", "").replace("_", "").replace(".", "")
        matched = False
        for kid in known_ids:
            kid_lower = kid.lower().replace("-", "").replace("_", "").replace(".", "")
            if d_lower in kid_lower or kid_lower in d_lower:
                matched = True
                break
        if not matched:
            new_dirs.append(d)

    return {
        "total_in_zoo": len(zoo_dirs),
        "total_in_catalog": len(known_ids),
        "new": new_dirs,
    }


def classify_model(repo_short: str) -> dict:
    """Classify a model by its repo name into catalog fields.

    Uses naming patterns to infer runner, capabilities, and suggested ID.
    """
    name_lower = repo_short.lower()

    # Infer runner
    if "CoreAI-official" in repo_short or "coreai-official" in name_lower:
        runner = "stock-runner"
        source_group = "official"
    elif "CoreAI" in repo_short:
        runner = "CoreAIRunner"
        source_group = "zoo"
    elif "LiteRT" in repo_short or "litert" in name_lower:
        runner = "CoreAIKit-GraphModel"
        source_group = "external"
    else:
        runner = "CoreAIRunner"
        source_group = "zoo"

    # Infer capabilities from name
    caps = []
    if any(x in name_lower for x in ["whisper", "parakeet", "asr", "speech-to-text"]):
        caps.append("speech-to-text")
    if any(x in name_lower for x in ["tts", "vibevoice", "voxcpm", "kokoro", "matcha"]):
        caps.append("text-to-speech")
    if any(x in name_lower for x in ["vl", "vlm", "vision", "minicpm-v", "holo"]):
        caps.append("vision-language")
    if any(x in name_lower for x in ["chat", "llm", "instruct", "qwen", "gemma", "mistral", "granite", "lfm"]):
        if "speech-to-text" not in caps and "text-to-speech" not in caps:
            caps.append("chat")
            caps.append("text-generation")
    if any(x in name_lower for x in ["yolox", "rf-detr", "detr"]):
        caps.append("object-detection")
    if any(x in name_lower for x in ["sam", "segment"]):
        caps.append("promptable-segmentation")
    if any(x in name_lower for x in ["depth", "metric3d"]):
        caps.append("monocular-depth")
    if any(x in name_lower for x in ["flux", "z-image", "stable-diffusion"]):
        caps.append("image-generation")
    if any(x in name_lower for x in ["embed", "colmodernvbert", "siglip", "clip"]):
        caps.append("embedding")
    if any(x in name_lower for x in ["ocr", "unlimited"]):
        caps.append("document-ocr")
    if any(x in name_lower for x in ["audio", "stable-audio", "music"]):
        caps.append("text-to-audio")
    if any(x in name_lower for x in ["video", "ltx"]):
        caps.append("text-to-video")
    if any(x in name_lower for x in ["vla", "bitvla"]):
        caps.append("vision-language-action")

    if not caps:
        caps = ["unknown"]

    # Suggest a catalog ID
    suggested_id = name_lower
    suggested_id = re.sub(r'-coreai-official$', '', suggested_id)
    suggested_id = re.sub(r'-coreai$', '', suggested_id)
    suggested_id = re.sub(r'-litert$', '', suggested_id)
    suggested_id = re.sub(r'[^a-z0-9-]', '-', suggested_id)
    suggested_id = re.sub(r'-+', '-', suggested_id).strip('-')

    return {
        "suggested_id": suggested_id,
        "runner": runner,
        "source_group": source_group,
        "capabilities": caps,
    }


def run_monitor(since_hours: int = 72) -> dict:
    """Run the full source monitor scan.

    Returns a structured report dict.
    """
    known_ids = load_catalog_ids()
    known_repos = load_catalog_hf_repos()

    since_date = None
    if since_hours > 0:
        since_date = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%Y-%m-%d")

    # Check HF accounts
    all_hf_models: list[dict] = []
    for account in HF_ACCOUNTS:
        models = check_hf_account(account, known_repos, since_date)
        all_hf_models.extend(models)

    # Classify new models
    new_models = [m for m in all_hf_models if m["is_new"]]
    for m in new_models:
        classification = classify_model(m["repo_short"])
        m.update(classification)

    # Check zoo tree
    zoo_status = check_zoo_tree(known_ids)

    return {
        "scan_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "since_date": since_date or "all-time",
        "catalog_count": len(known_ids),
        "hf_total_checked": len(all_hf_models),
        "hf_new_count": len(new_models),
        "new_models": new_models,
        "zoo_status": zoo_status,
    }


def format_report(report: dict) -> str:
    """Format the report as Markdown for GitHub Issue."""
    lines = [
        f"## Source Monitor Report",
        f"",
        f"**Scan time:** {report['scan_time']}",
        f"**Catalog:** {report['catalog_count']} models",
        f"**Checked:** {report['hf_total_checked']} HF artifacts",
        f"**New:** {report['hf_new_count']} not in catalog",
        f"",
    ]

    if report["new_models"]:
        lines.append("### New Models Detected")
        lines.append("")
        for m in report["new_models"]:
            icon = "🆕"
            lines.append(f"#### {icon} {m['repo_short']}")
            lines.append(f"- **HF:** {m['url']}")
            lines.append(f"- **Modified:** {m['last_modified']}")
            lines.append(f"- **Suggested ID:** `{m['suggested_id']}`")
            lines.append(f"- **Runner:** `{m['runner']}`")
            lines.append(f"- **Source group:** `{m['source_group']}`")
            lines.append(f"- **Capabilities:** {', '.join(m['capabilities'])}")
            lines.append("")
    else:
        lines.append("No new models detected. ✅")
        lines.append("")

    zoo = report["zoo_status"]
    if zoo.get("new"):
        lines.append(f"### Zoo Directory: {len(zoo['new'])} potentially new models")
        lines.append(f"Zoo has {zoo['total_in_zoo']} dirs vs catalog's {zoo['total_in_catalog']} models")
        for d in zoo["new"][:10]:
            lines.append(f"- {d}")
        if len(zoo["new"]) > 10:
            lines.append(f"- ... and {len(zoo['new']) - 10} more")
        lines.append("")

    lines.append("---")
    lines.append("Review findings and update `catalog.yaml` if new models are confirmed.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Source Monitor — detect new Core AI models")
    parser.add_argument("--since", type=int, default=72, help="Lookback hours (default: 72)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()

    report = run_monitor(since_hours=args.since)

    if args.json or args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_report(report))

    # Exit non-zero if new models found (for CI integration)
    if report["hf_new_count"] > 0:
        return 1  # Signal: new models need review

    return 0


if __name__ == "__main__":
    sys.exit(main())
