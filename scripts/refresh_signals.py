#!/usr/bin/env python3
"""
Refresh the VOLATILE host-signal layer into dist/signals.json.

Per-artifact Hugging Face popularity/recency signals (downloads, likes,
lastModified, gated), keyed by artifact id, with an `as_of` timestamp.

This is deliberately SEPARATE from scripts/generate.py: those exports are the
deterministic, offline, source-grounded catalog. Popularity signals are
volatile and gameable, so they live in their own refreshable snapshot and are
used ONLY as a tiebreaker in the host-selection policy
(coreai_catalog.catalog.artifact_host_key). See
docs/concepts/multi-host-provenance.md.

Usage:
    python scripts/refresh_signals.py [YYYY-MM-DD]   # optional as_of override
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _fetch(owner: str, repo: str, timeout: float = 25.0) -> dict:
    url = f"https://huggingface.co/api/models/{owner}/{repo}"
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "coreai-catalog-signals"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    return {
        "downloads": data.get("downloads", 0) or 0,
        "likes": data.get("likes", 0) or 0,
        "last_modified": (data.get("lastModified") or "")[:10],
        "gated": data.get("gated", False),
    }


def main(as_of: str | None = None) -> int:
    artifacts = yaml.safe_load((ROOT / "artifacts.yaml").read_text())["artifacts"]
    signals: dict[str, dict] = {}
    for artifact in artifacts:
        hf = artifact.get("huggingface") or {}
        owner, repo = hf.get("owner"), hf.get("repo")
        if not (owner and repo):
            continue
        try:
            signals[artifact["id"]] = _fetch(owner, repo)
        except Exception as exc:  # network is best-effort; record the failure
            signals[artifact["id"]] = {"error": str(exc)}
    out = {
        "as_of": as_of or date.today().isoformat(),
        "source": "huggingface.co/api/models",
        "note": "Volatile popularity/recency signals — tiebreaker only, not source-grounded truth.",
        "signals": signals,
    }
    (ROOT / "dist").mkdir(exist_ok=True)
    (ROOT / "dist" / "signals.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    )
    ok = sum(1 for v in signals.values() if "error" not in v)
    print(f"wrote dist/signals.json — {ok}/{len(signals)} artifacts, as_of {out['as_of']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
