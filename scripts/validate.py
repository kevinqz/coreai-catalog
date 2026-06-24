from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]

def validate_file(data_path: Path, schema_path: Path, key: str) -> int:
    data = yaml.safe_load(data_path.read_text())
    schema = json.loads(schema_path.read_text())
    validator = Draft202012Validator(schema)
    count = 0
    for item in data.get(key, []):
        errors = sorted(validator.iter_errors(item), key=lambda e: e.path)
        if errors:
            print(f"\nInvalid {key[:-1]}: {item.get('id', '<missing id>')}")
            for error in errors:
                path = '.'.join(str(p) for p in error.path)
                print(f"  - {path}: {error.message}")
            raise SystemExit(1)
        count += 1
    return count

def main() -> None:
    models = validate_file(ROOT / 'catalog.yaml', ROOT / 'schema' / 'model.schema.json', 'models')
    artifacts = validate_file(ROOT / 'artifacts.yaml', ROOT / 'schema' / 'artifact.schema.json', 'artifacts')
    print(f'OK: {models} models and {artifacts} artifacts validated.')

if __name__ == '__main__':
    main()
