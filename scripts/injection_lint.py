#!/usr/bin/env python3
"""
Prompt-injection lint for catalog free-text fields (redteam finding D6).

Free-text fields (notes, name, title, definition, environment, ...) in
the YAML/JSONL sources flow verbatim into MCP tool results and generated
docs, i.e. into downstream agents' context windows. A PR that plants
instruction-like text in those fields is an indirect prompt-injection
vector. This lint runs at PR time and flags:

  - imperative-to-agent phrases ("ignore previous instructions",
    "you must now", "do not tell the user", ...)
  - tool-call / chat-transcript syntax (<tool_use>, "tool_call":,
    <|im_start|>, "assistant:", ...)
  - shell-execution requests aimed at the reading agent
  - markdown auto-fetch / data-exfil patterns (image links, data: URLs,
    templated query strings)
  - invisible / bidirectional Unicode that hides payloads from reviewers
  - markdown fence-breaking sequences (```)

An ALLOWLIST of verified-legitimate phrasings suppresses known-benign
matches (each entry documents why it is safe). Output follows the
scripts/validate.py conventions: ALL findings aggregated, actionable
messages, --json for machines, exit 1 when anything is flagged.

Usage:
  python scripts/injection_lint.py           # human-readable report
  python scripts/injection_lint.py --json    # machine-readable JSON

Scans: catalog.yaml, artifacts.yaml, benchmarks.jsonl, sources.yaml,
upstreams.yaml, terms.yaml.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

#: Keys whose values are free-form prose (anything a human typed).
#: Schema-constrained identifiers/enums/URLs are not scanned.
FREE_TEXT_KEYS = {
    "name", "notes", "title", "description", "definition",
    "caveats", "reason", "environment", "label",
}

#: Detection patterns. Each entry: (pattern_id, compiled regex, message).
#: Tuned against the full current corpus (247 unique free-text strings,
#: 2026-07-03) — technical prose like "Use model-specific Qwen cards" or
#: "custom Metal kernel per upstream caveat" must NOT trip these, so
#: every pattern requires an agent-directed construction, not a bare
#: imperative verb.
PATTERNS: list[tuple[str, re.Pattern, str]] = [
    (
        "override-instructions",
        re.compile(
            r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,50}"
            r"\b(previous|prior|above|earlier|all|any|system|your)\b[^.\n]{0,30}"
            r"\b(instruction|prompt|rule|guideline|message|context)s?\b",
            re.IGNORECASE,
        ),
        "instruction-override phrase aimed at a reading agent",
    ),
    (
        "agent-directive",
        re.compile(
            r"\byou (must|should|will|are (now |required to ))\b"
            r"|\bas an ai\b|\bthe assistant (must|should|will)\b",
            re.IGNORECASE,
        ),
        "second-person directive addressed to the reading agent",
    ),
    (
        "role-or-transcript-syntax",
        re.compile(
            r"<\|im_start\|>|<\|system\|>|\[/?(?:INST|SYS)\]"
            r"|^\s*(system|assistant|user)\s*:\s"
            r"|\bnew system prompt\b|\bdeveloper message\b",
            re.IGNORECASE | re.MULTILINE,
        ),
        "chat-transcript / role-marker syntax embedded in data",
    ),
    (
        "tool-call-syntax",
        re.compile(
            r"<(tool_use|tool_call|function_call|invoke|antml)\b"
            r"|\"(tool_call|function_call|tool_name)\"\s*:"
            r"|\bmcp__[a-z0-9_]+__",
            re.IGNORECASE,
        ),
        "tool-call syntax embedded in data",
    ),
    (
        "exec-request",
        re.compile(
            r"\b(run|execute)\s+(the\s+following|this)\s+(command|script|code|shell)\b"
            r"|\bcurl\s+-|\bcurl\s+https?://|\brm\s+-rf\b|\bchmod\s+\+x\b"
            r"|\$\(.*\)|`[a-z]+\s+-[a-z]",
            re.IGNORECASE,
        ),
        "shell-execution request or command substitution in prose",
    ),
    (
        "exfil-markdown",
        re.compile(
            r"!\[[^\]]*\]\(\s*https?://"      # auto-fetching image link
            r"|\]\(\s*data:"                   # data: URL link target
            r"|\]\(\s*https?://[^)\s]*[?&][^)\s]*(\{|%7B|\$)",  # templated query
            re.IGNORECASE,
        ),
        "markdown auto-fetch / data-exfiltration link pattern",
    ),
    (
        "secrecy-directive",
        re.compile(
            r"\bdo not (tell|show|reveal|mention|inform|alert)\b"
            r"|\bwithout (telling|informing|asking)\b"
            r"|\bkeep this (secret|hidden)\b",
            re.IGNORECASE,
        ),
        "secrecy directive aimed at the reading agent",
    ),
    (
        "invisible-unicode",
        re.compile(
            "["
            "\u00ad"
            "\u200b-\u200f"
            "\u202a-\u202e"
            "\u2060-\u2064"
            "\u2066-\u2069"
            "\ufeff"
            "\ufff9-\ufffb"
            "\U000e0000-\U000e007f"
            "]"
        ),
        "invisible or bidirectional Unicode character (hidden-payload vector)",
    ),
    (
        "fence-break",
        re.compile(r"`{3,}|~{4,}"),
        "markdown fence sequence (can escape a rendered code block)",
    ),
]

#: Verified-legitimate phrasings. A finding whose matched text occurs
#: inside one of these exact substrings is suppressed. Add entries ONLY
#: for phrases verified against the actual upstream source — never to
#: silence an unreviewed finding.
ALLOWLIST: list[str] = [
    # (none needed for current catalog data as of 2026-07-03; the
    #  patterns above pass the full corpus without suppression)
]


def _iter_free_text(prefix: str, obj) -> list[tuple[str, str]]:
    """Recursively yield (field_path, value) for free-text keys."""
    found: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, str) and key in FREE_TEXT_KEYS:
                found.append((path, value))
            else:
                found.extend(_iter_free_text(path, value))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            found.extend(_iter_free_text(f"{prefix}[{idx}]", value))
    return found


def _allowlisted(matched: str, text: str) -> bool:
    """True when the match sits inside a verified-legitimate phrase."""
    for allowed in ALLOWLIST:
        if matched in allowed and allowed in text:
            return True
    return False


def scan_text(file: str, entity_id: str, field: str, text: str) -> list[dict]:
    """Scan one free-text value; return finding dicts (validate.py shape)."""
    findings: list[dict] = []
    for pattern_id, pattern, message in PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        matched = match.group(0)
        if _allowlisted(matched, text):
            continue
        findings.append({
            "file": file,
            "entity_id": entity_id,
            "field": field,
            "pattern": pattern_id,
            "matched": matched if matched.strip() else repr(matched),
            "message": message,
            "hint": (
                "free-text fields must contain descriptive prose only; "
                "if this phrasing is genuinely legitimate, verify it "
                "against the upstream source and add it to ALLOWLIST in "
                "scripts/injection_lint.py with a justification"
            ),
        })
    return findings


def scan_entities(file: str, entities: list[dict]) -> list[dict]:
    """Scan a list of entity dicts (models, artifacts, sources, ...)."""
    findings: list[dict] = []
    for entity in entities:
        entity_id = str(entity.get("id", "<no-id>"))
        for field, value in _iter_free_text("", entity):
            findings.extend(scan_text(file, entity_id, field, value))
    return findings


def collect_findings(root: Path = ROOT) -> list[dict]:
    """Aggregate findings across every catalog source file."""
    findings: list[dict] = []

    def load_yaml(name: str) -> dict:
        path = root / name
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text()) or {}

    findings.extend(
        scan_entities("catalog.yaml", load_yaml("catalog.yaml").get("models", []))
    )
    findings.extend(
        scan_entities("artifacts.yaml", load_yaml("artifacts.yaml").get("artifacts", []))
    )
    findings.extend(
        scan_entities("sources.yaml", load_yaml("sources.yaml").get("sources", []))
    )
    findings.extend(
        scan_entities("terms.yaml", load_yaml("terms.yaml").get("terms", []))
    )
    upstreams_data = load_yaml("upstreams.yaml")
    for group, items in upstreams_data.items():
        if isinstance(items, list):
            findings.extend(
                scan_entities("upstreams.yaml", [u for u in items if isinstance(u, dict)])
            )

    jsonl = root / "benchmarks.jsonl"
    if jsonl.exists():
        benchmarks = []
        for line in jsonl.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                benchmarks.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # malformed lines are validate.py's job
        findings.extend(scan_entities("benchmarks.jsonl", benchmarks))

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Lint catalog free-text fields for prompt-injection patterns "
            "(aggregated, never fail-fast)."
        ),
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit a machine-readable JSON report",
    )
    args = parser.parse_args(argv)

    findings = collect_findings(ROOT)

    if args.json:
        print(json.dumps({
            "ok": not findings,
            "finding_count": len(findings),
            "findings": findings,
        }, indent=2, ensure_ascii=False))
        return 1 if findings else 0

    if findings:
        print(f"\n{len(findings)} injection-lint finding(s):\n")
        for f in findings:
            print(
                f"  - {f['file']} [{f['entity_id']}] {f['field']}: "
                f"{f['message']} (pattern={f['pattern']}, "
                f"matched={f['matched']!r})"
            )
            print(f"      hint: {f['hint']}")
        print(f"\nTotal: {len(findings)} finding(s).")
        return 1

    print("OK: 0 injection-lint findings across catalog free-text fields.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
