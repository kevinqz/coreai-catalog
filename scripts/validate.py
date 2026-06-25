from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]

UPSTREAM_GROUPS = [
    'framework_sources',
    'conversion_sources',
    'artifact_hosts',
    'benchmark_sources',
    'sample_sources',
    'original_model_sources',
    'license_sources',
]


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


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
    data = read_yaml(data_path)
    return validate_items(data.get(key, []), schema_path, key[:-1])


def flatten_upstreams(data: dict) -> list[dict]:
    items: list[dict] = []
    for group in UPSTREAM_GROUPS:
        items.extend(data.get(group, []) or [])
    return items


def fail(message: str) -> None:
    print(f"\nCross-reference validation failed: {message}")
    raise SystemExit(1)


def validate_cross_references() -> tuple[int, int, int, int]:
    catalog = read_yaml(ROOT / 'catalog.yaml')
    artifacts = read_yaml(ROOT / 'artifacts.yaml')
    sources = read_yaml(ROOT / 'sources.yaml')
    upstreams = read_yaml(ROOT / 'upstreams.yaml')
    benchmarks = read_yaml(ROOT / 'benchmarks.yaml')

    model_ids = {item['id'] for item in catalog.get('models', [])}
    artifact_ids = {item['id'] for item in artifacts.get('artifacts', [])}
    source_ids = {item['id'] for item in sources.get('sources', [])}
    upstream_items = flatten_upstreams(upstreams)
    upstream_ids = {item['id'] for item in upstream_items}

    for model in catalog.get('models', []):
        artifact_ref = model.get('artifact_ref')
        if artifact_ref not in artifact_ids:
            fail(f"model {model['id']} points to missing artifact_ref {artifact_ref}")
        for source_id in model.get('sources', []):
            if source_id not in source_ids and source_id not in upstream_ids:
                fail(f"model {model['id']} points to missing source {source_id}")

    for artifact in artifacts.get('artifacts', []):
        github = artifact.get('github', {}) or {}
        path = github.get('path')
        owner, repo = github.get('owner'), github.get('repo')
        if isinstance(path, str) and path.startswith('https://github.com/'):
            if f'{owner}/{repo}' not in path:
                fail(
                    f"artifact {artifact['id']} github.path {path} "
                    f"is inconsistent with owner/repo {owner}/{repo}"
                )

    for benchmark in benchmarks.get('benchmarks', []):
        model_id = benchmark.get('model_id')
        if model_id not in model_ids:
            fail(f"benchmark {benchmark['id']} points to missing model_id {model_id}")
        source_id = benchmark.get('source')
        if source_id not in source_ids and source_id not in upstream_ids:
            fail(f"benchmark {benchmark['id']} points to missing source {source_id}")

    original_model_sources = upstreams.get('original_model_sources', []) or []
    for upstream in original_model_sources:
        for target in upstream.get('applies_to', []) or []:
            if target not in model_ids and target not in artifact_ids:
                fail(f"original model upstream {upstream['id']} applies_to missing target {target}")

    return len(model_ids), len(artifact_ids), len(upstream_ids), len(benchmarks.get('benchmarks', []))


def main() -> None:
    validate_file(ROOT / 'catalog.yaml', ROOT / 'schema' / 'model.schema.json', 'models')
    validate_file(ROOT / 'artifacts.yaml', ROOT / 'schema' / 'artifact.schema.json', 'artifacts')
    validate_file(ROOT / 'benchmarks.yaml', ROOT / 'schema' / 'benchmark.schema.json', 'benchmarks')

    upstream_data = read_yaml(ROOT / 'upstreams.yaml')
    validate_items(flatten_upstreams(upstream_data), ROOT / 'schema' / 'upstream.schema.json', 'upstream')

    models, artifacts, upstreams, benchmarks = validate_cross_references()
    print(f'OK: {models} models, {artifacts} artifacts, {upstreams} upstreams and {benchmarks} benchmarks validated.')


if __name__ == '__main__':
    main()
