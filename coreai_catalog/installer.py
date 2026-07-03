"""
Core AI Catalog installer — resolves, downloads, and registers model
artifacts from Hugging Face without redistributing them.

Verification is content-addressed and honest:
  - When the catalog records a pinned ``huggingface.revision``, the download
    is pinned to that commit (``hf download --revision``).
  - When the catalog records per-file ``huggingface.files`` sha256 digests,
    each file is hashed (streamed) and compared; any mismatch fails the
    install hard.
  - When no digests are recorded, NO hash check is possible and the manifest
    records ``verification: unavailable`` — it never claims bytes were
    verified when they were not.
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


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute the sha256 hex digest of *path* with streamed (chunked) reads."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file_digests(
    artifact_dir: Path,
    files: list[dict],
    verbose: bool = True,
) -> dict:
    """Verify catalog-recorded sha256 digests against downloaded files.

    *files* is the ``huggingface.files`` list from ``artifacts.yaml``:
    ``[{path, sha256, size_bytes}]``. Every listed file must exist locally
    and hash to the recorded digest; anything else is a hard failure.

    Returns a result dict::

        {
          "status": "verified" | "failed",
          "files_total": int,
          "files_verified": int,
          "mismatched": [str, ...],   # paths whose sha256 differed
          "missing": [str, ...],      # paths absent from the download
        }
    """
    result = {
        "status": "verified",
        "files_total": len(files),
        "files_verified": 0,
        "mismatched": [],
        "missing": [],
    }
    for entry in files:
        rel_path = entry.get("path", "")
        expected = str(entry.get("sha256", "")).lower()
        local = artifact_dir / rel_path
        if not local.is_file():
            result["missing"].append(rel_path)
            continue
        try:
            actual = _sha256_file(local)
        except OSError:
            result["missing"].append(rel_path)
            continue
        if actual != expected:
            result["mismatched"].append(rel_path)
            if verbose:
                print(f"  ❌ sha256 mismatch: {rel_path}")
                print(f"     expected {expected}")
                print(f"     actual   {actual}")
        else:
            result["files_verified"] += 1

    if result["mismatched"] or result["missing"]:
        result["status"] = "failed"
    return result


def install_model(
    model: dict,
    artifact: dict,
    benchmarks: list[dict],
    dry_run: bool = False,
    verbose: bool = True,
    no_verify: bool = False,
) -> dict:
    """
    Install a model artifact from Hugging Face.

    Steps:
      1. Resolve HF repo URL from artifact record
      2. Pre-check disk space against artifact size
      3. Download files to cache (uses ``hf`` CLI, not deprecated
         ``huggingface-cli``), pinned to ``huggingface.revision`` when the
         catalog records one
      4. Verify per-file sha256 digests when the catalog records them
         (streamed hashing); any mismatch or missing file FAILS the install.
         When no digests exist, the manifest records
         ``verification.status: unavailable`` — no hash check is claimed.
         ``no_verify=True`` skips the check (recorded as ``skipped``).
      5. Write manifest.json (verification state recorded truthfully)
      6. Generate Swift integration snippet

    Returns the manifest dict.
    """
    model_id = model["id"]
    hf = artifact.get("huggingface", {}) or {}
    owner = hf.get("owner", "")
    repo = hf.get("repo", "")
    url = hf.get("url", f"https://huggingface.co/{owner}/{repo}")
    revision = hf.get("revision")
    digest_files = hf.get("files") or []

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
            "revision": revision,
        },
        "artifact": {
            "format": model.get("artifact", {}).get("format", "aimodel"),
            "local_path": str(artifact_dir),
        },
        "runtime": model.get("runtime", {}),
        "verified": {
            "catalog_schema": True,
            "source_available": "not_checked",
            "file_layout": "not_checked",
        },
        "verification": {
            "status": "not_checked",
            "revision_pinned": bool(revision),
            "files_total": len(digest_files),
            "files_verified": 0,
        },
        # Which generator the snippet.swift comes from: "io_contract"
        # (typed contract in catalog.yaml) or "runner_bucket" (legacy
        # conceptual template).
        "snippet_source": snippet_source(model),
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
            pin = f" @ {revision[:12]}" if revision else " (unpinned — no revision in catalog)"
            print(f"  Downloading from Hugging Face: {owner}/{repo}{pin}")
        cmd = [hfcli, "download", f"{owner}/{repo}"]
        if revision:
            cmd += ["--revision", revision]
        cmd += ["--local-dir", str(artifact_dir), "--quiet"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except (subprocess.TimeoutExpired, OSError) as e:
            if verbose:
                print(f"  ❌ Download error: {e}")
            manifest["verified"]["file_layout"] = "download_failed"
            manifest["verified"]["source_available"] = False
        else:
            if result.returncode != 0:
                if verbose:
                    print(f"  ❌ Download failed: {result.stderr[:200]}")
                manifest["verified"]["file_layout"] = "download_failed"
                manifest["verified"]["source_available"] = False
            else:
                manifest["verified"]["file_layout"] = "downloaded"
                manifest["verified"]["source_available"] = True
                # Check for .aimodel directories
                aimodels = list(artifact_dir.rglob("*.aimodel"))
                manifest["artifact"]["aimodel_count"] = len(aimodels)

                # ── Content verification (per-file sha256, streamed) ──
                if no_verify:
                    manifest["verification"]["status"] = "skipped"
                    if verbose:
                        print("  ⚠️  ⚠️  --no-verify: sha256 verification SKIPPED.")
                        print("        The downloaded bytes were NOT checked against")
                        print("        the catalog digests. Do not trust this artifact")
                        print("        for anything security-sensitive.")
                elif digest_files:
                    if verbose:
                        print(f"  Verifying {len(digest_files)} file digest(s)...")
                    check = verify_file_digests(artifact_dir, digest_files, verbose=verbose)
                    manifest["verification"]["status"] = check["status"]
                    manifest["verification"]["files_verified"] = check["files_verified"]
                    if check["status"] == "failed":
                        manifest["verification"]["mismatched"] = check["mismatched"]
                        manifest["verification"]["missing"] = check["missing"]
                        manifest["verified"]["file_layout"] = "verification_failed"
                        if verbose:
                            print("  ❌ VERIFICATION FAILED — downloaded bytes do not")
                            print("     match the catalog's recorded sha256 digests.")
                            print("     The artifact may have been swapped upstream.")
                            print("     Refusing to register this install as usable.")
                    elif verbose:
                        print(f"  ✅ Verified {check['files_verified']}/{check['files_total']} file digest(s).")
                else:
                    # Catalog has no digests for this artifact — say so honestly.
                    manifest["verification"]["status"] = "unavailable"
                    if verbose:
                        print("  ⚠️  No sha256 digests recorded in the catalog for this")
                        print("      artifact — content verification is unavailable.")
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

    # ── Generate Swift snippet (not for failed-verification installs) ──
    if manifest["verification"]["status"] != "failed":
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


def snippet_source(model: dict) -> str:
    """Which generator a model's snippet comes from (recorded in the manifest).

    ``io_contract`` — typed contract authored in catalog.yaml (redteam C1/C2);
    ``runner_bucket`` — legacy conceptual template keyed on the runner field.
    """
    return "io_contract" if model.get("io_contract") else "runner_bucket"


def _generate_swift_snippet(model: dict, artifact: dict) -> str:
    """Generate a Swift integration snippet for the model.

    When the catalog entry carries an authored ``io_contract`` (typed IO
    contract, redteam C1/C2/C6), the snippet is rendered FROM the contract:
    real entrypoint init pattern, every declared input with its
    preprocessing/constraints, real output decoding notes, and the resolved
    local artifact path interpolated. Image-input models get an image code
    path instead of a text-only chat template.

    Otherwise falls back to the legacy runner-bucket template (labeled as
    such in the emitted snippet).
    """
    if model.get("io_contract"):
        return _generate_contract_snippet(model, artifact)
    return _generate_bucket_snippet(model, artifact)


def _contract_io_comments(ioc: dict) -> str:
    """Render the contract's inputs/outputs as typed comment lines."""
    lines: list[str] = ["// Typed IO contract (authored in catalog.yaml):"]
    lines.append("//   inputs:")
    for inp in ioc.get("inputs", []):
        head = f"//   - {inp.get('name', '?')} ({inp.get('modality', '?')})"
        if inp.get("swift_type"):
            head += f": {inp['swift_type']}"
        tensor = inp.get("tensor") or {}
        if tensor:
            bits = []
            if tensor.get("shape") is not None:
                bits.append(f"shape {tensor['shape']}")
            if tensor.get("dtype"):
                bits.append(str(tensor["dtype"]))
            if tensor.get("layout"):
                bits.append(str(tensor["layout"]))
            head += " — tensor " + ", ".join(bits)
        lines.append(head)
        for section in ("preprocessing", "constraints"):
            for key, val in (inp.get(section) or {}).items():
                lines.append(f"//       {key}: {val}")
    lines.append("//   outputs:")
    for out in ioc.get("outputs", []):
        head = f"//   - {out.get('name', '?')}"
        if out.get("swift_type"):
            head += f": {out['swift_type']}"
        lines.append(head)
        for key, val in (out.get("decoding") or {}).items():
            lines.append(f"//       {key}: {val}")
    files = ioc.get("files") or {}
    if files:
        lines.append("//   files (paths in the pinned HF revision / installed artifact):")
        for key, val in files.items():
            lines.append(f"//       {key}: {val}")
    return "\n".join(lines)


