"""
Core AI Catalog benchmark orchestrator (redteam findings B1/B7/B8; spec
§3.2 step 1 and §4 P1 "Pinned open-source runner").

Drives the Swift reference runner (``bench/CoreAIBenchRunner``) and turns
its output into a schema-valid ``benchmarks.jsonl`` candidate line with
full artifact provenance:

  1. Resolve the *installed* artifact via the installer manifest
     (``~/.coreai-catalog/models/<id>/manifest.json``).
  2. Collect provenance from ``artifacts.yaml``: the pinned HF ``revision``
     and a digest root computed over the per-file sha256 list.
  3. Locate (or explain how to build) the runner binary. The runner needs
     macOS 27+ — apple/coreai-models declares
     ``platforms: [.macOS("27.0")]`` (upstream Package.swift:12) — so on
     older systems the error says exactly that instead of failing cryptically.
  4. Invoke the runner with a run-context JSON (model id, revision, digest
     root, freshness nonce = catalog HEAD commit).
  5. Validate the runner's output: manifest completeness, trial count,
     medians recomputed from the raw trials, nonce echo.
  6. Assemble the candidate line (``extraction_method:
     app_benchmark_protocol``, ``verification_tier: unverified``) plus the
     run manifest path for signing. Nothing is appended to
     ``benchmarks.jsonl`` automatically — submission stays a reviewed step.

Pure-Python steps (2, 5, 6 and the helpers) are unit-tested with fixtures
in ``tests/test_p1_bench.py`` — no macOS 27 runtime needed.

Usage:
  python3 -m coreai_catalog.bench <model-id> [--out-dir DIR] [--seed N]
                                  [--source SOURCE_ID] [--runner PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
from datetime import date
from pathlib import Path

from .contribute import find_root, load_schema, read_yaml
from .installer import get_model_dir

#: Runner version this orchestrator was written against; a mismatch is
#: reported but not fatal (the manifest records the actual version).
EXPECTED_RUNNER_VERSION = "0.1.0"

#: Relative tolerance when recomputing the runner's medians from raw trials.
MEDIAN_TOLERANCE = 1e-6

#: Keys the run manifest must carry to be submittable.
REQUIRED_MANIFEST_KEYS = (
    "runner_version",
    "protocol_version",
    "model_id",
    "seed",
    "measured_runs",
    "warmup_runs",
    "metrics",
    "environment",
    "self_check",
)


class BenchError(Exception):
    """Actionable orchestration failure (message is meant for the user)."""


# ── Provenance (pure Python, unit-tested) ──


def compute_sha256_root(files: list[dict]) -> str | None:
    """Digest root over an ``artifacts.yaml`` ``huggingface.files`` list.

    Format (documented in docs/benchmark-protocol.md, "Artifact digest
    root"): sort entries by ``path``, join ``"<sha256>  <path>"`` lines with
    a newline, then sha256 the UTF-8 bytes. Returns None when the catalog
    records no digests (unknown stays absent — never fabricated).
    """
    rows = [
        (str(f.get("path", "")), str(f.get("sha256", "")).lower())
        for f in files or []
        if f.get("path") and f.get("sha256")
    ]
    if not rows:
        return None
    rows.sort(key=lambda r: r[0])
    blob = "\n".join(f"{sha}  {path}" for path, sha in rows)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def artifact_provenance(artifact: dict) -> dict:
    """Extract revision + digest root from an ``artifacts.yaml`` entry.

    Absent data stays None; nothing is invented.
    """
    hf = artifact.get("huggingface", {}) or {}
    files = hf.get("files") or []
    return {
        "artifact_revision": hf.get("revision"),
        "artifact_sha256_root": compute_sha256_root(files),
        "artifact_files_total": len(files) if files else None,
    }


def load_artifact_entry(model_id: str, root: Path | None = None) -> tuple[dict, dict]:
    """Return (model, artifact) records for *model_id* from the YAML sources."""
    root = root or find_root()
    catalog = read_yaml(root / "catalog.yaml")
    models = {m.get("id"): m for m in catalog.get("models", [])}
    model = models.get(model_id)
    if model is None:
        raise BenchError(
            f"Model '{model_id}' not found in catalog.yaml. "
            "Run `coreai-catalog list` to see valid ids."
        )
    artifact_ref = model.get("artifact_ref")
    artifacts = read_yaml(root / "artifacts.yaml")
    entries = {a.get("id"): a for a in artifacts.get("artifacts", [])}
    artifact = entries.get(artifact_ref)
    if artifact is None:
        raise BenchError(
            f"Artifact '{artifact_ref}' (artifact_ref of '{model_id}') not "
            "found in artifacts.yaml."
        )
    return model, artifact


# ── Installed artifact resolution ──


def resolve_installed(model_id: str, models_dir: Path | None = None) -> dict:
    """Load the installer manifest for *model_id* or explain how to get one."""
    install_dir = (
        models_dir / str(model_id).replace("/", "--")
        if models_dir is not None
        else get_model_dir(model_id)
    )
    manifest_path = install_dir / "manifest.json"
    if not manifest_path.exists():
        raise BenchError(
            f"Model '{model_id}' is not installed (no {manifest_path}).\n"
            f"Install it first:  coreai-catalog install {model_id}"
        )
    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise BenchError(f"Unreadable installer manifest {manifest_path}: {exc}")
    artifact_dir = Path(manifest.get("artifact", {}).get("local_path", install_dir / "artifacts"))
    aimodels = sorted(artifact_dir.rglob("*.aimodel")) if artifact_dir.exists() else []
    if not aimodels:
        raise BenchError(
            f"No .aimodel bundle found under {artifact_dir}.\n"
            f"Re-run:  coreai-catalog install {model_id}"
        )
    manifest["_bench"] = {
        "install_dir": str(install_dir),
        # The runner loads the directory that CONTAINS the .aimodel
        # (LanguageBundle resolves components from the bundle dir).
        "bundle_path": str(aimodels[0].parent),
        "aimodel_count": len(aimodels),
    }
    return manifest


# ── Runner discovery ──


def macos_major_version() -> int | None:
    """Best-effort macOS major version; None off-macOS or unparseable."""
    if platform.system() != "Darwin":
        return None
    release = platform.mac_ver()[0]
    try:
        return int(release.split(".")[0])
    except (ValueError, IndexError):
        return None


def runner_unavailable_message(root: Path) -> str:
    """Actionable message for a missing runner binary, OS-aware."""
    pkg_dir = root / "bench" / "CoreAIBenchRunner"
    lines = [
        "coreai-bench-runner binary not found.",
        "",
        "The benchmark runner needs macOS 27+: the apple/coreai-models",
        'runtime declares platforms: [.macOS("27.0")] (upstream',
        "Package.swift:12), so it cannot build or run on older systems.",
    ]
    major = macos_major_version()
    if major is not None and major < 27:
        lines += [
            "",
            f"This machine reports macOS {platform.mac_ver()[0]} — benchmarks",
            "cannot run here. Use a macOS 27 machine, then:",
        ]
    else:
        lines += ["", "To build it:"]
    lines += [
        f"  cd {pkg_dir}",
        "  swift build -c release",
        "",
        "or point COREAI_BENCH_RUNNER at an existing binary, or pass --runner.",
    ]
    return "\n".join(lines)


def locate_runner(root: Path | None = None, env: dict | None = None) -> Path:
    """Find the built runner binary or raise BenchError with build guidance."""
    root = root or find_root()
    env = env if env is not None else os.environ
    override = env.get("COREAI_BENCH_RUNNER")
    candidates = []
    if override:
        candidates.append(Path(override))
    build_dir = root / "bench" / "CoreAIBenchRunner" / ".build"
    candidates += [
        build_dir / "release" / "coreai-bench-runner",
        build_dir / "arm64-apple-macosx" / "release" / "coreai-bench-runner",
    ]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise BenchError(runner_unavailable_message(root))


# ── Run context + invocation ──


def git_head_nonce(root: Path | None = None) -> str | None:
    """Catalog HEAD commit as a freshness nonce; None when unavailable."""
    root = root or find_root()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    head = result.stdout.strip()
    return head if result.returncode == 0 and head else None


def build_run_context(model_id: str, provenance: dict, nonce: str | None) -> dict:
    """Run-context payload the runner echoes into its manifest (never invents)."""
    return {
        "model_id": model_id,
        "artifact_revision": provenance.get("artifact_revision"),
        "artifact_sha256_root": provenance.get("artifact_sha256_root"),
        "artifact_files_total": provenance.get("artifact_files_total"),
        "freshness_nonce": nonce,
    }


def invoke_runner(
    runner: Path,
    bundle_path: str,
    model_id: str,
    run_context_path: Path,
    out_dir: Path,
    protocol_config_path: Path,
    seed: int = 0,
    timeout: int = 3600,
) -> None:
    """Run the Swift runner; raise BenchError with its stderr on failure."""
    cmd = [
        str(runner),
        "--model-path", bundle_path,
        "--model-id", model_id,
        "--run-context", str(run_context_path),
        "--protocol-config", str(protocol_config_path),
        "--out-dir", str(out_dir),
        "--seed", str(seed),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise BenchError(f"Runner timed out after {timeout}s: {' '.join(cmd)}")
    except OSError as exc:
        raise BenchError(f"Failed to execute runner {runner}: {exc}")
    if result.returncode != 0:
        raise BenchError(
            f"Runner exited {result.returncode}.\n{result.stderr[-2000:]}"
        )


# ── Output validation (pure Python, unit-tested) ──


def read_trials(trials_path: Path) -> list[dict]:
    trials = []
    for lineno, line in enumerate(trials_path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            trials.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise BenchError(f"{trials_path}:{lineno}: invalid JSON: {exc}")
    return trials


def validate_runner_output(
    out_dir: Path, expected_nonce: str | None = None
) -> tuple[dict, list[dict]]:
    """Cross-check run-manifest.json against the raw trials.

    Checks: required manifest keys, trial count == measured_runs, medians
    recomputed from raw trials match the manifest summaries, and (when
    known) the freshness nonce echo. Returns (manifest, trials).
    """
    manifest_path = out_dir / "run-manifest.json"
    trials_path = out_dir / "trials.jsonl"
    if not manifest_path.exists():
        raise BenchError(f"Runner produced no manifest at {manifest_path}")
    if not trials_path.exists():
        raise BenchError(f"Runner produced no raw trials at {trials_path}")
    manifest = json.loads(manifest_path.read_text())
    trials = read_trials(trials_path)

    missing = [k for k in REQUIRED_MANIFEST_KEYS if k not in manifest]
    if missing:
        raise BenchError(f"run-manifest.json missing keys: {', '.join(missing)}")

    measured = manifest["measured_runs"]
    if len(trials) != measured:
        raise BenchError(
            f"Trial count mismatch: manifest says measured_runs={measured}, "
            f"trials.jsonl has {len(trials)} lines."
        )

    by_metric = {
        "decode_throughput": [t.get("decode_tokens_per_second") for t in trials],
        "time_to_first_token": [t.get("time_to_first_token_ms") for t in trials],
    }
    for summary in manifest["metrics"]:
        metric = summary.get("metric")
        values = [v for v in by_metric.get(metric, []) if isinstance(v, (int, float))]
        if not values:
            raise BenchError(f"No raw trial values found for metric '{metric}'.")
        recomputed = statistics.median(values)
        reported = summary.get("median")
        if not isinstance(reported, (int, float)):
            raise BenchError(f"Manifest metric '{metric}' has no numeric median.")
        scale = max(abs(recomputed), abs(reported), 1e-12)
        if abs(recomputed - reported) / scale > MEDIAN_TOLERANCE:
            raise BenchError(
                f"Median mismatch for '{metric}': manifest={reported}, "
                f"recomputed from raw trials={recomputed}."
            )

    if expected_nonce is not None and manifest.get("freshness_nonce") != expected_nonce:
        raise BenchError(
            "Freshness nonce mismatch: expected "
            f"{expected_nonce}, manifest has {manifest.get('freshness_nonce')}."
        )
    return manifest, trials


# ── Candidate line assembly (pure Python, unit-tested) ──


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")


def assemble_benchmark_line(
    manifest: dict,
    source: str,
    installer_manifest: dict | None = None,
    observed_date: str | None = None,
    raw_trials_url: str | None = None,
) -> dict:
    """Build a schema-valid benchmarks.jsonl candidate from a run manifest.

    Only real data flows in: provenance fields appear only when the manifest
    carries them; device_class comes from the runner's coarsening (the
    chip_family string, matching the convention of existing rows like
    "M4 Max"); model_verified is True only when the installer actually
    verified the catalog digests.
    """
    summaries = {m.get("metric"): m for m in manifest.get("metrics", [])}
    decode = summaries.get("decode_throughput")
    if not decode:
        raise BenchError("Run manifest has no decode_throughput summary.")

    env = manifest.get("environment", {})
    self_check = manifest.get("self_check", {})
    model_id = manifest["model_id"]
    device_class = manifest.get("chip_family") or manifest.get("device_class") or "unknown"
    compute_unit = env.get("compute_unit_inferred", "unknown")
    if compute_unit not in ("GPU", "ANE", "CPU", "mixed"):
        compute_unit = "unknown"
    observed = observed_date or date.today().isoformat()

    clean_run = (
        not self_check.get("thermal_pressure_detected", True)
        and self_check.get("all_trials_completed_requested_tokens", False)
        and self_check.get("prompt_token_count_exact", False)
    )

    line = {
        "id": (
            f"{model_id}-{_slug(device_class)}-{compute_unit.lower()}"
            f"-protocol-{observed.replace('-', '')}"
        ),
        "model_id": model_id,
        "metric": "decode_throughput",
        "value": round(float(decode["median"]), 2),
        "unit": "tokens_per_second",
        "device_class": device_class,
        "os_major": str(env.get("os_major", "unknown")),
        "compute_unit": compute_unit,
        "extraction_method": "app_benchmark_protocol",
        # A single local run is never more than medium confidence; anything
        # with thermal pressure / short trials needs review.
        "confidence": "medium" if clean_run else "needs_review",
        "observed_date": observed,
        "source": source,
        "device_verified": False,
        "higher_is_better": True,
        "verification_tier": "unverified",
        "environment": {
            "protocol_version": str(manifest.get("protocol_version", "1.0")),
            "engine": env.get("engine_type", "unknown"),
            "warmup_runs": manifest.get("warmup_runs"),
            "measured_runs": manifest.get("measured_runs"),
            "statistic": "median",
            "stddev": round(float(decode.get("stddev", 0)), 4),
            "thermal_state": env.get("thermal_state_end", "unknown"),
            "low_power_mode": bool(env.get("low_power_mode", False)),
        },
        "notes": (
            f"Measured by coreai-bench-runner {manifest.get('runner_version')} "
            f"(protocol v{manifest.get('protocol_version')}, greedy sampling, "
            f"{manifest.get('measured_runs')} trials)."
        ),
    }

    if manifest.get("runner_version"):
        line["runner_version"] = manifest["runner_version"]
    if manifest.get("artifact_revision"):
        line["artifact_revision"] = manifest["artifact_revision"]
    if manifest.get("artifact_sha256_root"):
        line["artifact_sha256_root"] = manifest["artifact_sha256_root"]
    if raw_trials_url:
        line["raw_trials_url"] = raw_trials_url

    # model_verified only when the installer verified the recorded digests
    # against the downloaded bytes (installer.py verify_file_digests).
    verification = (installer_manifest or {}).get("verification", {})
    line["model_verified"] = verification.get("status") == "verified"
    return line


def schema_validate_line(line: dict, root: Path | None = None) -> list[str]:
    """Validate a candidate line against schema/benchmark.schema.json."""
    from jsonschema import Draft202012Validator

    root = root or find_root()
    schema = load_schema("benchmark", root)
    validator = Draft202012Validator(schema)
    return [
        f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
        for e in validator.iter_errors(line)
    ]


# ── Orchestration ──


def bench_run(
    model_id: str,
    out_dir: Path | None = None,
    seed: int = 0,
    source: str = "self-reported",
    runner_path: Path | None = None,
    verbose: bool = True,
) -> dict:
    """Full benchmark flow. Returns a result dict with candidate + manifest."""
    root = find_root()
    model, artifact = load_artifact_entry(model_id, root)
    installer_manifest = resolve_installed(model_id)
    provenance = artifact_provenance(artifact)
    runner = Path(runner_path) if runner_path else locate_runner(root)
    nonce = git_head_nonce(root)

    out_dir = out_dir or Path.cwd() / "bench-out" / model_id
    out_dir.mkdir(parents=True, exist_ok=True)
    run_context = build_run_context(model_id, provenance, nonce)
    run_context_path = out_dir / "run-context.json"
    run_context_path.write_text(json.dumps(run_context, indent=2) + "\n")

    if verbose:
        pin = provenance.get("artifact_revision") or "UNPINNED"
        print(f"  Runner:   {runner}")
        print(f"  Bundle:   {installer_manifest['_bench']['bundle_path']}")
        print(f"  Revision: {pin}")

    invoke_runner(
        runner=runner,
        bundle_path=installer_manifest["_bench"]["bundle_path"],
        model_id=model_id,
        run_context_path=run_context_path,
        out_dir=out_dir,
        protocol_config_path=root / "benchmarks" / "protocol-config.json",
        seed=seed,
    )

    manifest, trials = validate_runner_output(out_dir, expected_nonce=nonce)
    if manifest.get("runner_version") != EXPECTED_RUNNER_VERSION and verbose:
        print(
            f"  Note: runner version {manifest.get('runner_version')} != "
            f"orchestrator expectation {EXPECTED_RUNNER_VERSION}."
        )

    line = assemble_benchmark_line(
        manifest, source=source, installer_manifest=installer_manifest
    )
    errors = schema_validate_line(line, root)
    if errors:
        raise BenchError(
            "Assembled candidate line failed schema validation:\n  "
            + "\n  ".join(errors)
        )

    candidate_path = out_dir / "benchmark-candidate.jsonl"
    candidate_path.write_text(json.dumps(line, ensure_ascii=False) + "\n")
    if verbose:
        print(f"  Candidate line: {candidate_path}")
        print(f"  Run manifest (sign this): {out_dir / 'run-manifest.json'}")
        print(f"  Raw trials: {out_dir / 'trials.jsonl'} ({len(trials)} trials)")
    return {
        "candidate_path": str(candidate_path),
        "manifest_path": str(out_dir / "run-manifest.json"),
        "trials_path": str(out_dir / "trials.jsonl"),
        "line": line,
        "manifest": manifest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m coreai_catalog.bench",
        description=(
            "Run the coreai-catalog benchmark protocol against an installed "
            "model and assemble a benchmarks.jsonl candidate line."
        ),
    )
    parser.add_argument("model_id", help="Catalog model id (must be installed)")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--source",
        default="self-reported",
        help="sources.yaml id to attribute the measurement to",
    )
    parser.add_argument(
        "--runner", type=Path, default=None,
        help="Path to a coreai-bench-runner binary (else auto-located)",
    )
    args = parser.parse_args(argv)
    try:
        bench_run(
            args.model_id,
            out_dir=args.out_dir,
            seed=args.seed,
            source=args.source,
            runner_path=args.runner,
        )
    except BenchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
