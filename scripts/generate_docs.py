from __future__ import annotations
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs'
def fmt(v): return ', '.join(str(x) for x in (v or []))
def dev(ds):
    out=[]
    if ds.get('iphone') is True: out.append('iPhone')
    if ds.get('ipad') is True: out.append('iPad')
    if ds.get('mac') is True: out.append('Mac')
    return '/'.join(out) or 'unknown'
def main():
    data=yaml.safe_load((ROOT/'catalog.yaml').read_text())
    DOCS.mkdir(exist_ok=True)
    lines=['# Model Registry','','| ID | Model | Group | Family | Capabilities | Input | Output | Size | Device | License | Status |','|---|---|---|---|---|---|---|---|---|---|---|']
    for m in data['models']:
        lines.append(f"| {m['id']} | {m['name']} | {m['source_group']} | {m['family']} | {fmt(m['capabilities'])} | {fmt(m['modalities']['input'])} | {fmt(m['modalities']['output'])} | {m['size'].get('parameters','unknown')} | {dev(m['device_support'])} | {m['license'].get('name','unknown')} | {m['status']} |")
    (DOCS/'model-registry.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__': main()
