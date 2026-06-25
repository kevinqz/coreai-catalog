from __future__ import annotations
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs'
def main():
    data=yaml.safe_load((ROOT/'artifacts.yaml').read_text())
    DOCS.mkdir(exist_ok=True)
    lines=['# Artifact Provenance','','Generated from `artifacts.yaml`.','','| ID | Group | GitHub | Hugging Face | Apple recipe | Apple-hosted |','|---|---|---|---|---|---|']
    for a in data['artifacts']:
        gh=f"{a['github']['owner']}/{a['github']['repo']}"
        hf=f"{a['huggingface']['owner']}/{a['huggingface']['repo']}"
        off=a['officiality']
        lines.append(f"| {a['id']} | {a['group']} | {gh} | {hf} | {off['apple_export_recipe']} | {off['apple_hosted_artifact']} |")
    (DOCS/'artifact-provenance.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__': main()
