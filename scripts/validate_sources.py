#!/usr/bin/env python3
"""
Core AI Catalog — sources.yaml validator.

Validates every record in sources.yaml against schema/source.schema.json
(entity schema, duplicate ids, trusted-host URL allowlist — the allowlist
is encoded in the schema's url pattern).

Standalone usage:
  python scripts/validate_sources.py

Library usage (for scripts/validate.py to call):
  from validate_sources import validate_sources
  errors = validate_sources(ROOT)   # list[str]; empty means valid
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def validate_sources(root: Path = ROOT) -> list[str]:
    """Validate sources.yaml against schema/source.schema.json.

    Returns a list of human-readable error strings; an empty list means
    every source record is valid. Aggregates all errors instead of
    stopping at the first one.
    """
    schema = json.loads((root / "schema" / "source.schema.json").read_text())
    validator = Draft202012Validator(schema)
    data = yaml.safe_load((root / "sources.yaml").read_text()) or {}
    sources = data.get("sources", [])

    errors: list[str] = []
    seen_ids: set[str] = set()
    for source in sources:
        source_id = source.get("id", "<missing id>")
        if source_id in seen_ids:
            errors.append(f"source {source_id}: duplicate id")
        seen_ids.add(source_id)
        for error in sorted(validator.iter_errors(source), key=lambda e: list(e.path)):
            path = ".".join(str(p) for p in error.path) or "<root>"
            errors.append(f"source {source_id}: {path}: {error.message}")
    return errors


def main() -> int:
    errors = validate_sources(ROOT)
    if errors:
        print("Invalid sources.yaml:")
        for error in errors:
            print(f"  - {error}")
        return 1
    data = yaml.safe_load((ROOT / "sources.yaml").read_text()) or {}
    print(f"OK: {len(data.get('sources', []))} sources validated against schema.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
