"""Integration test: simulate the full Phase 2 benchmark submission flow.

Tests the complete pipeline locally:
1. Create a synthetic benchmark report
2. Sign it with the relay private key
3. Verify the signature
4. Validate against schema
5. Run outlier check

This does NOT test the CF Worker or GitHub Action — those need
deployment to test. But it validates all the Python-side components
work together.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TestBenchmarkPipeline(unittest.TestCase):
    """End-to-end test of the benchmark validation pipeline."""

    @classmethod
    def setUpClass(cls):
        # Check that keypair exists
        cls.pubkey_path = ROOT / ".github" / "relay-pubkey.pem"
        cls.privkey_path = ROOT / ".internal" / "relay-privkey.pem"
        if not cls.pubkey_path.exists() or not cls.privkey_path.exists():
            raise unittest.SkipTest("Ed25519 keypair not found — run keypair generation first")

    def _sign_payload(self, payload: dict) -> str:
        """Sign a payload dict with the relay private key, return hex signature."""
        from cryptography.hazmat.primitives.serialization import (
            load_pem_private_key, Encoding, PublicFormat
        )
        privkey = load_pem_private_key(self.privkey_path.read_bytes(), password=None)
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        sig = privkey.sign(payload_bytes)
        return sig.hex()

    def _make_benchmark_entry(self) -> dict:
        """Create a valid benchmark entry for testing."""
        return {
            "id": "bm-test-integration-001",
            "model_id": "official-qwen3-4b",
            "metric": "decode_throughput",
            "value": 145.4,
            "unit": "tokens_per_second",
            "device_class": "A18 Pro",
            "os_major": "27",
            "compute_unit": "GPU",
            "precision": "int4",
            "extraction_method": "app_benchmark_protocol",
            "confidence": "medium",
            "observed_date": "2026-07-02",
            "source": "crowdsourced-relay",
            "device_verified": False,
            "model_verified": False,
            "higher_is_better": True,
            "submission_channel": "ditto-ios-0.1.0",
            "environment": {
                "protocol_version": "1.0",
                "engine": "coreai-pipelined",
                "thermal_state": "nominal",
                "battery_state": "charging",
            },
        }

    def test_signature_round_trip(self):
        """Sign → verify cycle works correctly."""
        # Sign
        entry = self._make_benchmark_entry()
        payload_json = json.dumps(entry, sort_keys=True).encode()

        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        pubkey = load_pem_public_key(self.pubkey_path.read_bytes())

        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        privkey = load_pem_private_key(self.privkey_path.read_bytes(), password=None)

        sig = privkey.sign(payload_json)

        # Verify
        pubkey.verify(sig, payload_json)  # raises on failure

    def test_signed_entry_passes_verification(self):
        """A properly signed entry passes verify_benchmark_signature.py."""
        entry = self._make_benchmark_entry()
        sig = self._sign_payload(entry)
        signed_entry = {**entry, "_signature": sig}

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(signed_entry) + "\n")
            temp_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "verify_benchmark_signature.py"), temp_path],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )
            self.assertEqual(result.returncode, 0, f"Verification failed: {result.stderr}")
            self.assertIn("Signature verified", result.stdout)
        finally:
            os.unlink(temp_path)

    def test_unsigned_entry_fails_verification(self):
        """An entry without _signature fails verification."""
        entry = self._make_benchmark_entry()
        # NO _signature field

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(entry) + "\n")
            temp_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "verify_benchmark_signature.py"), temp_path],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )
            self.assertNotEqual(result.returncode, 0, "Should fail without signature")
            self.assertIn("No _signature field", result.stdout + result.stderr)
        finally:
            os.unlink(temp_path)

    def test_tampered_signature_fails(self):
        """An entry with a modified value after signing fails verification."""
        entry = self._make_benchmark_entry()
        sig = self._sign_payload(entry)

        # Tamper: change the value after signing
        tampered = {**entry, "value": 999.0, "_signature": sig}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(tampered) + "\n")
            temp_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "verify_benchmark_signature.py"), temp_path],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )
            self.assertNotEqual(result.returncode, 0, "Should fail with tampered payload")
        finally:
            os.unlink(temp_path)

    def test_valid_entry_passes_schema_validation(self):
        """A valid entry passes schema validation."""
        entry = self._make_benchmark_entry()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(entry) + "\n")
            temp_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "validate_benchmark_entry.py"), temp_path],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )
            self.assertEqual(result.returncode, 0, f"Schema validation failed: {result.stderr}")
            self.assertIn("VALID", result.stdout)
        finally:
            os.unlink(temp_path)

    def test_outlier_check_insufficient_data(self):
        """Outlier check returns 'insufficient-data' for a new model+device combo."""
        entry = self._make_benchmark_entry()
        # Use a fictional model to ensure no cohort exists
        entry["model_id"] = "nonexistent-model-xyz"
        entry["metric"] = "decode_throughput"
        entry["device_class"] = "FictionalChip"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(entry) + "\n")
            temp_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "outlier_check.py"),
                 "--input", temp_path,
                 "--catalog", str(ROOT / "benchmarks.jsonl")],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )
            # insufficient-data is exit 0 (doesn't block)
            self.assertEqual(result.returncode, 0)
            self.assertIn("INSUFFICIENT DATA", result.stdout)
        finally:
            os.unlink(temp_path)

    def test_outlier_check_detects_extreme_value(self):
        """Outlier check flags a value that's 100x the cohort median."""
        # Find a model with enough data
        benchmarks_path = ROOT / "benchmarks.jsonl"
        if not benchmarks_path.exists():
            self.skipTest("benchmarks.jsonl not found")

        # Pick a well-benchmarked model
        from collections import Counter
        model_counts = Counter()
        for line in benchmarks_path.read_text().splitlines():
            if line.strip():
                entry = json.loads(line)
                key = (entry.get("model_id"), entry.get("metric"), entry.get("device_class"))
                model_counts[key] += 1

        if not model_counts:
            self.skipTest("No benchmark data for outlier test")

        best_key, best_count = model_counts.most_common(1)[0]
        if best_count < 5:
            self.skipTest("Not enough data points for outlier test")

        model_id, metric, device_class = best_key

        # Submit an extreme outlier
        entry = self._make_benchmark_entry()
        entry["model_id"] = model_id
        entry["metric"] = metric
        entry["device_class"] = device_class
        entry["value"] = 99999.0  # extreme outlier

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(entry) + "\n")
            temp_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "outlier_check.py"),
                 "--input", temp_path,
                 "--catalog", str(ROOT / "benchmarks.jsonl")],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )
            self.assertNotEqual(result.returncode, 0, "Should detect outlier")
            self.assertIn("OUTLIER", result.stdout)
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    unittest.main()
