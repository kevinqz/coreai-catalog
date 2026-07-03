#!/usr/bin/env python3
"""
Core AI Catalog — aggregated schema + cross-reference validator.

Collects ALL errors across ALL entity categories before exiting — never
fail-fast (redteam findings A9/F3). Every error carries the file, the
entity id, the field, and an actionable fix hint (nearest enum value,
allowed field names, missing-field list, ...). The validation core lives
in coreai_catalog/contribute.py and is shared with the CLI
``coreai-catalog contribute`` command and the MCP ``validate_entry`` tool
(one implementation, three surfaces).

Usage:
  python scripts/validate.py            # human-readable report
  python scripts/validate.py --json     # machine-readable JSON report
  python scripts/validate.py --github   # GitHub Actions ::error annotations

Exit codes: 0 = everything valid, 1 = at least one error.

Validates: catalog.yaml (models), artifacts.yaml, benchmarks.jsonl,
upstreams.yaml, terms.yaml, sources.yaml (schema/source.schema.json,
absorbing scripts/validate_sources.py), plus cross-reference integrity
between all of them.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coreai_catalog.contribute import (  # noqa: E402
    UPSTREAM_GROUPS,
    cross_reference_errors,
    format_error,
    ids_context,
    load_schema,
    make_error,
    read_yaml,
    schema_errors,
)


def _load_benchmarks_jsonl(root: Path, errors: list[dict]) -> list[dict]:
    """Parse benchmarks.jsonl, reporting malformed lines as errors."""
    path = root / "benchmarks.jsonl"
    benchmarks: list[dict] = []
    if not path.exists():
        return benchmarks
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            benchmarks.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            errors.append(
                make_error(
                    "benchmarks.jsonl",
                    f"<line {lineno}>",
                    "<root>",
                    f"invalid JSON: {exc}",
                    "each line must be exactly one JSON object",
                )
            )
    return benchmarks


def collect_errors(root: Path = ROOT) -> tuple[list[dict], dict]:
    """Aggregate every schema + cross-reference error across all entities."""
    errors: list[dict] = []

    catalog = read_yaml(root / "catalog.yaml")
    artifacts_data = read_yaml(root / "artifacts.yaml")
    sources_data = read_yaml(root / "sources.yaml")
    terms_data = read_yaml(root / "terms.yaml")
    upstreams_data = read_yaml(root / "upstreams.yaml")

    models = catalog.get("models", [])
    artifacts = artifacts_data.get("artifacts", [])
    sources = sources_data.get("sources", [])
    terms = terms_data.get("terms", [])
    upstreams: list[dict] = []
    for group in UPSTREAM_GROUPS:
        upstreams.extend(upstreams_data.get(group, []) or [])

    benchmarks = _load_benchmarks_jsonl(root, errors)

    # ── 1. Schema validation (aggregated per entry, hints included) ──
    for kind, items in [
        ("model", models),
        ("artifact", artifacts),
        ("benchmark", benchmarks),
        ("upstream", upstreams),
        ("term", terms),
        ("source", sources),
    ]:
        schema = load_schema(kind, root)
        for item in items:
            errors.extend(schema_errors(kind, item, root, schema=schema))

    # ── 2. Duplicate source ids (absorbs scripts/validate_sources.py) ──
    seen_source_ids: set[str] = set()
    for source in sources:
        source_id = source.get("id")
        if source_id in seen_source_ids:
            errors.append(
                make_error(
                    "sources.yaml", str(source_id), "id",
                    "duplicate id", "source ids must be unique",
                )
            )
        if source_id:
            seen_source_ids.add(source_id)

    # ── 3. Cross-reference integrity (same rules as validate_entry) ──
    context = ids_context(root)
    for kind, items in [
        ("model", models),
        ("artifact", artifacts),
        ("benchmark", benchmarks),
        ("upstream", upstreams),
    ]:
        for item in items:
            errors.extend(cross_reference_errors(kind, item, context))

    counts = {
        "models": len(models),
        "artifacts": len(artifacts),
        "benchmarks": len(benchmarks),
        "upstreams": len(upstreams),
        "terms": len(terms),
        "sources": len(sources),
    }
    return errors, counts


def find_entity_line(root: Path, err: dict) -> int | None:
    """Best-effort line number for an error's entity in its source file."""
    path = root / err["file"]
    if not path.exists():
        return None
    entity_id = err.get("entity_id", "")
    match = re.match(r"<line (\d+)>", entity_id)
    if match:
        return int(match.group(1))
    if not entity_id or entity_id.startswith("<"):
        return None
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    if err["file"].endswith(".jsonl"):
        needle = f'"id": "{entity_id}"'
        for i, line in enumerate(lines, start=1):
            if needle in line:
                return i
        return None
    pattern = re.compile(
        rf"^-\s+id:\s*['\"]?{re.escape(entity_id)}['\"]?\s*$"
    )
    for i, line in enumerate(lines, start=1):
        if pattern.match(line):
            return i
    return None


def emit_github_annotations(errors: list[dict], root: Path) -> None:
    """Emit GitHub Actions ::error annotations with file + line mapping."""
    for err in errors:
        location = f"file={err['file']}"
        line = find_entity_line(root, err)
        if line is not None:
            location += f",line={line}"
        message = f"{err['entity_id']}: {err['field']}: {err['message']}"
        if err.get("hint"):
            message += f" | hint: {err['hint']}"
        # Annotation messages must be single-line.
        message = message.replace("\n", " ")
        print(f"::error {location},title=validate::{message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate all catalog entities (aggregated, never fail-fast).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit a machine-readable JSON report",
    )
    parser.add_argument(
        "--github", action="store_true",
        help="Emit GitHub Actions ::error annotations (file + line)",
    )
    args = parser.parse_args(argv)

    errors, counts = collect_errors(ROOT)

    if args.json:
        report = {
            "ok": not errors,
            "error_count": len(errors),
            "counts": counts,
            "errors": [
                {**err, "line": find_entity_line(ROOT, err)} for err in errors
            ],
        }
        print(json.dumps(report, indent=2))
        if args.github and errors:
            emit_github_annotations(errors, ROOT)
        return 1 if errors else 0

    if args.github and errors:
        emit_github_annotations(errors, ROOT)

    if errors:
        print(f"\n{len(errors)} validation error(s) found:\n")
        for err in errors:
            print(f"  - {format_error(err)}")
        print(f"\nTotal: {len(errors)} error(s) across all entity categories.")
        return 1

    print(f"OK: {counts['benchmarks']} benchmarks (JSONL) validated against schema.")
    print(
        f"OK: {counts['models']} models, {counts['artifacts']} artifacts, "
        f"{counts['upstreams']} upstreams, {counts['benchmarks']} benchmarks, "
        f"{counts['sources']} sources and {counts['terms']} terms validated."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
