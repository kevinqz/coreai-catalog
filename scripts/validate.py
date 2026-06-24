from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog.yaml"
SCHEMA_PATH = ROOT / "schema" / "model.schema.json"


def main() -> None:
    catalog = yaml.safe_load(CATALOG_PATH.read_text())
    schema = json.loads(SCHEMA_PATH.read_text())
    validator = Draft202012Validator(schema)
    errors_found = False

    for model in catalog.get("models", []):
        errors = sorted(validator.iter_errors(model), key=lambda e: e.path)
        if errors:
            errors_found = True
            print(f"\nInvalid model: {model.get('id', '<missing id>')}")
            for error in errors:
                path = ".".join(str(p) for p in error.path)
                print(f"  - {path}: {error.message}")

    if errors_found:
        raise SystemExit(1)

    print(f"OK: {len(catalog.get('models', []))} models validated.")


if __name__ == "__main__":
    main()
