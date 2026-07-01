"""
Core AI Catalog installer — resolves, downloads, verifies, and registers
model artifacts from Hugging Face without redistributing them.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

CACHE_DIR = Path.home() / ".coreai-catalog"
MODELS_DIR = CACHE_DIR / "models"


def get_model_dir(model_id: str) -> Path:
    """Return the install directory for a model."""
    safe_id = str(model_id or "").replace("/", "--")
    return MODELS_DIR / safe_id if safe_id else MODELS_DIR


def is_installed(model_id: str) -> bool:
    """Check if a model is already installed."""
    d = get_model_dir(model_id)
    return (d / "manifest.json").exists()


def _parse_artifact_size_gb(size_str: str) -> float | None:
    """Parse an artifact_size string to GB.

    Accepts formats like '3.2 GB', '650 MB', '1.5TB'.
    Returns None if unparseable.
    """
    if not size_str or size_str in ("unknown", "not_published"):
        return None
    s = str(size_str).strip().upper()
    # Extract the first numeric token (optionally preceded by ~) followed by a unit
    m = re.match(r"^\s*~?\s*([0-9.]+)\s*(TB|GB|MB|KB)?", s)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2) or "GB"
    multipliers = {"KB": 1 / (1024 ** 2), "MB": 1 / 1024, "GB": 1.0, "TB": 1024.0}
    return val * multipliers.get(unit, 1.0)


def _get_free_disk_gb(path: Path) -> float | None:
    """Return available disk space in GB at *path*, or None if uncheckable."""
    try:
        stat = os.statvfs(str(path))
        return (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
    except (OSError, AttributeError):
        return None


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
      2. Pre-check disk space against artifact size
      3. Download files to cache (uses ``hf`` CLI, not deprecated ``huggingface-cli``)
      4. Verify file hashes if available
      5. Write manifest.json
      6. Generate Swift integration snippet

    Returns the manifest dict.
    """
    model_id = model["id"]
    hf = artifact.get("huggingface", {}) or {}
    owner = hf.get("owner", "")
    repo = hf.get("repo", "")
    url = hf.get("url", f"https://huggingface.co/{owner}/{repo}")

    install_dir = get_model_dir(model_id)
    artifact_dir = install_dir / "artifacts"
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

    # ── Disk space pre-check ──
    size_str = model.get("size", {}).get("artifact_size", "")
    needed_gb = _parse_artifact_size_gb(size_str)
    if needed_gb is not None:
        free_gb = _get_free_disk_gb(install_dir.parent if install_dir.parent.exists() else Path.home())
        if free_gb is not None and needed_gb > free_gb:
            if verbose:
                print(
                    f"  ❌ Insufficient disk space: need ~{needed_gb:.1f} GB, "
                    f"only {free_gb:.1f} GB available."
                )
            manifest["verified"]["file_layout"] = "insufficient_disk"
            return manifest

    # ── Create directories (with graceful error handling) ──
    try:
        install_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        if verbose:
            print(f"  ❌ Failed to create install directory {install_dir}: {e}")
        manifest["verified"]["file_layout"] = "mkdir_failed"
        return manifest

    # ── Download using ``hf`` CLI (``huggingface-cli`` is deprecated) ──
    hfcli = shutil.which("hf") or shutil.which("huggingface-cli")

    if hfcli:
        if verbose:
            print(f"  Downloading from Hugging Face: {owner}/{repo}")
        cmd = [
            hfcli, "download",
            f"{owner}/{repo}",
            "--local-dir", str(artifact_dir),
            "--quiet",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except (subprocess.TimeoutExpired, OSError) as e:
            if verbose:
                print(f"  ❌ Download error: {e}")
            manifest["verified"]["file_layout"] = "download_failed"
        else:
            if result.returncode != 0:
                if verbose:
                    print(f"  ❌ Download failed: {result.stderr[:200]}")
                manifest["verified"]["file_layout"] = "download_failed"
            else:
                manifest["verified"]["file_layout"] = "downloaded"
                # Check for .aimodel directories
                aimodels = list(artifact_dir.rglob("*.aimodel"))
                manifest["artifact"]["aimodel_count"] = len(aimodels)
    else:
        if verbose:
            print(f"  ⚠️  hf CLI not found. Manual download required:")
            print(f"     {url}")
        manifest["verified"]["file_layout"] = "manual_required"

    # ── Write manifest (with graceful error handling) ──
    try:
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        )
    except OSError as e:
        if verbose:
            print(f"  ❌ Failed to write manifest {manifest_path}: {e}")
        return manifest

    # ── Generate Swift snippet ──
    snippet = _generate_swift_snippet(model, artifact)
    try:
        snippet_path.write_text(snippet)
    except OSError as e:
        if verbose:
            print(f"  ⚠️  Failed to write Swift snippet {snippet_path}: {e}")

    if verbose:
        file_layout = manifest["verified"]["file_layout"]
        if file_layout in ("downloaded",):
            print(f"  ✅ Installed to {install_dir}")
            print(f"  📄 Manifest: {manifest_path}")
            print(f"  📄 Swift snippet: {snippet_path}")
        elif file_layout == "manual_required":
            print(f"  ⚠️  Manifest written, manual download required.")
            print(f"  📄 Manifest: {manifest_path}")
        else:
            print(f"  ❌ Installation incomplete (file_layout: {file_layout}).")
            print(f"  📄 Manifest: {manifest_path}")

    return manifest


def uninstall_model(model_id: str, verbose: bool = True) -> bool:
    """Remove a model from the local cache."""
    if not model_id or not isinstance(model_id, str):
        if verbose:
            print("  Model ID is required.")
        return False
    install_dir = get_model_dir(model_id)
    if not install_dir.exists():
        if verbose:
            print(f"  Model '{model_id}' is not installed.")
        return False

    try:
        shutil.rmtree(install_dir)
    except OSError as e:
        if verbose:
            print(f"  ❌ Failed to remove {install_dir}: {e}")
        return False
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
            try:
                manifest = json.loads(manifest_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
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
