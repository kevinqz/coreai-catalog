#!/usr/bin/env python3
"""Doc-test: validate documentation examples and templates against schemas.

Guards against docs drifting from the enforced contract (redteam findings
A3/A4/A10/F2): every fenced ``yaml``/``json``/``jsonl`` example in
CONTRIBUTING.md and AGENTS.md that is tagged with an entity type is
validated against the matching JSON Schema, and every file in ``templates/``
is validated against its schema.

Tag an example by placing a marker comment on the line before the fence:

    <!-- doc-test: model -->
    ```yaml
    - id: my-model-1b
      ...
    ```

Recognized entities map to ``schema/<entity>.schema.json`` (``model``,
``artifact``, ``benchmark``, ``upstream``, ``term``, ...).

Additionally, discovery surfaces (README, llms.txt, PROJECT_PHILOSOPHY,
copilot-instructions, docs/, templates/, skills/) are scanned for references
to retired stores/scripts (``benchmarks.yaml``, ``check_sources.sh``) so
stale instructions cannot silently reappear.

Errors are aggregated (never fail-fast) and printed with file + entity
context. Exit code 0 = everything valid.

Usage:
    python scripts/doc_test.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / 'schema'
TEMPLATE_DIR = ROOT / 'templates'

DOC_FILES = ['CONTRIBUTING.md', 'AGENTS.md']

#: Strings that must never reappear on discovery surfaces (redteam A10/F2:
#: docs directing contributors at retired stores/scripts become CI-failing
#: instructions — audit.py category 11 hard-fails if benchmarks.yaml returns).
RETIRED_REFERENCES = ['benchmarks.yaml', 'check_sources.sh']

#: Discovery surfaces scanned for retired references. CHANGELOG.md is
#: excluded (historical record), as are generated outputs (dist/, docs/
#: files listed as generated) — the sources that feed them are scanned.
RETIRED_SCAN_FILES = [
    'README.md', 'CONTRIBUTING.md', 'AGENTS.md', 'PROJECT_PHILOSOPHY.md',
    'SECURITY.md', 'CREDITS.md', 'llms.txt', 'llms-full.txt',
    '.github/copilot-instructions.md',
]
RETIRED_SCAN_GLOBS = ['docs/*.md', 'docs/concepts/*.md', 'templates/*', 'skills/**/*.md']

#: A line mentioning a retired reference is allowed when it explains the
#: retirement itself (e.g. the audit-guard note "benchmarks.yaml is retired").
RETIRED_ALLOW_MARKERS = ['retired', 'replaced benchmarks.yaml', 'legacy']

MARKER_RE = re.compile(r'<!--\s*doc-test:\s*([\w-]+)\s*-->')
FENCE_RE = re.compile(r'^```(\w*)')
TEMPLATE_RE = re.compile(r'^([\w-]+)-entry\.(yaml|jsonl|json)$')


def schema_validator(entity: str) -> Draft202012Validator | None:
    schema_path = SCHEMA_DIR / f'{entity}.schema.json'
    if not schema_path.exists():
        return None
    return Draft202012Validator(json.loads(schema_path.read_text()))


def parse_entries(text: str, fmt: str) -> list[dict]:
    """Parse an example block into a list of entries to validate."""
    if fmt == 'yaml':
        data = yaml.safe_load(text)
        entries = data if isinstance(data, list) else [data]
    else:
        # json / jsonl: one object per non-empty, non-comment line, or a
        # single (possibly multi-line) JSON object.
        lines = [
            line for line in text.splitlines()
            if line.strip() and not line.strip().startswith('#')
        ]
        try:
            entries = [json.loads(line) for line in lines]
        except json.JSONDecodeError:
            entries = [json.loads(text)]
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f'expected a mapping, got {type(entry).__name__}')
        entry = dict(entry)
        entry.pop('_signature', None)  # relay signature is not part of the schema
        result.append(entry)
    return result


def validate_entries(entries: list[dict], entity: str, context: str) -> list[str]:
    errors: list[str] = []
    validator = schema_validator(entity)
    if validator is None:
        return [f'{context}: no schema found for entity "{entity}" (schema/{entity}.schema.json)']
    for entry in entries:
        for e in validator.iter_errors(entry):
            path = '.'.join(str(p) for p in e.path) or '<root>'
            errors.append(f'{context} [{entity} {entry.get("id", "?")}] {path}: {e.message}')
    return errors


def extract_tagged_blocks(path: Path) -> list[tuple[str, str, str, int]]:
    """Return (entity, format, block_text, line_number) for tagged fences."""
    blocks = []
    lines = path.read_text().splitlines()
    i = 0
    while i < len(lines):
        marker = MARKER_RE.search(lines[i])
        if marker:
            entity = marker.group(1)
            # The fence must start within the next 2 lines.
            for j in range(i + 1, min(i + 3, len(lines))):
                fence = FENCE_RE.match(lines[j].strip())
                if fence:
                    fmt = (fence.group(1) or 'yaml').lower()
                    fmt = {'json': 'json', 'jsonl': 'jsonl'}.get(fmt, 'yaml' if fmt in ('', 'yaml', 'yml') else fmt)
                    body: list[str] = []
                    k = j + 1
                    while k < len(lines) and not lines[k].strip().startswith('```'):
                        body.append(lines[k])
                        k += 1
                    blocks.append((entity, fmt, '\n'.join(body), j + 1))
                    i = k
                    break
        i += 1
    return blocks


def check_docs() -> tuple[int, list[str]]:
    count = 0
    errors: list[str] = []
    for doc in DOC_FILES:
        path = ROOT / doc
        if not path.exists():
            continue
        for entity, fmt, body, lineno in extract_tagged_blocks(path):
            context = f'{doc}:{lineno}'
            try:
                entries = parse_entries(body, fmt)
            except Exception as e:  # aggregated, never fail-fast
                errors.append(f'{context} [{entity}] unparseable example: {e}')
                continue
            errors.extend(validate_entries(entries, entity, context))
            count += len(entries)
    return count, errors


def check_templates() -> tuple[int, list[str]]:
    count = 0
    errors: list[str] = []
    for path in sorted(TEMPLATE_DIR.glob('*')):
        m = TEMPLATE_RE.match(path.name)
        if not m:
            continue
        entity = m.group(1)
        fmt = 'yaml' if m.group(2) == 'yaml' else 'jsonl'
        context = f'templates/{path.name}'
        try:
            entries = parse_entries(path.read_text(), fmt)
        except Exception as e:
            errors.append(f'{context} [{entity}] unparseable template: {e}')
            continue
        errors.extend(validate_entries(entries, entity, context))
        count += len(entries)
    return count, errors


def check_retired_references() -> tuple[int, list[str]]:
    """Fail on discovery-surface lines that reference retired stores/scripts."""
    paths: list[Path] = []
    for name in RETIRED_SCAN_FILES:
        path = ROOT / name
        if path.exists():
            paths.append(path)
    for pattern in RETIRED_SCAN_GLOBS:
        paths.extend(p for p in sorted(ROOT.glob(pattern)) if p.is_file())

    count = 0
    errors: list[str] = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        count += 1
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            lowered = line.lower()
            for retired in RETIRED_REFERENCES:
                if retired in lowered and not any(
                    marker in lowered for marker in RETIRED_ALLOW_MARKERS
                ):
                    rel = path.relative_to(ROOT)
                    errors.append(
                        f'{rel}:{lineno} references retired "{retired}" — '
                        'benchmarks live in benchmarks.jsonl and link checks '
                        'in scripts/validate_links.py; update the doc (or add '
                        'a retirement note if the mention is intentional)'
                    )
    return count, errors


def main() -> None:
    doc_count, doc_errors = check_docs()
    tpl_count, tpl_errors = check_templates()
    retired_count, retired_errors = check_retired_references()
    errors = doc_errors + tpl_errors + retired_errors

    if doc_count == 0:
        errors.append(
            'No tagged examples found in ' + ', '.join(DOC_FILES)
            + ' — expected at least one `<!-- doc-test: ... -->` block.'
        )
    if tpl_count == 0:
        errors.append('No templates found in templates/ — expected *-entry.{yaml,jsonl}.')

    if errors:
        print(f'Doc-test FAILED with {len(errors)} error(s):\n')
        for error in errors:
            print(f'  - {error}')
        raise SystemExit(1)

    print(
        f'OK: {doc_count} documentation example(s) and {tpl_count} template '
        f'entr(y/ies) validated against schemas; {retired_count} discovery '
        'surface(s) free of retired references.'
    )


if __name__ == '__main__':
    main()
