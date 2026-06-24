from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def validate_items(items: Iterable[dict], schema_path: Path, label: str) -> int:
    schema = json.loads(schema_path.read_text())
    validator = Draft202012Validator(schema)
    count = 0
    for item in items:
        errors = sorted(validator.iter_errors(item), key=lambda e: e.path)
        if errors:
            print(f"\nInvalid {label}: {item.get('id', '<missing id>')}")
            for error in errors:
                path = '.'.join(str(p) for p in error.path)
                print(f"  - {path}: {error.message}")
            raise SystemExit(1)
        count += 1
    return count


def validate_file(data_path: Path, schema_path: Path, key: str) -> int:
    data = yaml.safe_load(data_path.read_text()) or {}
    return validate_items(data.get(key, []), schema_path, key[:-1])


def flatten_upstreams(data: dict) -> list[dict]:
    groups = [
        'framework_sources',
        'conversion_sources',
        'artifact_hosts',
        'benchmark_sources',
        'sample_sources',
        'original_model_sources',
        'license_sources',
    ]
    items: list[dict] = []
    for group in groups:
        items.extend(data.get(group, []) or [])
    return items


def main() -> None:
    models = validate_file(ROOT / 'catalog.yaml', ROOT / 'schema' / 'model.schema.json', 'models')
    artifacts = validate_file(ROOT / 'artifacts.yaml', ROOT / 'schema' / 'artifact.schema.json', 'artifacts')
    benchmarks = validate_file(ROOT / 'benchmarks.yaml', ROOT / 'schema' / 'benchmark.schema.json', 'benchmarks')

    upstream_data = yaml.safe_load((ROOT / 'upstreams.yaml').read_text()) or {}
    upstreams = validate_items(flatten_upstreams(upstream_data), ROOT / 'schema' / 'upstream.schema.json', 'upstream')

    print(f'OK: {models} models, {artifacts} artifacts, {upstreams} upstreams and {benchmarks} benchmarks validated.')


if __name__ == '__main__':
    main()
