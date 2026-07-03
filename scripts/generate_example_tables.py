#!/usr/bin/env python3
"""Generate example capability tables in examples/*/README.md from catalog.yaml.

The old conceptual examples hand-wrote capability tables that contradicted
the catalog (redteam findings C4: wrong license/architecture for the OCR
model; C10: capability claims absent from catalog.yaml). This script makes
the example READMEs DERIVED views: every value in a capability table comes
verbatim from catalog.yaml / artifacts.yaml, so an example can never claim
something the catalog does not.

Each examples/*/README.md may contain one or more marker blocks:

    <!-- BEGIN GENERATED: capability-table model=<model-id> -->
    ...replaced content...
    <!-- END GENERATED: capability-table -->

Usage:
    python scripts/generate_example_tables.py           # (re)write READMEs
    python scripts/generate_example_tables.py --check   # fail if stale

Exit codes: 0 = OK / in sync; 1 = stale (--check) or unknown model id.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'catalog.yaml'
ARTIFACTS = ROOT / 'artifacts.yaml'
EXAMPLES_DIR = ROOT / 'examples'

BLOCK_RE = re.compile(
    r'(<!-- BEGIN GENERATED: capability-table model=(?P<model_id>[A-Za-z0-9._-]+) -->)'
    r'(?P<body>.*?)'
    r'(<!-- END GENERATED: capability-table -->)',
    re.DOTALL,
)


def _fmt(value) -> str:
    """Render a catalog scalar for a markdown cell without inventing data."""
    if value is None:
        return 'unknown'
    if value is True:
        return 'yes'
    if value is False:
        return 'no'
    return str(value)


def _devices(device_support: dict) -> str:
    parts = []
    for key, label in (('iphone', 'iPhone'), ('ipad', 'iPad'), ('mac', 'Mac')):
        if key in device_support:
            parts.append(f'{label}: {_fmt(device_support[key])}')
    return ' · '.join(parts) if parts else 'unknown'


def render_table(model: dict, artifact: dict | None) -> str:
    """Render one capability table. Every value is copied from the catalog."""
    license_ = model.get('license', {}) or {}
    size = model.get('size', {}) or {}
    runtime = model.get('runtime', {}) or {}
    modalities = model.get('modalities', {}) or {}

    rows: list[tuple[str, str]] = [
        ('Model', f"{model.get('name', model['id'])} (`{model['id']}`)"),
        ('Capabilities', ', '.join(model.get('capabilities', [])) or 'unknown'),
        ('Inputs', ', '.join(modalities.get('input', [])) or 'unknown'),
        ('Outputs', ', '.join(modalities.get('output', [])) or 'unknown'),
        ('License', _fmt(license_.get('name'))),
        ('Commercial use', _fmt(license_.get('commercial_use'))),
    ]
    if size.get('parameters'):
        rows.append(('Parameters', _fmt(size.get('parameters'))))
    if size.get('artifact_size'):
        rows.append(('Artifact size', _fmt(size.get('artifact_size'))))
    rows.extend([
        ('Devices', _devices(model.get('device_support', {}) or {})),
        ('Runner', _fmt(runtime.get('runner'))),
        ('Status', f"{_fmt(model.get('status'))} ({_fmt(model.get('maturity'))})"),
        ('Last verified', _fmt(model.get('last_verified'))),
    ])
    hf = (artifact or {}).get('huggingface') or {}
    if hf.get('url'):
        rows.append(('Artifact', hf['url']))

    lines = [
        '',
        '<!-- Generated from catalog.yaml by scripts/generate_example_tables.py',
        '     — do not edit by hand. Run the script to refresh. -->',
        '',
        '| Field | Value (from catalog.yaml) |',
        '|---|---|',
    ]
    lines += [f'| {k} | {v} |' for k, v in rows]
    lines.append('')
    return '\n'.join(lines)


def process_readme(path: Path, models: dict, artifacts: dict) -> tuple[str, list[str]]:
    """Return (new_text, errors) for one README."""
    text = path.read_text()
    errors: list[str] = []

    def _replace(match: re.Match) -> str:
        model_id = match.group('model_id')
        model = models.get(model_id)
        if model is None:
            errors.append(f'{path}: unknown model id {model_id!r} in capability-table marker')
            return match.group(0)
        artifact = artifacts.get(model.get('artifact_ref', model_id))
        return f'{match.group(1)}{render_table(model, artifact)}{match.group(4)}'

    return BLOCK_RE.sub(_replace, text), errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true',
                        help='fail (exit 1) if any README table is stale')
    args = parser.parse_args()

    models = {m['id']: m for m in yaml.safe_load(CATALOG.read_text())['models']}
    artifacts = {a['id']: a for a in yaml.safe_load(ARTIFACTS.read_text())['artifacts']}

    stale: list[Path] = []
    failed = False
    seen_blocks = 0
    for readme in sorted(EXAMPLES_DIR.glob('*/README.md')):
        new_text, errors = process_readme(readme, models, artifacts)
        for err in errors:
            print(f'ERROR: {err}', file=sys.stderr)
            failed = True
        seen_blocks += len(BLOCK_RE.findall(readme.read_text()))
        if new_text != readme.read_text():
            if args.check:
                stale.append(readme)
            else:
                readme.write_text(new_text)
                print(f'updated {readme.relative_to(ROOT)}')

    if seen_blocks == 0:
        print('ERROR: no capability-table marker blocks found under examples/',
              file=sys.stderr)
        failed = True

    if stale:
        for path in stale:
            print(f'STALE: {path.relative_to(ROOT)} — run '
                  f'`python scripts/generate_example_tables.py`', file=sys.stderr)
        return 1
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
