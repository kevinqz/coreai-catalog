#!/usr/bin/env python3
"""Discover: analyze upstream model landscape and prioritize porting candidates.

Thin CLI wrapper around coreai_catalog/discover.py (the reusable module —
see it for the dedup design that fixed redteam finding F4). The weekly
.github/workflows/discover.yml runs this with --format markdown and
upserts the single pinned "Porting candidates" issue.

Usage:
    python scripts/discover.py                     # full scan, terminal report
    python scripts/discover.py --device iphone     # iPhone-capable only
    python scripts/discover.py --json              # JSON output
    python scripts/discover.py --format markdown   # pinned-issue body
    python scripts/discover.py --limit 10          # top 10 candidates
    python scripts/discover.py --no-base-models    # skip HF lineage fetches
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coreai_catalog import discover  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Discover models worth porting to Core AI"
    )
    parser.add_argument("--device", choices=["iphone", "mac"], help="Filter by device")
    parser.add_argument("--limit", type=int, default=20, help="Max results")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--format", choices=["report", "json", "markdown"], default="report",
        help="Output format (markdown = pinned-issue body)",
    )
    parser.add_argument(
        "--no-base-models", action="store_true",
        help="Skip Hugging Face base_model lineage fetches (faster, "
             "dedup falls back to upstream_repo + fuzzy name layers)",
    )
    args = parser.parse_args()

    candidates = discover.run_discovery(
        root=ROOT,
        device_filter=args.device,
        limit=args.limit,
        resolve_base_models=not args.no_base_models,
    )

    if args.json or args.format == "json":
        print(discover.render_json(candidates))
    elif args.format == "markdown":
        index = discover.build_catalog_index(root=ROOT)
        print(discover.render_markdown(
            candidates, catalog_count=index.model_count,
        ))
    else:
        print(discover.format_report(candidates))

    return 0


if __name__ == "__main__":
    sys.exit(main())
