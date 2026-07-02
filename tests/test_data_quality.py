"""P0 tests: critical coverage gaps identified by test suite audit.

Tests the following previously-untested features:
1. JSONL malformed line handling
2. Confidence filtering (get_benchmarks with min_confidence)
3. Aggregate generation k=3 suppression
4. min_confidence invalid value validation
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TestJSONLLoader(unittest.TestCase):
    """Test JSONL benchmark loading with malformed data."""

    @classmethod
    def setUpClass(cls):
        # Find a real model ID for test entries
        from coreai_catalog.catalog import Catalog
        cat = Catalog(ROOT)
        cls.real_model = cat.models[0]["id"] if cat.models else "test-model"

    def test_malformed_json_line_is_skipped(self):
        """A line with invalid JSON is skipped, valid lines are loaded."""
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            # Minimal catalog.yaml
            (tmpdir / "catalog.yaml").write_text(yaml.dump({
                "metadata": {"version": "test"},
                "models": [{"id": "test-model", "capabilities": ["chat"]}]
            }))

            # benchmarks.jsonl with one good, one bad line
            (tmpdir / "benchmarks.jsonl").write_text(
                json.dumps({"id": "bm-1", "model_id": "test-model", "metric": "decode_throughput",
                            "value": 100, "unit": "tokens_per_second", "confidence": "high"}) + "\n"
                "THIS IS NOT VALID JSON\n"
            )

            from coreai_catalog.catalog import Catalog
            cat = Catalog(tmpdir)
            bms = cat.get_benchmarks("test-model")
            self.assertEqual(len(bms), 1, "Should load 1 valid entry, skip 1 invalid")
            self.assertEqual(bms[0]["model_id"], "test-model")

    def test_entry_without_model_id_is_skipped(self):
        """An entry without model_id is rejected (schema validation)."""
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            (tmpdir / "catalog.yaml").write_text(yaml.dump({
                "metadata": {"version": "test"},
                "models": [{"id": "test-model", "capabilities": ["chat"]}]
            }))

            # JSONL with valid JSON but missing model_id
            (tmpdir / "benchmarks.jsonl").write_text(
                json.dumps({"wrong": "schema", "value": 100}) + "\n"
                + json.dumps({"id": "bm-2", "model_id": "test-model", "metric": "x",
                              "value": 50, "unit": "tokens_per_second"}) + "\n"
            )

            from coreai_catalog.catalog import Catalog
            cat = Catalog(tmpdir)
            bms = cat.get_benchmarks("test-model")
            self.assertEqual(len(bms), 1, "Only the entry with model_id should load")

    def test_corrupt_jsonl_does_not_fall_back_to_yaml(self):
        """If JSONL exists but is empty/corrupt, YAML is NOT used."""
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            (tmpdir / "catalog.yaml").write_text(yaml.dump({
                "metadata": {"version": "test"},
                "models": [{"id": "test-model", "capabilities": ["chat"]}]
            }))
            # JSONL exists but only has garbage
            (tmpdir / "benchmarks.jsonl").write_text("GARBAGE LINE 1\nGARBAGE LINE 2\n")
            # YAML has real data
            (tmpdir / "benchmarks.yaml").write_text(yaml.dump({
                "benchmarks": [{"id": "bm-yaml", "model_id": "test-model", "value": 100}]
            }))

            from coreai_catalog.catalog import Catalog
            cat = Catalog(tmpdir)
            bms = cat.get_benchmarks("test-model")
            self.assertEqual(len(bms), 0, "Should NOT fall back to YAML when JSONL exists")


class TestConfidenceFiltering(unittest.TestCase):
    """Test get_benchmarks(min_confidence=) parameter."""

    @classmethod
    def setUpClass(cls):
        import yaml

        cls.tmpdir = tempfile.mkdtemp()
        tmpdir = Path(cls.tmpdir)
        (tmpdir / "catalog.yaml").write_text(yaml.dump({
            "metadata": {"version": "test"},
            "models": [{"id": "test-model", "capabilities": ["chat"]}]
        }))
        # Create benchmarks with different confidence levels
        lines = [
            {"id": "bm-1", "model_id": "test-model", "metric": "x", "value": 100,
             "unit": "u", "confidence": "high"},
            {"id": "bm-2", "model_id": "test-model", "metric": "y", "value": 200,
             "unit": "u", "confidence": "medium"},
            {"id": "bm-3", "model_id": "test-model", "metric": "z", "value": 300,
             "unit": "u", "confidence": "low"},
        ]
        (tmpdir / "benchmarks.jsonl").write_text(
            "\n".join(json.dumps(l) for l in lines) + "\n"
        )

    def test_no_filter_returns_all(self):
        from coreai_catalog.catalog import Catalog
        cat = Catalog(Path(self.tmpdir))
        bms = cat.get_benchmarks("test-model")
        self.assertEqual(len(bms), 3)

    def test_high_only_filters_low_and_medium(self):
        from coreai_catalog.catalog import Catalog
        cat = Catalog(Path(self.tmpdir))
        bms = cat.get_benchmarks("test-model", min_confidence="high")
        self.assertEqual(len(bms), 1)
        self.assertEqual(bms[0]["confidence"], "high")

    def test_medium_filters_low(self):
        from coreai_catalog.catalog import Catalog
        cat = Catalog(Path(self.tmpdir))
        bms = cat.get_benchmarks("test-model", min_confidence="medium")
        self.assertEqual(len(bms), 2)
        confidences = {b["confidence"] for b in bms}
        self.assertEqual(confidences, {"high", "medium"})

    def test_invalid_confidence_raises(self):
        from coreai_catalog.catalog import Catalog
        cat = Catalog(Path(self.tmpdir))
        with self.assertRaises(ValueError) as ctx:
            cat.get_benchmarks("test-model", min_confidence="INVALID")
        self.assertIn("Invalid min_confidence", str(ctx.exception))


class TestAggregateSuppression(unittest.TestCase):
    """Test k=3 suppression in aggregate generation."""

    def test_group_with_lt3_samples_is_suppressed(self):
        """Groups with <3 samples have suppressed=True."""
        sys.path.insert(0, str(ROOT / "scripts"))
        from generate_benchmarks_aggregate import generate_aggregate

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            (tmpdir / "catalog.yaml").write_text("metadata:\n  version: test\nmodels: []\n")

            # Group A: 2 samples (should be suppressed)
            # Group B: 4 samples (should be published)
            lines = []
            for i in range(2):
                lines.append({"id": f"a-{i}", "model_id": "model-a",
                              "metric": "decode_throughput", "value": 100+i,
                              "unit": "u", "confidence": "high"})
            for i in range(4):
                lines.append({"id": f"b-{i}", "model_id": "model-b",
                              "metric": "decode_throughput", "value": 200+i,
                              "unit": "u", "confidence": "high"})

            (tmpdir / "benchmarks.jsonl").write_text(
                "\n".join(json.dumps(l) for l in lines) + "\n"
            )

            dist = tmpdir / "dist"
            dist.mkdir(exist_ok=True)
            result = generate_aggregate(tmpdir / "benchmarks.jsonl", dist)

            groups = {g["model_id"]: g for g in result["aggregates"]}
            self.assertTrue(groups["model-a"]["suppressed"], "model-a (N=2) should be suppressed")
            self.assertFalse(groups["model-b"]["suppressed"], "model-b (N=4) should be published")
            self.assertIn("median", groups["model-b"])
            self.assertIn("p25", groups["model-b"])
            self.assertIn("p75", groups["model-b"])
            self.assertEqual(result["published_count"], 1)
            self.assertEqual(result["suppressed_count"], 1)

    def test_low_confidence_excluded_from_aggregate(self):
        """Low-confidence entries are not included in aggregate stats."""
        sys.path.insert(0, str(ROOT / "scripts"))
        from generate_benchmarks_aggregate import generate_aggregate

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            (tmpdir / "catalog.yaml").write_text("metadata:\n  version: test\nmodels: []\n")

            lines = [
                {"id": "x-0", "model_id": "model-x", "metric": "m", "value": 100,
                 "unit": "u", "confidence": "low"},
                {"id": "x-1", "model_id": "model-x", "metric": "m", "value": 110,
                 "unit": "u", "confidence": "low"},
                {"id": "x-2", "model_id": "model-x", "metric": "m", "value": 120,
                 "unit": "u", "confidence": "low"},
                {"id": "x-3", "model_id": "model-x", "metric": "m", "value": 130,
                 "unit": "u", "confidence": "low"},
            ]
            (tmpdir / "benchmarks.jsonl").write_text(
                "\n".join(json.dumps(l) for l in lines) + "\n"
            )

            dist = tmpdir / "dist"
            dist.mkdir(exist_ok=True)
            result = generate_aggregate(tmpdir / "benchmarks.jsonl", dist)

            self.assertEqual(result["total_count"], 0, "Low-confidence entries should be excluded")

    def test_aggregate_has_metadata(self):
        """Aggregate output has export_schema_version and description."""
        sys.path.insert(0, str(ROOT / "scripts"))
        from generate_benchmarks_aggregate import generate_aggregate

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            (tmpdir / "catalog.yaml").write_text("metadata:\n  version: test\nmodels: []\n")
            (tmpdir / "benchmarks.jsonl").write_text("")

            dist = tmpdir / "dist"
            dist.mkdir(exist_ok=True)
            result = generate_aggregate(tmpdir / "benchmarks.jsonl", dist)

            self.assertIn("export_schema_version", result)
            self.assertIn("export_catalog_version", result)
            self.assertIn("description", result)


if __name__ == "__main__":
    unittest.main()
