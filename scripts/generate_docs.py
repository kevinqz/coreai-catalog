from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog.yaml"
DOCS_DIR = ROOT / "docs"


def fmt_list(value):
    return ", ".join(str(v) for v in (value or []))


def device_label(device_support):
    devices = []
    if device_support.get("iphone") is True:
        devices.append("iPhone")
    if device_support.get("ipad") is True:
        devices.append("iPad")
    if device_support.get("mac") is True:
        devices.append("Mac")
    return "/".join(devices) or "unknown"


def main() -> None:
    catalog = yaml.safe_load(CATALOG_PATH.read_text())
    models = catalog.get("models", [])
    DOCS_DIR.mkdir(exist_ok=True)

    lines = [
        "# Model Registry",
        "",
        "| ID | Model | Group | Family | Capabilities | Input | Output | Size | Device | License | Status |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for model in models:
        lines.append(
            "| {id} | {name} | {group} | {family} | {caps} | {inputs} | {outputs} | {size} | {device} | {license} | {status} |".format(
                id=model.get("id", ""),
                name=model.get("name", ""),
                group=model.get("source_group", ""),
                family=model.get("family", ""),
                caps=fmt_list(model.get("capabilities", [])),
                inputs=fmt_list(model.get("modalities", {}).get("input", [])),
                outputs=fmt_list(model.get("modalities", {}).get("output", [])),
                size=model.get("size", {}).get("parameters", "unknown"),
                device=device_label(model.get("device_support", {})),
                license=model.get("license", {}).get("name", "unknown"),
                status=model.get("status", "unknown"),
            )
        )

    (DOCS_DIR / "model-registry.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
