#!/usr/bin/env python3
"""
Core AI Catalog — Link Validator (availability watchdog)

Checks all URLs in the catalog YAMLs for accessibility (HTTP 2xx/3xx).
Retries transient failures (5xx, 429, network errors) with backoff, and
classifies rate limits separately so they do not count as regressions.

Runs daily in CI via .github/workflows/link-check.yml, which files or
updates a single pinned "Availability regression" issue on failure.
(Replaces the retired scripts/check_sources.sh laptop-bound watchdog.)

Exit codes: 0 = all links OK (rate limits tolerated), 1 = broken links.

Usage:
  python scripts/validate_links.py [--timeout 10] [--workers 10] [--retries 2]
                                   [--json] [--output report.json]
                                   [--issue-body body.md]
"""
from __future__ import annotations

import argparse
import sys
import concurrent.futures
import json
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

import yaml

ROOT = Path(__file__).resolve().parent.parent

USER_AGENT = "coreai-catalog-link-checker/2.0"

# HTTP statuses treated as transient: retried, and (for 429) never a regression.
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


# ── Collect all URLs from YAMLs ──
def collect_urls() -> list[dict]:
    """Return list of {file, id, field, url} dicts for every URL in the YAML sources."""
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
        for i, mirror in enumerate(a.get("mirrors", []) or []):
            murl = mirror.get("url", "") if isinstance(mirror, dict) else ""
            if murl:
                urls.append({"file": "artifacts.yaml", "id": a["id"], "field": f"mirrors[{i}].url", "url": murl})

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


def _fetch_status(url: str, timeout: int) -> int:
    """Return the HTTP status for a URL (raises HTTPError/URLError on failure)."""
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        return resp.status


def check_url(entry: dict, timeout: int = 10, retries: int = 2, backoff: float = 2.0) -> dict:
    """Check a single URL with retries. Returns entry + status/ok/rate_limited."""
    url = entry["url"]
    result = dict(entry)
    result["attempts"] = 0
    last_status = 0
    last_error = ""

    for attempt in range(retries + 1):
        result["attempts"] = attempt + 1
        try:
            status = _fetch_status(url, timeout)
            result["status"] = status
            result["ok"] = True
            result["rate_limited"] = False
            return result
        except HTTPError as e:
            last_status = e.code
            last_error = str(e)
            if e.code not in RETRYABLE_STATUSES:
                break
        except URLError as e:
            last_status = 0
            last_error = str(e.reason)
        except Exception as e:  # pragma: no cover — defensive
            last_status = 0
            last_error = str(e)
        if attempt < retries:
            time.sleep(backoff * (attempt + 1))

    result["status"] = last_status
    result["ok"] = False
    # Rate limits are transient upstream throttling, not availability regressions.
    result["rate_limited"] = last_status == 429
    result["error"] = last_error
    return result


def build_report(results: list[dict]) -> dict:
    """Aggregate per-URL results into the JSON report structure."""
    broken = [r for r in results if not r["ok"] and not r.get("rate_limited")]
    rate_limited = [r for r in results if not r["ok"] and r.get("rate_limited")]
    return {
        "total": len(results),
        "ok": len(results) - len(broken) - len(rate_limited),
        "broken": len(broken),
        "rate_limited": len(rate_limited),
        "results": results,
    }


def build_issue_body(report: dict) -> str:
    """Render a markdown issue body for the pinned availability-regression issue."""
    lines = [
        "# Availability regression",
        "",
        f"Automated link check found **{report['broken']} broken URL(s)** "
        f"out of {report['total']} checked "
        f"({report['ok']} OK, {report['rate_limited']} rate-limited).",
        "",
        "| Source file | Entity | Field | Status | URL |",
        "|---|---|---|---|---|",
    ]
    for r in report["results"]:
        if r["ok"] or r.get("rate_limited"):
            continue
        status = r["status"] if r["status"] else f"network error: {r.get('error', '?')[:60]}"
        lines.append(f"| `{r['file']}` | `{r['id']}` | `{r['field']}` | {status} | {r['url']} |")
    lines += [
        "",
        "_This issue is maintained by `.github/workflows/link-check.yml` "
        "(scripts/validate_links.py). It is updated in place — do not open duplicates._",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate catalog URLs")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP timeout per URL")
    parser.add_argument("--workers", type=int, default=10, help="Concurrent workers")
    parser.add_argument("--retries", type=int, default=2, help="Retries per URL on transient failures")
    parser.add_argument("--json", action="store_true", help="Output report as JSON to stdout")
    parser.add_argument("--output", type=Path, default=None, help="Write JSON report to this file")
    parser.add_argument("--issue-body", type=Path, default=None,
                        help="Write a markdown issue body to this file when links are broken")
    args = parser.parse_args()

    urls = collect_urls()
    print(f"Checking {len(urls)} unique URLs...", file=sys.stderr)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(check_url, u, args.timeout, args.retries): u for u in urls}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    # Sort: broken first, then by URL
    results.sort(key=lambda r: (1 if r["ok"] else 0, r["url"]))
    report = build_report(results)

    if args.output:
        args.output.write_text(json.dumps(report, indent=2))
    if args.issue_body and report["broken"]:
        args.issue_body.write_text(build_issue_body(report))

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for r in results:
            if r["ok"]:
                status = "OK"
            elif r.get("rate_limited"):
                status = "RATE-LIMITED"
            else:
                status = f"BROKEN ({r['status']})"
            print(f"  [{status:12s}] {r['url'][:80]}")
            if not r["ok"]:
                print(f"                 {r.get('error', '')[:80]}")

        print(
            f"\n{report['ok']} OK, {report['broken']} broken, "
            f"{report['rate_limited']} rate-limited out of {report['total']} URLs",
            file=sys.stderr,
        )

    return 1 if report["broken"] else 0


if __name__ == "__main__":
    sys.exit(main())