def _contract_usage_block(model: dict, ioc: dict, artifact_dir: Path) -> str:
    """Entrypoint-specific usage code rendered from the contract."""
    entry = ioc.get("entrypoint") or {}
    etype = entry.get("type", "")
    init_pattern = entry.get("init_pattern", "")
    # Interpolate the resolved local artifact path into the init pattern.
    init_pattern = init_pattern.replace("<install-dir>", str(artifact_dir))
    inputs = ioc.get("inputs", [])
    outputs = ioc.get("outputs", [])
    image_inputs = [i for i in inputs if i.get("modality") == "image"]
    text_inputs = [i for i in inputs if i.get("modality") == "text"]

    lines: list[str] = []
    lines.append("// Installed artifact root (resolved by `coreai-catalog install`)")
    lines.append(f'let modelDir = URL(fileURLWithPath: "{artifact_dir}", isDirectory: true)')

    # Emit `let` bindings for URL identifiers the init pattern references.
    ident_hints = {
        "bundleURL": "// bundle dir containing metadata.json (pick your platform's subdir if the repo ships several)\nlet bundleURL = modelDir",
        "bundleDir": "let bundleDir = modelDir.path",
        "aimodelURL": '// point at the .aimodel directory inside the installed artifact\nlet aimodelURL = modelDir.appending(path: "<name>.aimodel")',
        "visionURL": '// vision encoder .aimodel inside the installed artifact\nlet visionURL = modelDir.appending(path: "<vision>.aimodel")',
        "decoderURL": '// decoder .aimodel inside the installed artifact\nlet decoderURL = modelDir.appending(path: "<decoder>.aimodel")',
    }
    for ident, binding in ident_hints.items():
        if ident in init_pattern:
            lines.append(binding)
    lines.append("")
    lines.append("// Entrypoint (from io_contract)")
    lines.append(init_pattern)
    lines.append("")

    if image_inputs:
        name = image_inputs[0].get("name", "image")
        swift_type = image_inputs[0].get("swift_type", "")
        lines.append(f"// Image input '{name}' — this model consumes an image, not just text.")
        if swift_type == "URL" or etype == "CoreAIRunner":
            lines.append('let imageURL = URL(fileURLWithPath: "/path/to/input.png")')
        else:
            lines.append('// Load a CGImage (ImageIO):')
            lines.append('let imageURL = URL(fileURLWithPath: "/path/to/input.png")')
            lines.append("guard let src = CGImageSourceCreateWithURL(imageURL as CFURL, nil),")
            lines.append("      let image = CGImageSourceCreateImageAtIndex(src, 0, nil) else {")
            lines.append('    fatalError("cannot load image")')
            lines.append("}")
        lines.append("")

    if etype == "CoreAILanguageModel":
        lines.append("let session = LanguageModelSession(model: model)")
        lines.append('let response = try await session.respond(to: "Summarize this file in one sentence.")')
        lines.append("print(response.content)")
    elif etype == "CoreAIRunner" and image_inputs:
        lines.append("// Vision path (MultimodalInferenceEngine): encode the image, then")
        lines.append("// assemble the prompt with image placeholder tokens and generate —")
        lines.append("// see apple/coreai-models swift/Sources/Tools/llm-runner (VLM path).")
        lines.append("let embedded = try await engine.encodeImage(at: imageURL)")
    elif etype == "ObjectDetector":
        lines.append("let detections = try await detector.detect(image: image)")
        lines.append("for d in detections {")
        lines.append("    print(d.label, d.confidence, d.boundingBox)  // pixel CGRect, top-left origin")
        lines.append("}")
    elif etype == "ImageSegmenter":
        prompt_ok = bool(text_inputs)
        if prompt_ok:
            lines.append('let result = try await segmenter.segment(image: image, prompt: "a cat")')
        else:
            lines.append("let result = try await segmenter.segment(image: image)")
        lines.append("// result: SegmentationResponse — segments sorted by score descending")
    elif etype == "Flux2Pipeline":
        lines.append("// Generate: pipeline.generateImages(configuration:progressHandler:)")
        lines.append("// returns GenerationResult with .images: [CGImage] — see")
        lines.append("// apple/coreai-models swift/Sources/Tools/diffusion-runner.")
    elif etype == "AIModel":
        input_keys = ", ".join(
            f'"{i.get("name", "input")}": /* {i.get("modality", "?")} input */'
            for i in inputs
        )
        out_keys = ", ".join(f'"{o.get("name", "output")}"' for o in outputs)
        lines.append("// Run the graph — input keys below come from the typed contract,")
        lines.append("// not guessed:")
        if "let model" in init_pattern:
            lines.append(f"let request = try model.makeRequest(inputs: [{input_keys}])")
            lines.append("let result = try await model.run(request)")
        else:
            lines.append("// Multi-stage pipeline: drive each stage with")
            lines.append("// makeRequest(inputs:)/run(_:). Typed input keys:")
            lines.append(f"//   [{input_keys}]")
        lines.append(f"// outputs: {out_keys}")
    return "\n".join(lines)


