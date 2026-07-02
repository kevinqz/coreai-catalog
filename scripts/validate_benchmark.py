"""Benchmark validation script — validates new JSONL lines against schema."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def validate_line(line: str, schema: dict) -> list[str]:
    """Validate a single JSONL line. Returns list of errors (empty = valid)."""
    errors: list[str] = []

    try:
        entry = json.loads(line)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]

    # Required fields
    required = schema.get("required", [])
    for field in required:
        if field not in entry:
            errors.append(f"Missing required field: {field}")

    # Validate model_id is non-empty
    model_id = entry.get("model_id", "")
    if not model_id or not isinstance(model_id, str):
        errors.append("model_id must be a non-empty string")

    # Validate metric is in enum
    metric = entry.get("metric", "")
    metric_enum = schema.get("properties", {}).get("metric", {}).get("enum", [])
    if metric and metric_enum and metric not in metric_enum:
        errors.append(f"Invalid metric '{metric}'. Valid: {metric_enum}")

    # Validate unit is in enum
    unit = entry.get("unit", "")
    unit_enum = schema.get("properties", {}).get("unit", {}).get("enum", [])
    if unit and unit_enum and unit not in unit_enum:
        errors.append(f"Invalid unit '{unit}'. Valid: {unit_enum}")

    # Validate value is numeric
    value = entry.get("value")
    if value is not None and not isinstance(value, (int, float)):
        if isinstance(value, str):
            try:
                float(value)
            except ValueError:
                errors.append(f"value must be numeric, got: {value!r}")
        else:
            errors.append(f"value must be numeric, got: {type(value).__name__}")

    # Validate observed date format
    import re
    observed = entry.get("observed", "")
    if observed and not re.match(r"^\d{4}-\d{2}-\d{2}$", observed):
        errors.append(f"observed must be YYYY-MM-DD format, got: {observed!r}")

    # Validate confidence enum
    confidence = entry.get("confidence", "")
    conf_enum = schema.get("properties", {}).get("confidence", {}).get("enum", [])
    if confidence and conf_enum and confidence not in conf_enum:
        errors.append(f"Invalid confidence '{confidence}'. Valid: {conf_enum}")

    # Validate provenance block if present
    prov = entry.get("provenance", {})
    if prov:
        extraction = prov.get("extraction_method", "")
        extraction_enum = (
            schema.get("properties", {})
            .get("provenance", {})
            .get("properties", {})
            .get("extraction_method", {})
            .get("enum", [])
        )
        if extraction and extraction_enum and extraction not in extraction_enum:
            errors.append(f"Invalid extraction_method '{extraction}'. Valid: {extraction_enum}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate benchmark JSONL lines")
    parser.add_argument("--input", required=True, help="Path to JSONL file to validate")
    parser.add_argument("--schema", default="schema/benchmark.schema.json",
                        help="Path to benchmark schema")
    args = parser.parse_args()

    schema_path = Path(args.schema)
    if not schema_path.exists():
        print(f"Schema not found: {schema_path}", file=sys.stderr)
        return 1

    schema = json.loads(schema_path.read_text())

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 1

    total = 0
    errors_count = 0

    for line_num, line in enumerate(input_path.read_text().strip().split("\n"), 1):
        line = line.strip()
        if not line:
            continue
        total += 1
        errors = validate_line(line, schema)
        if errors:
            errors_count += 1
            entry = json.loads(line) if line.startswith("{") else {}
            model_id = entry.get("model_id", "unknown")
            print(f"  FAIL line {line_num} ({model_id}):")
            for e in errors:
                print(f"    - {e}")

    if errors_count == 0:
        print(f"  {total} benchmark(s) validated, 0 errors")
        return 0
    else:
        print(f"\n  {errors_count}/{total} benchmark(s) FAILED validation")
        return 1


if __name__ == "__main__":
    sys.exit(main())
