"""
P1 benchmark-runner tests (redteam findings B1, B7 second half, B8).

Covers the pure-Python orchestrator (coreai_catalog/bench.py) with
fixtures — no macOS 27 runtime needed:

1. Artifact provenance: sha256 digest root computation + revision
   extraction from artifacts.yaml (real repo data and synthetic fixtures).
2. Installed-artifact resolution with actionable errors.
3. Runner discovery: env override + the macOS-27/build guidance message.
4. Runner-output validation: manifest completeness, trial-count check,
   median recomputation, freshness-nonce echo.
5. Candidate line assembly: schema-valid, app_benchmark_protocol,
   verification_tier, provenance propagation, never-fabricate rules.
6. Schema migration is additive: all existing benchmarks.jsonl rows still
   validate; the superseded_by value dropped by the YAML→JSONL migration is
   restored (recovered from benchmarks.yaml @ commit 0d25b15).
7. Swift package sanity on this machine: manifest parses
   (`swift package dump-package`) and every source file passes
   `xcrun swiftc -parse` (build/run needs macOS 27 — see docs).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from coreai_catalog import bench  # noqa: E402
from coreai_catalog.bench import (  # noqa: E402
    BenchError,
    artifact_provenance,
    assemble_benchmark_line,
    build_run_context,
    compute_sha256_root,
    locate_runner,
    resolve_installed,
    schema_validate_line,
    validate_runner_output,
)


def make_manifest(**overrides) -> dict:
    """A consistent run-manifest fixture (keys match the Swift runner)."""
    manifest = {
        "runner_version": "0.1.0",
        "protocol_version": "1.0",
        "run_id": "fixture-run",
        "started_at": "2026-07-03T10:00:00Z",
        "finished_at": "2026-07-03T10:05:00Z",
        "model_id": "qwen3-5-0-8b",
        "model_bundle_name": "qwen3_5_0_8b_decode_int8lin",
        "artifact_revision": "34ed8b08946395397c3b01d07d0a532237e71af3",
        "artifact_sha256_root": "a" * 64,
        "artifact_files_total": 9,
        "freshness_nonce": "deadbeef" * 5,
        "seed": 0,
        "sampling": "greedy(temperature=0)",
        "device_class": "mac-m4-max",
        "chip_family": "M4 Max",
        "prompt_tokens": 128,
        "generation_tokens": 256,
        "warmup_runs": 3,
        "measured_runs": 3,
        "metrics": [
            {
                "metric": "decode_throughput",
                "unit": "tokens_per_second",
                "median": 200.0,
                "stddev": 5.0,
                "p50": 200.0,
                "p95": 208.0,
                "higher_is_better": True,
            },
            {
                "metric": "time_to_first_token",
                "unit": "milliseconds",
                "median": 90.0,
                "stddev": 2.0,
                "p50": 90.0,
                "p95": 93.0,
                "higher_is_better": False,
            },
        ],
        "environment": {
            "os_version": "27.0.0",
            "os_major": "27",
            "low_power_mode": False,
            "thermal_state_start": "nominal",
            "thermal_state_end": "nominal",
            "engine_type": "CoreAIPipelinedEngine",
            "compute_unit_inferred": "GPU",
        },
        "self_check": {
            "prompt_token_count_exact": True,
            "greedy_sampling": True,
            "sampling_seed_applied": False,
            "thermal_pressure_detected": False,
            "all_trials_completed_requested_tokens": True,
            "device_class_coarsened": True,
        },
        "raw_trials_file": "trials.jsonl",
    }
    manifest.update(overrides)
    return manifest


def make_trials(throughputs=(190.0, 200.0, 210.0), ttfts=(88.0, 90.0, 92.0)) -> list[dict]:
    trials = []
    for i, (tps, ttft) in enumerate(zip(throughputs, ttfts), start=1):
        trials.append({
            "trial": i,
            "prompt_tokens": 128,
            "generated_tokens": 256,
            "time_to_first_token_ms": ttft,
            "decode_tokens": 255,
            "decode_seconds": 255 / tps,
            "decode_tokens_per_second": tps,
            "total_seconds": 255 / tps + ttft / 1000,
            "peak_memory_mb": 1100.5,
            "thermal_state_before": "nominal",
            "thermal_state_after": "nominal",
        })
    return trials


def write_run_output(out_dir: Path, manifest: dict, trials: list[dict]) -> None:
    (out_dir / "run-manifest.json").write_text(json.dumps(manifest, indent=2))
    (out_dir / "trials.jsonl").write_text(
        "\n".join(json.dumps(t) for t in trials) + "\n"
    )


class TestSha256Root(unittest.TestCase):
    def test_known_value_and_path_sorted(self):
        files = [
            {"path": "b/model.mlirb", "sha256": "B" * 64, "size_bytes": 2},
            {"path": "a/tokenizer.json", "sha256": "a" * 64, "size_bytes": 1},
        ]
        expected_blob = (
            f"{'a' * 64}  a/tokenizer.json\n{'b' * 64}  b/model.mlirb"
        )
        expected = hashlib.sha256(expected_blob.encode()).hexdigest()
        self.assertEqual(compute_sha256_root(files), expected)
        # Input order must not matter.
        self.assertEqual(compute_sha256_root(list(reversed(files))), expected)

    def test_absent_digests_stay_absent(self):
        self.assertIsNone(compute_sha256_root([]))
        self.assertIsNone(compute_sha256_root([{"path": "x", "sha256": ""}]))
        prov = artifact_provenance({"huggingface": {}})
        self.assertIsNone(prov["artifact_revision"])
        self.assertIsNone(prov["artifact_sha256_root"])

    def test_real_catalog_artifact_has_provenance(self):
        import yaml

        artifacts = yaml.safe_load((REPO_ROOT / "artifacts.yaml").read_text())
        entry = next(
            a for a in artifacts["artifacts"] if a["id"] == "qwen3-5-0-8b"
        )
        prov = artifact_provenance(entry)
        self.assertRegex(prov["artifact_revision"], r"^[0-9a-f]{40}$")
        self.assertRegex(prov["artifact_sha256_root"], r"^[0-9a-f]{64}$")
        self.assertGreater(prov["artifact_files_total"], 0)


class TestResolveInstalled(unittest.TestCase):
    def test_not_installed_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(BenchError) as ctx:
                resolve_installed("qwen3-5-0-8b", models_dir=Path(tmp))
        self.assertIn("coreai-catalog install qwen3-5-0-8b", str(ctx.exception))

    def test_installed_with_bundle_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp) / "demo-model"
            bundle = install_dir / "artifacts" / "macos" / "demo.aimodel"
            bundle.mkdir(parents=True)
            (install_dir / "manifest.json").write_text(json.dumps({
                "id": "demo-model",
                "artifact": {"local_path": str(install_dir / "artifacts")},
            }))
            manifest = resolve_installed("demo-model", models_dir=Path(tmp))
        self.assertEqual(manifest["_bench"]["bundle_path"], str(bundle.parent))
        self.assertEqual(manifest["_bench"]["aimodel_count"], 1)

    def test_installed_without_bundle_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp) / "demo-model"
            install_dir.mkdir(parents=True)
            (install_dir / "manifest.json").write_text(json.dumps({
                "id": "demo-model",
                "artifact": {"local_path": str(install_dir / "artifacts")},
            }))
            with self.assertRaises(BenchError) as ctx:
                resolve_installed("demo-model", models_dir=Path(tmp))
        self.assertIn("No .aimodel bundle", str(ctx.exception))


class TestLocateRunner(unittest.TestCase):
    def test_env_override_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "coreai-bench-runner"
            fake.write_text("#!/bin/sh\n")
            fake.chmod(0o755)
            found = locate_runner(REPO_ROOT, env={"COREAI_BENCH_RUNNER": str(fake)})
        self.assertEqual(found, fake)

    def test_missing_runner_explains_macos27_and_build(self):
        with self.assertRaises(BenchError) as ctx:
            locate_runner(REPO_ROOT, env={})
        message = str(ctx.exception)
        self.assertIn("macOS 27", message)
        self.assertIn("swift build -c release", message)
        self.assertIn("bench/CoreAIBenchRunner", message)


class TestRunContext(unittest.TestCase):
    def test_context_echoes_provenance_without_invention(self):
        ctx = build_run_context(
            "m", {"artifact_revision": None, "artifact_sha256_root": None,
                  "artifact_files_total": None}, nonce=None)
        self.assertEqual(ctx["model_id"], "m")
        self.assertIsNone(ctx["artifact_revision"])
        self.assertIsNone(ctx["freshness_nonce"])


class TestValidateRunnerOutput(unittest.TestCase):
    def test_consistent_output_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_run_output(out, make_manifest(), make_trials())
            manifest, trials = validate_runner_output(
                out, expected_nonce="deadbeef" * 5)
        self.assertEqual(len(trials), 3)
        self.assertEqual(manifest["model_id"], "qwen3-5-0-8b")

    def test_median_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            manifest = make_manifest()
            manifest["metrics"][0]["median"] = 999.0  # fabricated summary
            write_run_output(out, manifest, make_trials())
            with self.assertRaises(BenchError) as ctx:
                validate_runner_output(out)
        self.assertIn("Median mismatch", str(ctx.exception))

    def test_trial_count_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_run_output(out, make_manifest(measured_runs=10), make_trials())
            with self.assertRaises(BenchError) as ctx:
                validate_runner_output(out)
        self.assertIn("Trial count mismatch", str(ctx.exception))

    def test_nonce_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_run_output(out, make_manifest(), make_trials())
            with self.assertRaises(BenchError) as ctx:
                validate_runner_output(out, expected_nonce="other-nonce")
        self.assertIn("nonce", str(ctx.exception).lower())

    def test_missing_manifest_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            manifest = make_manifest()
            del manifest["self_check"]
            write_run_output(out, manifest, make_trials())
            with self.assertRaises(BenchError) as ctx:
                validate_runner_output(out)
        self.assertIn("self_check", str(ctx.exception))


class TestAssembleLine(unittest.TestCase):
    def test_line_is_schema_valid_and_provenanced(self):
        line = assemble_benchmark_line(
            make_manifest(),
            source="self-reported",
            installer_manifest={"verification": {"status": "verified"}},
            observed_date="2026-07-03",
            raw_trials_url="https://example.com/trials.jsonl",
        )
        self.assertEqual(schema_validate_line(line, REPO_ROOT), [])
        self.assertEqual(line["extraction_method"], "app_benchmark_protocol")
        self.assertEqual(line["verification_tier"], "unverified")
        self.assertEqual(line["value"], 200.0)
        self.assertEqual(line["device_class"], "M4 Max")
        self.assertEqual(line["compute_unit"], "GPU")
        self.assertEqual(line["os_major"], "27")
        self.assertEqual(
            line["artifact_revision"], "34ed8b08946395397c3b01d07d0a532237e71af3")
        self.assertEqual(line["artifact_sha256_root"], "a" * 64)
        self.assertEqual(line["runner_version"], "0.1.0")
        self.assertEqual(line["raw_trials_url"], "https://example.com/trials.jsonl")
        self.assertTrue(line["model_verified"])
        self.assertFalse(line["device_verified"])
        self.assertEqual(line["confidence"], "medium")

    def test_absent_provenance_stays_absent(self):
        manifest = make_manifest(
            artifact_revision=None, artifact_sha256_root=None)
        line = assemble_benchmark_line(manifest, source="self-reported")
        self.assertNotIn("artifact_revision", line)
        self.assertNotIn("artifact_sha256_root", line)
        self.assertNotIn("raw_trials_url", line)
        # No installer verification info → model_verified must be False.
        self.assertFalse(line["model_verified"])
        self.assertEqual(schema_validate_line(line, REPO_ROOT), [])

    def test_thermal_pressure_downgrades_confidence(self):
        manifest = make_manifest()
        manifest["self_check"]["thermal_pressure_detected"] = True
        line = assemble_benchmark_line(manifest, source="self-reported")
        self.assertEqual(line["confidence"], "needs_review")

    def test_unexpected_compute_unit_becomes_unknown(self):
        manifest = make_manifest()
        manifest["environment"]["compute_unit_inferred"] = "TPU"
        line = assemble_benchmark_line(manifest, source="self-reported")
        self.assertEqual(line["compute_unit"], "unknown")
        self.assertEqual(schema_validate_line(line, REPO_ROOT), [])


class TestSchemaMigration(unittest.TestCase):
    """Schema change is additive-optional; superseded_by is restored."""

    @classmethod
    def setUpClass(cls):
        schema = json.loads(
            (REPO_ROOT / "schema" / "benchmark.schema.json").read_text())
        cls.validator = Draft202012Validator(schema)
        cls.lines = [
            json.loads(line)
            for line in (REPO_ROOT / "benchmarks.jsonl").read_text().splitlines()
            if line.strip()
        ]

    def test_all_existing_rows_still_validate(self):
        for row in self.lines:
            errors = list(self.validator.iter_errors(row))
            self.assertEqual(
                errors, [], f"row {row.get('id')} fails: {errors[:1]}")

    def test_superseded_by_restored_from_yaml_history(self):
        # Value recovered from benchmarks.yaml @ commit 0d25b15 (line 553),
        # dropped by the YAML→JSONL migration in commit bd4a9a8.
        by_id = {row["id"]: row for row in self.lines}
        row = by_id["official-qwen3-0-6b-m4max-gpu-macos26-toks"]
        self.assertEqual(
            row.get("superseded_by"), "official-qwen3-0-6b-m4max-gpu-toks")
        # The superseding row must actually exist.
        self.assertIn("official-qwen3-0-6b-m4max-gpu-toks", by_id)

    def test_new_fields_are_all_optional(self):
        schema = json.loads(
            (REPO_ROOT / "schema" / "benchmark.schema.json").read_text())
        for field in ("verification_tier", "artifact_revision",
                      "artifact_sha256_root", "runner_version",
                      "raw_trials_url", "superseded_by"):
            self.assertIn(field, schema["properties"])
            self.assertNotIn(field, schema["required"])


class TestSwiftRunnerPackage(unittest.TestCase):
    """Syntax-level checks — a macOS 27 machine must still `swift build`."""

    PKG = REPO_ROOT / "bench" / "CoreAIBenchRunner"

    @unittest.skipUnless(shutil.which("swift"), "swift toolchain not available")
    def test_manifest_parses(self):
        result = subprocess.run(
            ["swift", "package", "dump-package"],
            cwd=self.PKG, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr[:1000])
        dump = json.loads(result.stdout)
        platforms = dump.get("platforms", [])
        self.assertTrue(
            any(p.get("platformName") == "macos" and
                str(p.get("version", "")).startswith("27") for p in platforms),
            f"package must honestly declare macOS 27: {platforms}",
        )

    @unittest.skipUnless(shutil.which("xcrun"), "xcrun not available")
    def test_sources_parse(self):
        sources = sorted(self.PKG.rglob("Sources/**/*.swift"))
        self.assertGreaterEqual(len(sources), 2)
        for source in sources:
            result = subprocess.run(
                ["xcrun", "swiftc", "-parse", str(source)],
                capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(
                result.returncode, 0, f"{source}: {result.stderr[:1000]}")


if __name__ == "__main__":
    unittest.main()
