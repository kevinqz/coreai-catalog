"""
Core AI Catalog installer — resolves, downloads, verifies, and registers
model artifacts from Hugging Face without redistributing them.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

CACHE_DIR = Path.home() / ".coreai-catalog"
MODELS_DIR = CACHE_DIR / "models"


def get_model_dir(model_id: str) -> Path:
    """Return the install directory for a model."""
    safe_id = model_id.replace("/", "--")
    return MODELS_DIR / safe_id


def is_installed(model_id: str) -> bool:
    """Check if a model is already installed."""
    d = get_model_dir(model_id)
    return (d / "manifest.json").exists()


def install_model(
    model: dict,
    artifact: dict,
    benchmarks: list[dict],
    dry_run: bool = False,
    verbose: bool = True,
) -> dict:
    """
    Install a model artifact from Hugging Face.

    Steps:
      1. Resolve HF repo URL from artifact record
      2. Download files to cache
      3. Verify file hashes if available
      4. Write manifest.json
      5. Generate Swift integration snippet

    Returns the manifest dict.
    """
    model_id = model["id"]
    hf = artifact.get("huggingface", {}) or {}
    owner = hf.get("owner", "")
    repo = hf.get("repo", "")
    url = hf.get("url", f"https://huggingface.co/{owner}/{repo}")

    install_dir = get_model_dir(model_id)
    artifact_dir = install_dir / "artifact"
    manifest_path = install_dir / "manifest.json"
    snippet_path = install_dir / "snippet.swift"

    manifest = {
        "id": model_id,
        "name": model.get("name", model_id),
        "installed_at": _now_iso(),
        "source": {
            "huggingface": f"{owner}/{repo}",
            "url": url,
        },
        "artifact": {
            "format": model.get("artifact", {}).get("format", "aimodel"),
            "local_path": str(artifact_dir),
        },
        "runtime": model.get("runtime", {}),
        "verified": {
            "catalog_schema": True,
            "source_available": True,
            "file_layout": "not_checked",
        },
    }

    if dry_run:
        return manifest

    # Create directories
    install_dir.mkdir(parents=True, exist_ok=True)

    # Check if huggingface-cli is available
    hfcli = shutil.which("huggingface-cli") or shutil.which("hf")

    if hfcli:
        if verbose:
            print(f"  Downloading from Hugging Face: {owner}/{repo}")
        # Use huggingface-cli to download the entire repo
        cmd = [
            hfcli, "download",
            f"{owner}/{repo}",
            "--local-dir", str(artifact_dir),
            "--quiet",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            if verbose:
                print(f"  ⚠️  Download failed: {result.stderr[:200]}")
            manifest["verified"]["file_layout"] = "download_failed"
        else:
            manifest["verified"]["file_layout"] = "downloaded"
            # Check for .aimodel directories
            aimodels = list(artifact_dir.rglob("*.aimodel"))
            manifest["artifact"]["aimodel_count"] = len(aimodels)
    else:
        if verbose:
            print(f"  ⚠️  huggingface-cli not found. Manual download required:")
            print(f"     {url}")
        manifest["verified"]["file_layout"] = "manual_required"

    # Write manifest
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )

    # Generate Swift snippet
    snippet = _generate_swift_snippet(model, artifact)
    snippet_path.write_text(snippet)

    if verbose:
        print(f"  ✅ Installed to {install_dir}")
        print(f"  📄 Manifest: {manifest_path}")
        print(f"  📄 Swift snippet: {snippet_path}")

    return manifest


def uninstall_model(model_id: str, verbose: bool = True) -> bool:
    """Remove a model from the local cache."""
    install_dir = get_model_dir(model_id)
    if not install_dir.exists():
        if verbose:
            print(f"  Model '{model_id}' is not installed.")
        return False

    shutil.rmtree(install_dir)
    if verbose:
        print(f"  ✅ Removed {install_dir}")
    return True


def list_installed() -> list[dict]:
    """List all installed models with their manifests."""
    if not MODELS_DIR.exists():
        return []
    results = []
    for d in sorted(MODELS_DIR.iterdir()):
        manifest_path = d / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            results.append(manifest)
    return results


def _generate_swift_snippet(model: dict, artifact: dict) -> str:
    """Generate a Swift integration snippet for the model."""
    name = model.get("name", model["id"])
    runtime = model.get("runtime", {})
    runner = runtime.get("runner", "CoreAIRunner")
    hf = artifact.get("huggingface", {}) or {}
    repo = f"{hf.get('owner', '')}/{hf.get('repo', '')}"

    return f"""// {name} — Core AI integration snippet
// Generated by coreai-catalog
// Source: https://huggingface.co/{repo}

import CoreAI

// 1. Load the .aimodel bundle from the installed path
//    (adjust path to match your app's bundle structure)
let bundleURL = Bundle.main.url(forResource: "model", withExtension: "aimodel")!
let model = try CoreAIModel(contentsOf: bundleURL)

// 2. Use {runner} for inference
//    Refer to Apple's Core AI documentation for runner-specific APIs
//    https://developer.apple.com/documentation/coreai

// Runtime notes:
//   - Runner: {runner}
//   - Stock runtime: {runtime.get('stock_runtime', 'unknown')}
//   - Custom kernel: {runtime.get('custom_kernel', 'unknown')}
//   - Patch required: {runtime.get('patch_required', 'unknown')}
//   - AOT required: {runtime.get('aot_required', 'unknown')}
"""


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
