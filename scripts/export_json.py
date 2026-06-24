from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

INPUTS = {
    "catalog": ROOT / "catalog.yaml",
    "artifacts": ROOT / "artifacts.yaml",
    "sources": ROOT / "sources.yaml",
    "upstreams": ROOT / "upstreams.yaml",
    "benchmarks": ROOT / "benchmarks.yaml",
}


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def write_json(name: str, data: dict[str, Any]) -> None:
    DIST.mkdir(exist_ok=True)
    output_path = DIST / f"{name}.json"
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    for name, path in INPUTS.items():
        write_json(name, read_yaml(path))

    bundle = {name: read_yaml(path) for name, path in INPUTS.items()}
    write_json("coreai-catalog", bundle)


if __name__ == "__main__":
    main()
