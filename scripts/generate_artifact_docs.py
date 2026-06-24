from __future__ import annotations
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs'
def main():
    data=yaml.safe_load((ROOT/'artifacts.yaml').read_text())
    DOCS.mkdir(exist_ok=True)
    lines=['# Artifact Provenance','','Generated from `artifacts.yaml`.','','| ID | Group | GitHub | Hugging Face | Official Recipe |','|---|---|---|---|---|']
    for a in data['artifacts']:
        gh=f"{a['github']['owner']}/{a['github']['repo']}"
        hf=f"{a['huggingface']['owner']}/{a['huggingface']['repo']}"
        lines.append(f"| {a['id']} | {a['group']} | {gh} | {hf} | {a['is_official_recipe']} |")
    (DOCS/'artifact-provenance.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__': main()
