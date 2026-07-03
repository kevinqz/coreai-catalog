#!/usr/bin/env python3
"""Count-sync guard: one source of truth for every public count.

The boundary/feedback redteam found model/benchmark/tool counts drifting across
README, llms.txt, agent.json, openapi.yaml, the site, and PyPI (79 vs 80 vs 81;
65 vs 66; 12 vs 16). For a project whose whole value is verifiability, that is a
credibility bug. This script computes the CANONICAL counts from the data files
and asserts every surface agrees. Wire it into CI so the class of bug can't
return; run it before publishing.

Exit 0 = all surfaces agree. Exit 1 = a surface is stale (message says which).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def canonical() -> dict[str, int]:
    models = len(yaml.safe_load((ROOT / "catalog.yaml").read_text())["models"])
    artifacts = len(yaml.safe_load((ROOT / "artifacts.yaml").read_text())["artifacts"])
    upstreams = len(yaml.safe_load((ROOT / "upstreams.yaml").read_text().replace("\t", "  "))
                    .get("original_model_sources", []))  # placeholder, replaced below
    # upstreams.yaml groups sources under several keys; count them all.
    up = yaml.safe_load((ROOT / "upstreams.yaml").read_text())
    upstreams = sum(len(v) for k, v in up.items()
                    if isinstance(v, list))
    sources = len(yaml.safe_load((ROOT / "sources.yaml").read_text())["sources"])
    benchmarks = sum(1 for line in (ROOT / "benchmarks.jsonl").read_text().splitlines()
                     if line.strip())
    terms = len(yaml.safe_load((ROOT / "terms.yaml").read_text())["terms"])
    # MCP tool count: agent.json declares it and the validate.yml smoke test
    # already asserts it equals the live server, so it is authoritative here.
    tools = json.loads((ROOT / "agent.json").read_text())["mcp_server"]["tools"]
    return {
        "models": models,
        "artifacts": artifacts,
        "upstreams": upstreams,
        "sources": sources,
        "benchmarks": benchmarks,
        "terms": terms,
        "mcp_tools": tools,
    }


def check() -> list[str]:
    c = canonical()
    errors: list[str] = []

    def must_contain(rel: str, needle: str, why: str):
        text = (ROOT / rel).read_text()
        if needle not in text:
            errors.append(f"{rel}: expected {why} (looking for {needle!r})")

    def must_not_contain(rel: str, needle: str, why: str):
        text = (ROOT / rel).read_text()
        if needle in text:
            errors.append(f"{rel}: STALE — {why} (found {needle!r})")

    m = c["models"]
    # README scope table + status line.
    must_contain("README.md", f"{m} Apple Core AI models", "status line model count")
    must_contain("README.md", f"| Model records | {m} |", "scope-table model count")
    must_contain("README.md", f"| Artifact provenance records | {c['artifacts']} |", "artifact count")
    must_contain("README.md", f"| Source records | {c['sources']} |", "source count")
    must_contain("README.md", f"| Upstream taxonomy entries | {c['upstreams']} |", "upstream count")
    must_contain("README.md", f"| Benchmark records | {c['benchmarks']} |", "benchmark count")
    must_contain("README.md", f"| Terminology records | {c['terms']} |", "term count")
    # Agent + API surfaces.
    must_contain("llms.txt", f"catalog of {m} Apple Core AI models", "llms model count")
    must_contain("llms.txt", f"- {m} model records", "llms model-records count")
    must_contain("llms.txt", f"- {c['benchmarks']} benchmark records", "llms benchmark count")
    must_contain("agent.json", f"catalog of {m} Apple Core AI models", "agent.json model count")
    must_contain("openapi.yaml", f"catalog of {m} Apple Core AI models", "openapi model count")
    # Site: hero, About prose, meta description, and the stat fallbacks.
    must_contain("site/index.html", f">{m} Apple Core AI models", "site hero model count")
    must_contain("site/index.html", f"registry of {m} Apple Core AI models", "site About model count")
    must_contain("site/index.html", f'content="The agent-ready registry for Apple on-device AI. {m} Core AI models',
                 "site meta description model count")
    must_contain("site/index.html", f'id="stat-models">{m}<', "site stat-models fallback")
    must_contain("site/index.html", f'id="stat-mcp">{c["mcp_tools"]}<', "site stat-mcp count")
    return errors


def main() -> int:
    c = canonical()
    print("canonical counts: " + ", ".join(f"{k}={v}" for k, v in c.items()))
    errors = check()
    if errors:
        print(f"\ncount-sync FAILED ({len(errors)} surface(s) stale):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("count-sync OK: every checked surface agrees with the data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
