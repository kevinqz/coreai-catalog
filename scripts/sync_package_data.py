#!/usr/bin/env python3
"""Sync YAML source files into coreai_catalog/data/ for pip packaging.

Run before `python -m build` to ensure the wheel includes current data.
Called automatically by generate.py when --json is used, or manually.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
PKG_DATA = ROOT / "coreai_catalog" / "data"
YAML_FILES = ["catalog.yaml", "artifacts.yaml", "benchmarks.yaml",
              "sources.yaml", "upstreams.yaml", "terms.yaml"]

def main():
    PKG_DATA.mkdir(parents=True, exist_ok=True)
    for name in YAML_FILES:
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, PKG_DATA / name)
            print(f"  synced {name}")
    # Copy schema files
    schema_src = ROOT / "schema"
    schema_dst = PKG_DATA / "schema"
    if schema_src.exists():
        schema_dst.mkdir(parents=True, exist_ok=True)
        for sf in schema_src.glob("*.json"):
            shutil.copy2(sf, schema_dst / sf.name)
            print(f"  synced schema/{sf.name}")

if __name__ == "__main__":
    main()
