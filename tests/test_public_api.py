"""Tests for the public Python API (coreai_catalog.api.Catalog)."""
import unittest

from coreai_catalog import Catalog


class TestPublicAPI(unittest.TestCase):
    """Test the high-level Catalog API."""

    @classmethod
    def setUpClass(cls):
        cls.cat = Catalog.load()

    def test_load(self):
        """Catalog.load() returns a working instance."""
        self.assertIsNotNone(self.cat)
        self.assertGreater(self.cat.model_count, 0)

    def test_version(self):
        """Version is a non-empty string."""
        v = self.cat.version
        self.assertIsInstance(v, str)
        self.assertGreater(len(v), 0)

    def test_model_count(self):
        """Model count matches expected range."""
        self.assertGreaterEqual(self.cat.model_count, 70)

    def test_search_capability(self):
        """Search by capability returns matching models."""
        results = self.cat.search(capability="chat")
        self.assertGreater(len(results), 0)
        for m in results:
            self.assertIn("chat", m.get("capabilities", []))

    def test_search_device(self):
        """Search with device filter returns only matching models."""
        results = self.cat.search(capability="chat", device="iphone")
        for m in results:
            ds = m.get("device_support", {})
            self.assertTrue(ds.get("iphone") is True)

    def test_search_license(self):
        """Search with license filter returns only matching models."""
        results = self.cat.search(license_filter="likely", limit=200)
        for m in results:
            self.assertEqual(m.get("license", {}).get("commercial_use"), "likely")

    def test_search_empty(self):
        """Search with no matches returns empty list."""
        results = self.cat.search(capability="nonexistent-capability")
        self.assertEqual(len(results), 0)

    def test_search_limit(self):
        """Search respects limit parameter."""
        results = self.cat.search(limit=3)
        self.assertLessEqual(len(results), 3)

    def test_recommend(self):
        """Recommend returns sorted results for a valid task."""
        recs = self.cat.recommend(task="ocr")
        self.assertGreater(len(recs), 0)
        # Results should be sorted by score descending
        scores = [r["score"] for r in recs]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_recommend_with_device(self):
        """Recommend with device filter returns only matching models."""
        recs = self.cat.recommend(task="robot vision", device="iphone")
        for r in recs:
            ds = r.get("devices", {})
            self.assertTrue(ds.get("iphone") is True)

    def test_recommend_empty_task(self):
        """Recommend with unknown task returns empty list."""
        recs = self.cat.recommend(task="xyzzy-nonexistent-task-12345")
        self.assertEqual(len(recs), 0)

    def test_get_model(self):
        """get_model returns a dict with expected fields."""
        m = self.cat.get_model("qwen3-vl-2b")
        self.assertIsNotNone(m)
        self.assertEqual(m["id"], "qwen3-vl-2b")
        self.assertIn("capabilities", m)
        self.assertIn("license", m)

    def test_get_model_not_found(self):
        """get_model returns None for nonexistent ID."""
        self.assertIsNone(self.cat.get_model("does-not-exist"))

    def test_compare(self):
        """compare returns data for both models."""
        diff = self.cat.compare("qwen3-vl-2b", "unlimited-ocr")
        self.assertEqual(len(diff["models"]), 2)
        ids = {m["id"] for m in diff["models"]}
        self.assertEqual(ids, {"qwen3-vl-2b", "unlimited-ocr"})

    def test_compare_too_few(self):
        """compare raises ValueError with < 2 models."""
        with self.assertRaises(ValueError):
            self.cat.compare("qwen3-vl-2b")

    def test_compare_not_found(self):
        """compare raises KeyError for nonexistent model."""
        with self.assertRaises(KeyError):
            self.cat.compare("qwen3-vl-2b", "nonexistent")

    def test_license_report(self):
        """license_report returns structured license info."""
        report = self.cat.license_report("qwen3-vl-2b")
        self.assertEqual(report["model_id"], "qwen3-vl-2b")
        self.assertIn("license_name", report)
        self.assertIn("commercial_use", report)
        self.assertIn("officiality", report)

    def test_license_report_not_found(self):
        """license_report raises KeyError for nonexistent model."""
        with self.assertRaises(KeyError):
            self.cat.license_report("nonexistent")

    def test_tasks(self):
        """tasks returns a dict mapping capability to synonym list."""
        tasks = self.cat.tasks()
        self.assertIsInstance(tasks, dict)
        self.assertGreater(len(tasks), 10)
        # Each value is a non-empty list
        for cap, syns in tasks.items():
            self.assertIsInstance(syns, list)
            self.assertGreater(len(syns), 0)

    def test_capabilities(self):
        """capabilities returns list with counts."""
        caps = self.cat.capabilities()
        self.assertGreater(len(caps), 0)
        for c in caps:
            self.assertIn("capability", c)
            self.assertIn("model_count", c)
            self.assertGreater(c["model_count"], 0)

    def test_transforms_matrix(self):
        """Catalog.transforms() returns reachability matrix."""
        matrix = self.cat.transforms()
        self.assertIsInstance(matrix, dict)
        self.assertIn("text", matrix)

    def test_transform_pipeline(self):
        """Catalog.transform_pipeline() returns a pipeline."""
        pipeline = self.cat.transform_pipeline("text", "audio")
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline["output_modality"], "audio")

    def test_transform_reachable(self):
        """Catalog.reachable_outputs() returns list of modalities."""
        reachable = self.cat.reachable_outputs("image")
        self.assertIn("text", reachable)
        self.assertIn("audio", reachable)


if __name__ == "__main__":
    unittest.main()
