#!/usr/bin/env python3
"""
Core AI Catalog — io_contract bootstrapper (redteam findings C1/C2/C5/C6/C7).

For every artifact in artifacts.yaml this script:
  1. lists the Hugging Face repo file tree via the HF API (pinned to the
     catalog's ``huggingface.revision`` when one is recorded),
  2. locates the ``.aimodel`` bundle's SMALL metadata files — the bundle-level
     ``metadata.json`` (the file ``ModelBundle`` in apple/coreai-models
     swift/Sources/CoreAIShared/Bundle/ModelBundle.swift:121-144 actually
     parses: a bundle is a *directory* with metadata.json + assets +
     tokenizer), plus config-like companions (config.json, recipe.json,
     tokenizer_config.json, preprocessor_config.json, generation_config.json),
  3. downloads ONLY those small files (hard per-file and total size caps —
     never weights, never tokenizer.json/vocab blobs),
  4. emits a JSON report of the typed-IO metadata the real bundles carry, so
     authored ``io_contract`` blocks in catalog.yaml can be grounded in the
     bytes actually served, not guessed.

Requires ``huggingface_hub`` (run inside a venv):
  python -m venv /tmp/venv && /tmp/venv/bin/pip install huggingface_hub
  /tmp/venv/bin/python scripts/bootstrap_io_contracts.py --out report.json

401/404 repos (e.g. the known-gated yolox-s) are tolerated and reported.
This tool is read-only with respect to the catalog: it never edits YAML.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

#: Basenames worth downloading — small, structured, IO-relevant.
METADATA_BASENAMES = {
    "metadata.json",
    "config.json",
    "recipe.json",
    "generation_config.json",
    "preprocessor_config.json",
    "processor_config.json",
    "tokenizer_config.json",
    "pipeline.json",
    "model_index.json",
}

#: Never download anything bigger than this (bytes). Weights are GBs;
#: bundle metadata is bytes-to-KBs. tokenizer_config.json tops out ~200KB.
MAX_FILE_BYTES = 1_000_000
#: Global download budget across the whole run (bytes).
MAX_TOTAL_BYTES = 100_000_000
#: Per-repo cap so one strangely-shaped repo can't eat the budget.
MAX_FILES_PER_REPO = 24


def load_artifacts(root: Path) -> list[dict]:
    data = yaml.safe_load((root / "artifacts.yaml").read_text()) or {}
    return data.get("artifacts", [])


def classify_tree(paths: dict[str, int | None]) -> dict:
    """Summarize a repo file tree: bundle dirs, metadata files, tokenizers.

    *paths* maps repo path → size (None for directories).
    """
    aimodel_dirs = sorted(
        p for p, size in paths.items()
        if size is None and (p.endswith(".aimodel") or p.endswith(".aimodelc"))
    )
    metadata_files = sorted(
        p for p, size in paths.items()
        if size is not None and Path(p).name in METADATA_BASENAMES
    )
    # Bundle-level metadata.json = a metadata.json NOT inside a .aimodel dir
    # (each compiled .aimodel asset carries its own tiny internal one).
    bundle_metadata = [
        p for p in metadata_files
        if Path(p).name == "metadata.json" and ".aimodel" not in str(Path(p).parent)
    ]
    tokenizer_dirs = sorted({
        str(Path(p).parent) for p in paths
        if Path(p).name == "tokenizer.json"
    })
    return {
        "aimodel_dirs": aimodel_dirs,
        "metadata_files": metadata_files,
        "bundle_metadata_files": bundle_metadata,
        "tokenizer_dirs": tokenizer_dirs,
        "file_count": sum(1 for s in paths.values() if s is not None),
    }


def pick_downloads(paths: dict[str, int | None]) -> list[str]:
    """Pick the small metadata files worth downloading, honoring size caps."""
    picks: list[str] = []
    for p, size in sorted(paths.items()):
        if size is None or size > MAX_FILE_BYTES:
            continue
        if Path(p).name in METADATA_BASENAMES:
            picks.append(p)
        if len(picks) >= MAX_FILES_PER_REPO:
            break
    return picks


def summarize_json(path: Path) -> dict | list | str | None:
    """Parse a downloaded JSON file; long dicts are trimmed to IO-relevant keys."""
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if isinstance(data, dict) and len(json.dumps(data)) > 4000:
        keep = {
            k: v for k, v in data.items()
            if not isinstance(v, (dict, list)) or len(json.dumps(v)) < 800
        }
        keep["_trimmed_keys"] = sorted(set(data) - set(keep))
        return keep
    return data


def inspect_repo(api, repo_id: str, revision: str | None, tmp: Path,
                 budget: dict) -> dict:
    """List one repo's tree, download its small metadata files, summarize."""
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import (
        EntryNotFoundError,
        GatedRepoError,
        HfHubHTTPError,
        RepositoryNotFoundError,
        RevisionNotFoundError,
    )

    result: dict = {"repo": repo_id, "revision": revision, "status": "ok"}
    try:
        tree = list(api.list_repo_tree(repo_id, recursive=True, revision=revision))
    except (RepositoryNotFoundError, RevisionNotFoundError) as exc:
        result["status"] = "not_found"
        result["error"] = str(exc).splitlines()[0][:200]
        return result
    except GatedRepoError as exc:
        result["status"] = "gated"
        result["error"] = str(exc).splitlines()[0][:200]
        return result
    except HfHubHTTPError as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        result["status"] = {401: "unauthorized", 403: "forbidden",
                            404: "not_found"}.get(code, "http_error")
        result["error"] = str(exc).splitlines()[0][:200]
        return result

    paths = {f.path: getattr(f, "size", None) for f in tree}
    result["tree"] = classify_tree(paths)

    downloaded: dict[str, object] = {}
    for rel in pick_downloads(paths):
        size = paths.get(rel) or 0
        if budget["used"] + size > MAX_TOTAL_BYTES:
            result.setdefault("skipped_budget", []).append(rel)
            continue
        try:
            local = hf_hub_download(
                repo_id, rel, revision=revision, cache_dir=str(tmp),
            )
        except (EntryNotFoundError, GatedRepoError, HfHubHTTPError, OSError) as exc:
            downloaded[rel] = {"error": str(exc).splitlines()[0][:200]}
            continue
        budget["used"] += size
        downloaded[rel] = summarize_json(Path(local))
    result["metadata"] = downloaded
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ground io_contract authoring in real .aimodel bundle metadata.",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Write the full JSON report to this path (default: stdout summary only)",
    )
    parser.add_argument(
        "--only", nargs="*", default=None,
        help="Restrict to these artifact ids (default: all artifacts)",
    )
    parser.add_argument(
        "--root", type=Path, default=ROOT,
        help="Catalog root containing artifacts.yaml (default: repo root)",
    )
    args = parser.parse_args(argv)

    try:
        from huggingface_hub import HfApi
    except ImportError:
        print(
            "error: huggingface_hub is required. Create a venv and run:\n"
            "  pip install huggingface_hub",
            file=sys.stderr,
        )
        return 2

    artifacts = load_artifacts(args.root)
    if args.only:
        wanted = set(args.only)
        artifacts = [a for a in artifacts if a.get("id") in wanted]

    api = HfApi()
    budget = {"used": 0}
    tmp = Path(tempfile.mkdtemp(prefix="ioc-bootstrap-"))
    reports: list[dict] = []
    try:
        for art in artifacts:
            hf = art.get("huggingface", {}) or {}
            owner, repo = hf.get("owner", ""), hf.get("repo", "")
            if not owner or not repo:
                reports.append({
                    "id": art.get("id"), "status": "no_huggingface_block",
                })
                continue
            entry = inspect_repo(
                api, f"{owner}/{repo}", hf.get("revision"), tmp, budget,
            )
            entry["id"] = art.get("id")
            reports.append(entry)
            tree = entry.get("tree", {})
            print(
                f"{entry['id']}: {entry['status']}"
                + (
                    f" — {len(tree.get('aimodel_dirs', []))} .aimodel dir(s), "
                    f"{len(tree.get('bundle_metadata_files', []))} bundle metadata.json, "
                    f"{len(entry.get('metadata', {}))} metadata file(s) fetched"
                    if entry["status"] == "ok" else ""
                )
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    ok = sum(1 for r in reports if r.get("status") == "ok")
    with_bundle_meta = sum(
        1 for r in reports
        if r.get("tree", {}).get("bundle_metadata_files")
    )
    summary = {
        "artifacts_total": len(reports),
        "listed_ok": ok,
        "unreachable": [
            {"id": r.get("id"), "status": r.get("status")}
            for r in reports if r.get("status") not in ("ok",)
        ],
        "with_bundle_metadata_json": with_bundle_meta,
        "download_bytes_used": budget["used"],
    }
    print(json.dumps(summary, indent=2))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(
            {"summary": summary, "artifacts": reports},
            indent=2, ensure_ascii=False,
        ) + "\n")
        print(f"report written: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
