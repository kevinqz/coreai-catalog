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
    pyproject_version = _read_versions()["pyproject.toml"]
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
    must_contain("llms.txt", f"- {c['artifacts']} artifact provenance records", "llms artifact count")
    must_contain("llms.txt", f"- {c['benchmarks']} benchmark records", "llms benchmark count")
    must_contain("llms.txt", f"**Version:** {pyproject_version}", "llms version")
    must_contain("llms.txt", f"bundle_kind on all {m}", "llms bundle_kind count")
    # llms-full.txt — full LLM context file (same drift class)
    must_contain("llms-full.txt", f"- {m} model records", "llms-full model-records count")
    must_contain("llms-full.txt", f"- {c['artifacts']} artifact provenance records", "llms-full artifact count")
    must_contain("llms-full.txt", f"- {c['benchmarks']} benchmark records", "llms-full benchmark count")
    must_contain("llms-full.txt", f"**Version:** {pyproject_version}", "llms-full version")
    must_contain("llms-full.txt", f"bundle_kind` on all {m}", "llms-full bundle_kind count")
    must_contain("agent.json", f"catalog of {m} Apple Core AI models", "agent.json model count")
    must_contain("openapi.yaml", f"catalog of {m} Apple Core AI models", "openapi model count")
    # Site: hero, About prose, meta description, and the stat fallbacks.
    must_contain("site/index.html", f">{m} Apple Core AI models", "site hero model count")
    must_contain("site/index.html", f"registry of {m} Apple Core AI models", "site About model count")
    must_contain("site/index.html", f'content="The agent-ready registry for Apple on-device AI. {m} Core AI models',
                 "site meta description model count")
    must_contain("site/index.html", f'id="stat-models">{m}<', "site stat-models fallback")
    must_contain("site/index.html", f'id="stat-mcp">{c["mcp_tools"]}<', "site stat-mcp count")
    # README MCP-tools count must match the live server (feedback: README said
    # 12 while the server and every other surface said 16).
    must_contain("README.md", f"exposes {c['mcp_tools']} tools",
                 "README MCP-server tool count")
    must_contain("README.md", f"### Available tools ({c['mcp_tools']})",
                 "README MCP-tools section header count")

    errors.extend(_version_errors())
    return errors


def _read_versions() -> dict[str, str | None]:
    """Extract the declared version string from every surface that carries one."""
    import re

    def rx(rel: str, pattern: str) -> str | None:
        mo = re.search(pattern, (ROOT / rel).read_text())
        return mo.group(1) if mo else None

    return {
        "pyproject.toml": rx("pyproject.toml", r'(?m)^version\s*=\s*"([^"]+)"'),
        "catalog.yaml": yaml.safe_load((ROOT / "catalog.yaml").read_text())["metadata"].get("version"),
        "agent.json": json.loads((ROOT / "agent.json").read_text()).get("version"),
        "openapi.yaml": rx("openapi.yaml", r"(?m)^\s+version:\s*['\"]?([0-9][^'\"\n]+)"),
        "README.md": rx("README.md", r"\*\*Version:\*\*\s*v([0-9][0-9.]+)"),
        "llms.txt": rx("llms.txt", r"\*\*Version:\*\*\s*([0-9][0-9.]+)"),
        "llms-full.txt": rx("llms-full.txt", r"\*\*Version:\*\*\s*([0-9][0-9.]+)"),
    }


def _version_errors() -> list[str]:
    """The version contract: every surface must carry the same version."""
    versions = _read_versions()
    canonical_version = versions["pyproject.toml"]
    errs: list[str] = []
    for surface, ver in versions.items():
        if ver is None:
            errs.append(f"{surface}: could not read a version string")
        elif ver != canonical_version:
            errs.append(
                f"{surface}: version {ver!r} != pyproject.toml {canonical_version!r} "
                "(the version contract requires all surfaces to match)"
            )
    return errs


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