def _generate_contract_snippet(model: dict, artifact: dict) -> str:
    """Render the Swift snippet from the authored io_contract."""
    name = model.get("name", model["id"])
    ioc = model["io_contract"]
    entry = ioc.get("entrypoint") or {}
    runtime = model.get("runtime", {})
    hf = artifact.get("huggingface", {}) or {}
    repo = f"{hf.get('owner', '')}/{hf.get('repo', '')}"
    artifact_dir = get_model_dir(model["id"]) / "artifacts"

    framework = entry.get("framework", "CoreAI")
    imports = ["import CoreAI"]
    if framework and framework != "CoreAI":
        imports.append(f"import {framework}")
    if entry.get("type") == "CoreAILanguageModel":
        imports.append("import FoundationModels  // LanguageModelSession")
    if any(
        i.get("modality") == "image" and i.get("swift_type") == "CGImage"
        for i in ioc.get("inputs", [])
    ):
        imports.append("import ImageIO")

    session = ioc.get("session") or {}
    session_note = ""
    if session:
        session_note = (
            f"// Session: stateful={str(session.get('stateful', 'unknown')).lower()}, "
            f"streaming={str(session.get('streaming', 'unknown')).lower()}\n"
        )

    runtime_notes = f"""// Runtime notes:
//   - Runner: {runtime.get('runner', 'unknown')}
//   - Stock runtime: {runtime.get('stock_runtime', 'unknown')}
//   - Custom kernel: {runtime.get('custom_kernel', 'unknown')}
//   - Patch required: {runtime.get('patch_required', 'unknown')}
//   - AOT required: {runtime.get('aot_required', 'unknown')}
"""

    return f"""// {name} — Core AI integration snippet
// Generated by coreai-catalog
// Snippet source: io_contract (typed IO contract authored in catalog.yaml)
// Source: https://huggingface.co/{repo}

{chr(10).join(imports)}

{_contract_io_comments(ioc)}

{_contract_usage_block(model, ioc, artifact_dir)}

{session_note}{runtime_notes}"""


