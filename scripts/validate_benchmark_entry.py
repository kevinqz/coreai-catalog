#!/usr/bin/env python3
"""Validate a benchmark JSONL entry against the schema.

Usage:
    python scripts/validate_benchmark_entry.py <file_with_jsonl_lines>

Exit codes:
    0 — all entries valid
    1 — one or more entries invalid
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "benchmark.schema.json"


def validate_entry(entry: dict, schema: dict) -> tuple[bool, str]:
    """Validate a single benchmark entry against the schema.

    Returns (success, error_message).
    """
    try:
        jsonschema.validate(instance=entry, schema=schema)
        return True, ""
    except jsonschema.ValidationError as e:
        # Provide a clear path to the invalid field
        path = ".".join(str(p) for p in e.absolute_path) or "root"
        return False, f"{path}: {e.message}"
    except jsonschema.SchemaError as e:
        return False, f"Schema error: {e}"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: validate_benchmark_entry.py <jsonl_file>", file=sys.stderr)
        return 1

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        return 1

    # Load schema
    if not SCHEMA_PATH.exists():
        print(f"Error: Schema not found at {SCHEMA_PATH}", file=sys.stderr)
        return 1
    schema = json.loads(SCHEMA_PATH.read_text())

    # Also load catalog model IDs for cross-reference
    catalog_path = ROOT / "catalog.yaml"
    valid_model_ids: set[str] = set()
    if catalog_path.exists():
        import yaml
        cat = yaml.safe_load(catalog_path.read_text()) or {}
        valid_model_ids = {m["id"] for m in cat.get("models", []) if "id" in m}

    lines = input_path.read_text().strip().splitlines()
    lines = [l for l in lines if l.strip() and not l.strip().startswith("#")]

    all_valid = True
    results: list[str] = []

    for i, line in enumerate(lines):
        line = line.strip().lstrip("+")
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            results.append(f"Line {i+1}: INVALID JSON: {e}")
            all_valid = False
            continue

        # Strip _signature before schema validation
        entry.pop("_signature", None)

        # Schema validation
        valid, err = validate_entry(entry, schema)
        if not valid:
            results.append(f"Line {i+1}: SCHEMA FAIL: {err}")
            all_valid = False
            continue

        # Cross-reference: model_id must exist in catalog
        if valid_model_ids:
            model_id = entry.get("model_id", "")
            if model_id not in valid_model_ids:
                results.append(
                    f"Line {i+1}: UNKNOWN model_id '{model_id}' "
                    f"(not in catalog.yaml)"
                )
                all_valid = False
                continue

        results.append(f"Line {i+1}: VALID (model_id={entry.get('model_id')})")

    # Write comment for GitHub Action
    comment = "## Schema Validation Results\n\n| Line | Result |\n|---|---|\n"
    for r in results:
        parts = r.split(": ", 2)
        comment += f"| {parts[0]} | {parts[2] if len(parts) > 2 else parts[-1]} |\n"

    comment_path = Path("/tmp/schema-comment.md")
    try:
        comment_path.write_text(comment)
    except OSError:
        pass

    for r in results:
        print(r)

    if all_valid:
        print("\nAll entries valid")
        return 0
    else:
        print("\n::error::Schema validation failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
