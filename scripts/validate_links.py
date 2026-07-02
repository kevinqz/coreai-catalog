#!/usr/bin/env python3
"""
Core AI Catalog — Link Validator

Checks all URLs in the catalog YAMLs for accessibility (HTTP 200).
Outputs a report of broken or redirected links.

Usage:
  python scripts/validate_links.py [--timeout 10] [--workers 10]
"""
from __future__ import annotations

import argparse
import sys
import concurrent.futures
import json
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

import yaml

ROOT = Path(__file__).resolve().parent.parent

# ── Collect all URLs from YAMLs ──
def collect_urls() -> list[dict]:
    """Return list of {source_file, entity_id, field, url} dicts."""
    urls = []

    # catalog.yaml — source_path, artifact URLs
    with open(ROOT / "catalog.yaml") as f:
        data = yaml.safe_load(f)
    for m in data.get("models", []):
        sp = m.get("source_path", "")
        if sp and sp.startswith("http"):
            urls.append({"file": "catalog.yaml", "id": m["id"], "field": "source_path", "url": sp})

    # artifacts.yaml — github.path, huggingface.url
    with open(ROOT / "artifacts.yaml") as f:
        data = yaml.safe_load(f)
    for a in data.get("artifacts", []):
        gh = a.get("github", {}) or {}
        path = gh.get("path", "")
        if path and path.startswith("http"):
            urls.append({"file": "artifacts.yaml", "id": a["id"], "field": "github.path", "url": path})
        hf = a.get("huggingface", {}) or {}
        url = hf.get("url", "")
        if url:
            urls.append({"file": "artifacts.yaml", "id": a["id"], "field": "huggingface.url", "url": url})

    # sources.yaml — url
    with open(ROOT / "sources.yaml") as f:
        data = yaml.safe_load(f)
    for s in data.get("sources", []):
        url = s.get("url", "")
        if url:
            urls.append({"file": "sources.yaml", "id": s["id"], "field": "url", "url": url})

    # upstreams.yaml — all url fields
    with open(ROOT / "upstreams.yaml") as f:
        data = yaml.safe_load(f)
    for section, entries in data.items():
        if not isinstance(entries, list):
            continue
        for e in entries:
            if isinstance(e, dict):
                url = e.get("url", "")
                if url:
                    urls.append({"file": "upstreams.yaml", "id": e.get("id", section), "field": f"{section}.url", "url": url})

    # Deduplicate by URL
    seen = set()
    unique = []
    for u in urls:
        if u["url"] not in seen:
            seen.add(u["url"])
            unique.append(u)
    return unique


def check_url(entry: dict, timeout: int = 10) -> dict:
    """Check a single URL. Returns entry + status."""
    url = entry["url"]
    result = dict(entry)
    try:
        req = Request(url, headers={"User-Agent": "coreai-catalog-link-checker/1.0"})
        resp = urlopen(req, timeout=timeout)
        result["status"] = resp.status
        result["ok"] = True
    except HTTPError as e:
        result["status"] = e.code
        result["ok"] = False
        result["error"] = str(e)
    except URLError as e:
        result["status"] = 0
        result["ok"] = False
        result["error"] = str(e.reason)
    except Exception as e:
        result["status"] = 0
        result["ok"] = False
        result["error"] = str(e)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate catalog URLs")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP timeout per URL")
    parser.add_argument("--workers", type=int, default=10, help="Concurrent workers")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    urls = collect_urls()
    print(f"Checking {len(urls)} unique URLs...", file=sys.stderr)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(check_url, u, args.timeout): u for u in urls}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    # Sort: broken first, then by URL
    results.sort(key=lambda r: (0 if not r["ok"] else 1, r["url"]))

    broken = [r for r in results if not r["ok"]]
    ok_count = len(results) - len(broken)

    if args.json:
        print(json.dumps({
            "total": len(results),
            "ok": ok_count,
            "broken": len(broken),
            "results": results,
        }, indent=2))
    else:
        for r in results:
            status = "OK" if r["ok"] else f"BROKEN ({r['status']})"
            print(f"  [{status:12s}] {r['url'][:80]}")
            if not r["ok"]:
                print(f"                 {r.get('error', '')[:80]}")

        print(f"\n{ok_count} OK, {len(broken)} broken out of {len(results)} URLs", file=sys.stderr)

    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