def _generate_bucket_snippet(model: dict, artifact: dict) -> str:
    """Legacy runner-bucket snippet (used only when no io_contract exists).

    Selects the Apple/Core AI API pattern based on the runner type:
      - CoreAIRunner (LLMs)        → CoreAI LanguageModelSession + CoreAILanguageModel API
      - stock-runner / other       → CoreAI AIModel GraphModel API
      - speech models              → CoreAI SpeechModel API
      - diffusion                  → CoreAI DiffusionPipeline API
      - segmentation               → CoreAI ImageSegmenter API
      - detection                  → CoreAI ObjectDetector API
    """
    name = model.get("name", model["id"])
    model_id = model["id"]
    runtime = model.get("runtime", {})
    runner = runtime.get("runner", "CoreAIRunner")
    hf = artifact.get("huggingface", {}) or {}
    repo = f"{hf.get('owner', '')}/{hf.get('repo', '')}"
    capabilities = model.get("capabilities", [])

    runtime_notes = f"""// Runtime notes:
//   - Runner: {runner}
//   - Stock runtime: {runtime.get('stock_runtime', 'unknown')}
//   - Custom kernel: {runtime.get('custom_kernel', 'unknown')}
//   - Patch required: {runtime.get('patch_required', 'unknown')}
//   - AOT required: {runtime.get('aot_required', 'unknown')}
"""

    # Speech / transcription models → SpeechModel API
    if any(c in capabilities for c in ("speech-to-text", "transcription")):
        return f"""// {name} — Core AI integration snippet
// Generated by coreai-catalog
// Snippet source: runner-bucket template (no io_contract in catalog.yaml — conceptual)
// Source: https://huggingface.co/{repo}
//
// ⚠️  Conceptual — see https://github.com/apple/coreai-models for complete
//     working examples of the SpeechModel transcription API.

import CoreAI

// 1. Create a SpeechModel (uses the installed .aimodel bundle)
let transcriber = SpeechModel()

// 2. Transcribe audio
let result = try await transcriber.transcribe(audioURL)
print(result.text)

{runtime_notes}"""

    # Image generation → DiffusionPipeline API
    if runner == "CoreAIDiffusionPipeline" or "image-generation" in capabilities:
        return f"""// {name} — Core AI integration snippet
// Generated by coreai-catalog
// Snippet source: runner-bucket template (no io_contract in catalog.yaml — conceptual)
// Source: https://huggingface.co/{repo}
//
// ⚠️  Conceptual — see https://github.com/apple/coreai-models for complete
//     working examples of the DiffusionPipeline API.

import CoreAI

// 1. Create a diffusion pipeline (uses the installed .aimodel bundle)
let pipeline = try DiffusionPipeline(model: .flux2Klein4B)

// 2. Generate an image from a text prompt
let image = try await pipeline.generateImage(from: "a serene mountain landscape at sunset")

{runtime_notes}"""

    # Segmentation → ImageSegmenter API
    if runner == "CoreAIImageSegmenter" or any(
        c in capabilities for c in ("instance-segmentation", "promptable-segmentation")
    ):
        return f"""// {name} — Core AI integration snippet
// Generated by coreai-catalog
// Snippet source: runner-bucket template (no io_contract in catalog.yaml — conceptual)
// Source: https://huggingface.co/{repo}
//
// ⚠️  Conceptual — see https://github.com/apple/coreai-models for complete
//     working examples of the ImageSegmenter API.

import CoreAI

// 1. Create an image segmenter (uses the installed .aimodel bundle)
let segmenter = try ImageSegmenter(model: .sam3)

// 2. Segment an image
let mask = try await segmenter.segment(image: inputImage)

{runtime_notes}"""

    # Object detection → ObjectDetector API
    if "object-detection" in capabilities:
        return f"""// {name} — Core AI integration snippet
// Generated by coreai-catalog
// Snippet source: runner-bucket template (no io_contract in catalog.yaml — conceptual)
// Source: https://huggingface.co/{repo}
//
// ⚠️  Conceptual — see https://github.com/apple/coreai-models for complete
//     working examples of the ObjectDetector API.

import CoreAI

// 1. Create an object detector (uses the installed .aimodel bundle)
let detector = try ObjectDetector(model: .yoloxS)

// 2. Detect objects in an image
let detections = try await detector.detect(in: inputImage)

{runtime_notes}"""

    # LLM runners (CoreAIRunner, stock-runner) → LanguageModelSession API
    if runner in ("CoreAIRunner", "stock-runner"):
        return f"""// {name} — Core AI integration snippet
// Generated by coreai-catalog
// Snippet source: runner-bucket template (no io_contract in catalog.yaml — conceptual)
// Source: https://huggingface.co/{repo}
//
// ⚠️  Conceptual — see https://github.com/apple/coreai-models for complete
//     working examples of the LanguageModelSession API.

import CoreAI

// 1. Start a language model session (uses the installed .aimodel bundle)
let session = LanguageModelSession(model: CoreAILanguageModel())

// 2. Send a prompt and get a response
let response = try await session.respond(to: "Hello, how are you?")
print(response.content)

// 3. Multi-turn conversation — the session maintains state
let followUp = try await session.respond(to: "Tell me more about that.")
print(followUp.content)

{runtime_notes}"""

    # Non-LLM models (GraphModel, etc.) → CoreAI AIModel API
    return f"""// {name} — Core AI integration snippet
// Generated by coreai-catalog
// Snippet source: runner-bucket template (no io_contract in catalog.yaml — conceptual)
// Source: https://huggingface.co/{repo}
//
// ⚠️  Conceptual — see https://github.com/apple/coreai-models for complete
//     working examples of the AIModel GraphModel API.

import CoreAI

// 1. Load the .aimodel bundle from the installed path
//    (adjust path to match your app's bundle structure)
let bundleURL = Bundle.main.url(forResource: "{model_id}", withExtension: "aimodel")!
let model = try AIModel(contentsOf: bundleURL)

// 2. Build a request and run the model
//    Input key names vary by model — check the model spec in apple/coreai-models
let request = try model.makeRequest(inputs: [
    "input": /* your input here */,
])
let result = try await model.run(request)

// 3. Read the outputs
//    Output key names vary by model — check the model spec in apple/coreai-models
// let output = result.outputs["output"]

{runtime_notes}"""


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
