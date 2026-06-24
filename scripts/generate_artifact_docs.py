from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT / "artifacts"
DOCS_DIR = ROOT / "docs"
OUTPUT_PATH = DOCS_DIR / "artifact-provenance.md"


def load_artifact_files() -> list[tuple[str, dict]]:
    items: list[tuple[str, dict]] = []
    for path in sorted(ARTIFACTS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text()) or {}
        items.append((path.name, data))
    return items


def main() -> None:
    DOCS_DIR.mkdir(exist_ok=True)
    rows = [
        "# Artifact Provenance",
        "",
        "Generated from files in `artifacts/`.",
        "",
        "| File | Group | GitHub | HF Owner | Artifact IDs |",
        "|---|---|---|---|---|",
    ]

    for filename, data in load_artifact_files():
        group = data.get("group", data.get("source_group", "unknown"))
        credit = data.get("credit", {})
        github = "/".join(
            part for part in [credit.get("github_owner"), credit.get("github_repo")] if part
        ) or "unknown"
        hf_owner = data.get("hf_owner") or credit.get("hf_owner") or "unknown"
        artifacts = data.get("artifacts") or []
        items = data.get("items") or {}
        ids: list[str] = []
        if isinstance(artifacts, list):
            ids.extend(str(item.get("id")) for item in artifacts if isinstance(item, dict) and item.get("id"))
        if isinstance(items, dict):
            ids.extend(str(k) for k in items.keys())
        rows.append(f"| `{filename}` | `{group}` | `{github}` | `{hf_owner}` | {', '.join(ids) or 'unknown'} |")

    OUTPUT_PATH.write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    main()
