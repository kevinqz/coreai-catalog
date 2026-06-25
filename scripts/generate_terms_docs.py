from __future__ import annotations
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'

LAYER_ORDER = [
    'system_surface',
    'developer_framework',
    'model_provider',
    'provider_protocol',
    'ai_primitive',
    'artifact_format',
    'developer_tool',
    'model',
]
LAYER_LABEL = {
    'system_surface': 'System surfaces',
    'developer_framework': 'Developer frameworks',
    'model_provider': 'Model providers',
    'provider_protocol': 'Provider protocols',
    'ai_primitive': 'AI primitives',
    'artifact_format': 'Artifact formats',
    'developer_tool': 'Developer tools',
    'model': 'Models',
}


def main() -> None:
    data = yaml.safe_load((ROOT / 'terms.yaml').read_text()) or {}
    terms = data.get('terms', [])
    DOCS.mkdir(exist_ok=True)
    lines = [
        '# Apple Terminology Map',
        '',
        'Generated from `terms.yaml`. Verified Apple AI terminology, grouped by ecosystem layer.',
        '',
        'Every term cites an official Apple source. This is a reference layer, not legal or'
        ' affiliation claims; see the README scope and disclaimer.',
    ]
    for layer in LAYER_ORDER:
        rows = [t for t in terms if t.get('apple_layer') == layer]
        if not rows:
            continue
        lines += ['', f'## {LAYER_LABEL[layer]}', '',
                  '| Term | Definition | Verification | Source |',
                  '|---|---|---|---|']
        for t in sorted(rows, key=lambda x: x['id']):
            src = f"[link]({t['official_source']})"
            lines.append(
                f"| {t['label']} | {t['definition']} | {t['verification']} | {src} |"
            )
    (DOCS / 'apple-terminology-map.md').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
