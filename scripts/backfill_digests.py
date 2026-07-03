#!/usr/bin/env python3
"""
Backfill Hugging Face revision pins and per-file sha256 digests into
``artifacts.yaml`` — WITHOUT downloading any weights.

For every artifact with a ``huggingface`` block, queries the public HF API:

    https://huggingface.co/api/models/{owner}/{repo}?blobs=true

and records:
  - ``huggingface.revision``  — the repo's current commit SHA (``sha`` field)
  - ``huggingface.files``     — ``[{path, sha256, size_bytes}]`` for every file
                                the API can attest (LFS blobs expose sha256
                                OIDs; non-LFS files only carry git-sha1 blob
                                ids and are therefore NOT recorded — this
                                script never fabricates a digest)

Resilient by design:
  - Rate-limit friendly: sleeps between requests (``--sleep``, default 0.5s).
  - 404s / timeouts / network errors are logged and the artifact is left
    untouched (fields stay absent — absence is honest, fabrication is not).
  - Idempotent: artifacts that already carry ``revision`` + ``files`` are
    skipped unless ``--refresh`` is passed.

Exit code 0 unless artifacts.yaml itself is unreadable.

Usage:
  python scripts/backfill_digests.py
  python scripts/backfill_digests.py --refresh
  python scripts/backfill_digests.py --only whisper-large-v3-turbo-carstenl
  python scripts/backfill_digests.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_PATH = ROOT / "artifacts.yaml"

API_URL = "https://huggingface.co/api/models/{owner}/{repo}?blobs=true"
USER_AGENT = "coreai-catalog/backfill_digests (https://github.com/kevinqz/coreai-catalog)"


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def fetch_model_info(owner: str, repo: str, timeout: int = 30) -> dict | None:
    """Fetch HF model metadata (with blob info). Returns None on any failure."""
    url = API_URL.format(owner=owner, repo=repo)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"    ⚠️  HTTP {e.code} for {owner}/{repo} — leaving fields absent")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"    ⚠️  Network error for {owner}/{repo}: {e} — leaving fields absent")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"    ⚠️  Unparseable API response for {owner}/{repo}: {e}")
    return None


def parse_hf_model_info(data: dict) -> tuple[str | None, list[dict]]:
    """Extract (revision, files) from an HF ``?blobs=true`` API response.

    Only LFS blobs carry an attestable sha256 OID; other files are omitted.
    Never invents values: a missing/malformed field yields absence.
    """
    revision = data.get("sha")
    if not isinstance(revision, str) or not revision:
        revision = None

    files: list[dict] = []
    for sibling in data.get("siblings") or []:
        if not isinstance(sibling, dict):
            continue
        path = sibling.get("rfilename")
        lfs = sibling.get("lfs")
        if not path or not isinstance(lfs, dict):
            continue
        sha256 = lfs.get("sha256")
        size_bytes = lfs.get("size")
        if not isinstance(sha256, str) or not isinstance(size_bytes, int):
            continue
        files.append({
            "path": path,
            "sha256": sha256,
            "size_bytes": size_bytes,
        })
    return revision, files


def backfill(
    artifacts_path: Path = ARTIFACTS_PATH,
    refresh: bool = False,
    only: str | None = None,
    sleep_s: float = 0.5,
    dry_run: bool = False,
) -> dict:
    """Backfill revision + digests. Returns a summary dict of counters."""
    data = read_yaml(artifacts_path)
    artifacts = data.get("artifacts", [])

    summary = {"filled": 0, "already": 0, "no_hf": 0, "failed": 0, "no_lfs": 0}

    for artifact in artifacts:
        artifact_id = artifact.get("id", "<missing id>")
        if only and artifact_id != only:
            continue

        hf = artifact.get("huggingface") or {}
        owner, repo = hf.get("owner"), hf.get("repo")
        if not owner or not repo:
            summary["no_hf"] += 1
            continue

        if hf.get("revision") and hf.get("files") and not refresh:
            summary["already"] += 1
            continue

        print(f"  {artifact_id}: querying {owner}/{repo} ...")
        info = fetch_model_info(owner, repo)
        time.sleep(sleep_s)
        if info is None:
            summary["failed"] += 1
            continue

        revision, files = parse_hf_model_info(info)
        if revision is None:
            print(f"    ⚠️  No 'sha' in API response for {owner}/{repo} — skipping")
            summary["failed"] += 1
            continue

        hf["revision"] = revision
        if files:
            hf["files"] = files
        else:
            # No LFS blobs → no attestable digests; leave 'files' absent.
            summary["no_lfs"] += 1
        summary["filled"] += 1
        print(f"    ✅ revision {revision[:12]}, {len(files)} attested file(s)")

    if not dry_run:
        artifacts_path.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False,
                      allow_unicode=True)
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill HF revision + sha256 digests into artifacts.yaml"
    )
    parser.add_argument("--refresh", action="store_true",
                        help="Re-query artifacts that already have revision+files")
    parser.add_argument("--only", metavar="ARTIFACT_ID",
                        help="Backfill a single artifact by id")
    parser.add_argument("--sleep", type=float, default=0.5, metavar="SECONDS",
                        help="Delay between API requests (default: 0.5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Query and report, but do not write artifacts.yaml")
    args = parser.parse_args()

    if not ARTIFACTS_PATH.exists():
        print(f"artifacts.yaml not found at {ARTIFACTS_PATH}")
        return 1

    summary = backfill(
        refresh=args.refresh,
        only=args.only,
        sleep_s=args.sleep,
        dry_run=args.dry_run,
    )

    print("\nBackfill summary:")
    print(f"  filled (revision written):    {summary['filled']}")
    print(f"    ...of which no LFS digests: {summary['no_lfs']}")
    print(f"  skipped (already filled):     {summary['already']}")
    print(f"  skipped (no huggingface):     {summary['no_hf']}")
    print(f"  failed (API error/timeout):   {summary['failed']}")
    if args.dry_run:
        print("  (dry run — artifacts.yaml not written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
