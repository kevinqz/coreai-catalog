#!/usr/bin/env python3
"""Generate templates/ entry files from schema/*.json.

The templates are DERIVED views of the JSON Schemas — never edit them by
hand. Field comments come from schema ``description`` strings; enum values
are listed exactly as the schema enforces them; fields that are not in the
schema's ``required`` list are marked ``optional``. Every generated template
is self-validated against its schema before it is written, so a template
can never teach a value the schema rejects.

Usage:
    python scripts/generate_templates.py           # (re)write templates/
    python scripts/generate_templates.py --check   # fail if templates are stale

Rendered templates:
    schema/model.schema.json     -> templates/model-entry.yaml
    schema/artifact.schema.json  -> templates/artifact-entry.yaml
    schema/benchmark.schema.json -> templates/benchmark-entry.jsonl
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / 'schema'
TEMPLATE_DIR = ROOT / 'templates'

# Fixed date placeholder keeps regeneration idempotent (no daily diffs).
PLACEHOLDER_DATE = '2026-01-01'

# Placeholder values by field name — purely cosmetic hints so the template
# reads well. Structure, required-ness, enums, and comments all come from
# the schema; unknown fields fall back to generic placeholders.
NAME_HINTS = {
    'license.name': 'Apache-2.0',
    'id': 'model-id-here',
    'model_id': 'model-id-here',
    'artifact_ref': 'model-id-here',
    'name': 'Model Display Name',
    'family': 'ModelFamily',
    'owner': 'owner-here',
    'repo': 'repo-name-here',
    'parameters': '1B',
    'precision': 'int8',
    'quantization': 'int8lin',
    'artifact_size': '850MB',
    'capabilities': ['chat', 'text-generation'],
    'input': ['text'],
    'output': ['text'],
    'sources': ['coreai-model-zoo-readme'],
    'source': 'coreai-model-zoo-readme',
    'device_class': 'A18 Pro',
    'os_major': '27',
    'value': 52.3,
    'notes': 'One-line description or caveats.',
    'sha256': 'sha256-hex-digest-here',
    'revision': 'hf-commit-sha-here',
    'version': 'tool-version-here',
    'tool': 'tool-name-here',
    'format_version': 'format-version-here',
}


def field_comment(name: str, spec: dict, required: bool) -> str:
    """Build the trailing comment for a field: description + exact enums."""
    parts: list[str] = []
    enum = spec.get('enum')
    if enum is not None:
        rendered = ' | '.join(
            'true' if v is True else 'false' if v is False else str(v)
            for v in enum
        )
        parts.append(rendered)
    desc = spec.get('description')
    if desc:
        parts.append(desc)
    if not required:
        parts.append('optional')
    return ' — '.join(parts) if len(parts) > 1 and desc else '; '.join(parts)


def placeholder(name: str, spec: dict, parent: str = '') -> object:
    """Synthesize a schema-valid placeholder value for a property."""
    if 'default' in spec:
        return spec['default']
    if spec.get('examples'):
        return spec['examples'][0]
    enum = spec.get('enum')
    if enum is not None:
        # Prefer a non-"unknown" value so templates model good entries.
        for v in enum:
            if v != 'unknown':
                return v
        return enum[0]

    hint = NAME_HINTS.get(f'{parent}.{name}' if parent else name, NAME_HINTS.get(name))

    types = spec.get('type', 'string')
    if isinstance(types, list):
        # e.g. ["string", "null"] or ["boolean", "string"]
        types = [t for t in types if t != 'null'] or ['string']
        type_ = types[0]
    else:
        type_ = types

    if type_ == 'object':
        return {
            key: placeholder(key, sub, parent=name)
            for key, sub in (spec.get('properties') or {}).items()
        }
    if type_ == 'array':
        if isinstance(hint, list):
            return hint
        items = spec.get('items') or {'type': 'string'}
        return [placeholder(name, items, parent=parent)]
    if type_ == 'boolean':
        return hint if isinstance(hint, bool) else False
    if type_ == 'integer':
        return hint if isinstance(hint, int) else 1
    if type_ == 'number':
        return hint if isinstance(hint, (int, float)) else 1.0

    # Strings: honour patterns first, then name hints.
    pattern = spec.get('pattern', '')
    if pattern:
        value = string_for_pattern(pattern)
        if value is not None:
            return value
    if isinstance(hint, str):
        return hint
    return 'replace-me'


def string_for_pattern(pattern: str) -> str | None:
    """Synthesize a string matching common schema patterns."""
    import re

    if pattern.startswith('^\\d{4}-\\d{2}-\\d{2}'):
        return PLACEHOLDER_DATE
    if pattern.startswith('^https://'):
        return 'https://example.com/replace-me'
    # Fixed-length character classes, e.g. ^[0-9a-f]{40}$ (git shas, digests).
    m = re.fullmatch(r'\^\[([^\]]+)\]\{(\d+)\}\$', pattern)
    if m:
        char_class, length = m.group(1), int(m.group(2))
        first = char_class[0]
        candidate = first * length
        if re.fullmatch(pattern.strip('^$'), candidate):
            return candidate
    return None


def _bare_reinterprets_as_non_string(text: str) -> bool:
    """True if YAML would reparse a bare ``text`` as a non-string, or if the
    bare form does not parse at all as a plain scalar.

    A value containing ``: `` (e.g. a Swift call ``CoreAILanguageModel(
    resourcesAt: url)``) makes ``v: <text>`` ambiguous YAML and raises a
    scanner error — which means it must be quoted, not that generation should
    crash.
    """
    try:
        return not isinstance(yaml.safe_load(f'v: {text}')['v'], str)
    except yaml.YAMLError:
        return True


def fmt_scalar(value: object) -> str:
    """Render a scalar for YAML output, quoting where load-bearing."""
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if value is None:
        return 'null'
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    # Quote strings YAML would reinterpret (dates, numbers, specials).
    needs_quote = (
        text == ''
        or text != yaml.safe_load(yaml.safe_dump(text)).__str__()
        or _bare_reinterprets_as_non_string(text)
        or ':' in text
        or text.startswith(('#', '-', '*', '&', '!', '[', '{', '>', '|', '@'))
    )
    return f"'{text}'" if needs_quote else text


def render_yaml_object(
    spec: dict, key_col: int, lines: list[str], list_item: bool = False,
    parent: str = '',
) -> None:
    """Render an object's properties as commented YAML lines.

    ``key_col`` is the column where each key begins. When ``list_item`` is
    true, the first key is prefixed with ``- `` (list-entry style).
    """
    props = spec.get('properties') or {}
    required = set(spec.get('required') or [])
    first = True
    for name, sub in props.items():
        if list_item and first:
            lead = ' ' * (key_col - 2) + '- '
        else:
            lead = ' ' * key_col
        first = False
        comment = field_comment(name, sub, name in required)
        suffix = f'   # {comment}' if comment else ''

        types = sub.get('type', 'string')
        type_list = types if isinstance(types, list) else [types]

        if 'object' in type_list and 'enum' not in sub:
            lines.append(f'{lead}{name}:{suffix}')
            render_yaml_object(sub, key_col + 2, lines, parent=name)
        elif 'array' in type_list:
            items = sub.get('items') or {'type': 'string'}
            item_types = items.get('type', 'string')
            item_types = item_types if isinstance(item_types, list) else [item_types]
            lines.append(f'{lead}{name}:{suffix}')
            if 'object' in item_types:
                render_yaml_object(items, key_col + 2, lines, list_item=True, parent=name)
            else:
                value = placeholder(name, sub, parent=parent)
                for item in value if isinstance(value, list) else [value]:
                    lines.append(f'{" " * key_col}- {fmt_scalar(item)}')
        else:
            value = placeholder(name, sub, parent=parent)
            lines.append(f'{lead}{name}: {fmt_scalar(value)}{suffix}')


def header(schema_file: str, target: str) -> list[str]:
    return [
        f'# GENERATED from schema/{schema_file} by scripts/generate_templates.py.',
        '# Do not edit by hand — edit the schema and re-run the generator.',
        f'# {target}',
        '# Fields marked "optional" may be omitted entirely; never invent values',
        '# for fields you cannot source (leave optional fields absent instead).',
    ]


def render_yaml_template(schema: dict, schema_file: str, target: str) -> str:
    lines = header(schema_file, target)
    body: list[str] = []
    render_yaml_object(schema, 2, body, list_item=True)
    return '\n'.join(lines + [''] + body) + '\n'


def render_jsonl_template(schema: dict, schema_file: str, target: str) -> str:
    lines = header(schema_file, target)
    lines.append('# Field reference (see the schema for authoritative definitions):')
    props = schema.get('properties') or {}
    required = set(schema.get('required') or [])
    for name, sub in props.items():
        comment = field_comment(name, sub, name in required)
        lines.append(f'#   {name}: {comment}' if comment else f'#   {name}')
    entry = {name: placeholder(name, sub) for name, sub in props.items()}
    lines.append(json.dumps(entry, ensure_ascii=False))
    return '\n'.join(lines) + '\n'


TEMPLATES = [
    (
        'model.schema.json',
        'model-entry.yaml',
        'Copy this entry, fill in the fields, and append to catalog.yaml under `models:`.',
    ),
    (
        'artifact.schema.json',
        'artifact-entry.yaml',
        'Copy this entry, append to artifacts.yaml under `artifacts:` (id must match '
        'the catalog.yaml artifact_ref) and bump metadata.count by 1.',
    ),
    (
        'benchmark.schema.json',
        'benchmark-entry.jsonl',
        'Append ONE line like the last line of this file to benchmarks.jsonl '
        '(dedicated PR — one added line, no other changes).',
    ),
]


def load_entries(path: Path, text: str) -> list[dict]:
    """Parse a rendered template back into entries for self-validation."""
    if path.suffix == '.jsonl':
        return [
            json.loads(line)
            for line in text.splitlines()
            if line.strip() and not line.startswith('#')
        ]
    data = yaml.safe_load(text)
    return data if isinstance(data, list) else [data]


def build() -> dict[Path, str]:
    rendered: dict[Path, str] = {}
    for schema_file, template_file, target in TEMPLATES:
        schema_path = SCHEMA_DIR / schema_file
        schema = json.loads(schema_path.read_text())
        out_path = TEMPLATE_DIR / template_file
        if template_file.endswith('.jsonl'):
            text = render_jsonl_template(schema, schema_file, target)
        else:
            text = render_yaml_template(schema, schema_file, target)

        # Self-check: the template must validate against its own schema.
        validator = Draft202012Validator(schema)
        for entry in load_entries(out_path, text):
            entry.pop('_signature', None)
            errors = list(validator.iter_errors(entry))
            if errors:
                print(f'Generated template {template_file} does not satisfy {schema_file}:')
                for e in errors:
                    path = '.'.join(str(p) for p in e.path)
                    print(f'  - {path}: {e.message}')
                raise SystemExit(1)
        rendered[out_path] = text
    return rendered


def main() -> None:
    check = '--check' in sys.argv[1:]
    rendered = build()
    stale: list[str] = []
    for path, text in rendered.items():
        rel = path.relative_to(ROOT)
        if check:
            current = path.read_text() if path.exists() else ''
            if current != text:
                stale.append(str(rel))
            else:
                print(f'OK: {rel} is in sync with its schema.')
        else:
            TEMPLATE_DIR.mkdir(exist_ok=True)
            path.write_text(text)
            print(f'Wrote {rel}')
    if stale:
        print(
            '\nStale templates (re-run `python scripts/generate_templates.py`): '
            + ', '.join(stale)
        )
        raise SystemExit(1)


if __name__ == '__main__':
    main()
