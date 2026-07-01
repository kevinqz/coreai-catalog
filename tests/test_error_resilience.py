#!/usr/bin/env python3
"""
Error resilience test suite for Core AI Catalog.

Tests every public API surface for graceful handling of:
- None / empty / non-string inputs
- Nonexistent IDs
- Negative / zero / extreme limits
- Unicode / special characters
- Malformed data

Run: env -u PYTHONPATH .venv/bin/python -m pytest tests/ -v
Or:  env -u PYTHONPATH .venv/bin/python -m unittest tests.test_error_resilience -v
"""
from __future__ import annotations

import sys
import os
import unittest
from pathlib import Path

# Ensure we can find the package
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from coreai_catalog.catalog import Catalog, resolve_task, _parse_params, TASK_MAP
from coreai_catalog.installer import (
    get_model_dir, is_installed, uninstall_model,
    _parse_artifact_size_gb, _get_free_disk_gb,
)


class TestCatalogNoneGuards(unittest.TestCase):
    """Every public method must return gracefully on None/empty/non-string input."""

    def setUp(self):
        self.cat = Catalog(_ROOT)

    # ── get_model ──

    def test_get_model_none(self):
        self.assertIsNone(self.cat.get_model(None))

    def test_get_model_empty(self):
        self.assertIsNone(self.cat.get_model(""))

    def test_get_model_whitespace(self):
        self.assertIsNone(self.cat.get_model("   "))

    def test_get_model_non_string(self):
        self.assertIsNone(self.cat.get_model(123))
        self.assertIsNone(self.cat.get_model([]))
        self.assertIsNone(self.cat.get_model({}))

    def test_get_model_nonexistent(self):
        self.assertIsNone(self.cat.get_model("nonexistent-model-xyz"))

    # ── get_artifact ──

    def test_get_artifact_none(self):
        self.assertIsNone(self.cat.get_artifact(None))

    def test_get_artifact_empty(self):
        self.assertIsNone(self.cat.get_artifact(""))

    def test_get_artifact_nonexistent(self):
        self.assertIsNone(self.cat.get_artifact("nonexistent"))

    # ── get_benchmarks ──

    def test_get_benchmarks_none(self):
        self.assertEqual(self.cat.get_benchmarks(None), [])

    def test_get_benchmarks_empty(self):
        self.assertEqual(self.cat.get_benchmarks(""), [])

    def test_get_benchmarks_nonexistent(self):
        self.assertEqual(self.cat.get_benchmarks("nonexistent"), [])

    # ── readiness_score ──

    def test_readiness_score_none(self):
        self.assertEqual(self.cat.readiness_score(None), 0)

    def test_readiness_score_empty_dict(self):
        self.assertEqual(self.cat.readiness_score({}), 0)

    def test_readiness_score_non_dict(self):
        self.assertEqual(self.cat.readiness_score(123), 0)
        self.assertEqual(self.cat.readiness_score("string"), 0)

    # ── search ──

    def test_search_non_string_capability(self):
        """Non-string capability coerced to None → returns all (no filter applied)."""
        results = self.cat.search(capability=123)
        self.assertIsInstance(results, list)
        # Non-string capability is treated as None (no filter) — should return models

    def test_search_non_string_device(self):
        results = self.cat.search(device=123)
        # Should not crash; returns all models (no valid filter applied)
        self.assertIsInstance(results, list)

    def test_search_nonexistent_capability(self):
        results = self.cat.search(capability="nonexistent")
        self.assertEqual(results, [])

    def test_search_nonexistent_device(self):
        results = self.cat.search(device="android")
        self.assertEqual(results, [])

    # ── recommend_models ──

    def test_recommend_none_capabilities(self):
        self.assertEqual(self.cat.recommend_models(capabilities=None), [])

    def test_recommend_empty_capabilities(self):
        self.assertEqual(self.cat.recommend_models(capabilities=[]), [])

    def test_recommend_non_string_in_capabilities(self):
        self.assertEqual(self.cat.recommend_models(capabilities=[123]), [])

    def test_recommend_non_string_device(self):
        results = self.cat.recommend_models(capabilities=["chat"], device=123)
        self.assertIsInstance(results, list)


class TestResolveTask(unittest.TestCase):

    def test_resolve_none(self):
        self.assertEqual(resolve_task(None), [])

    def test_resolve_empty(self):
        self.assertEqual(resolve_task(""), [])

    def test_resolve_whitespace(self):
        self.assertEqual(resolve_task("   "), [])

    def test_resolve_non_string(self):
        self.assertEqual(resolve_task(123), [])
        self.assertEqual(resolve_task([]), [])

    def test_resolve_unknown_returns_kebab(self):
        result = resolve_task("some unknown task")
        self.assertIsInstance(result, list)
        self.assertIn("some-unknown-task", result)

    def test_resolve_known_task(self):
        result = resolve_task("chat")
        self.assertIn("chat", result)


class TestParseParams(unittest.TestCase):
    """Parameter parsing must never crash on any input."""

    def test_none(self):
        self.assertEqual(_parse_params(None), float("inf"))

    def test_non_string(self):
        self.assertEqual(_parse_params(123), 123.0)
        self.assertEqual(_parse_params([]), float("inf"))

    def test_standard_formats(self):
        self.assertEqual(_parse_params("2B"), 2.0)
        self.assertEqual(_parse_params("350M"), 0.35)
        self.assertEqual(_parse_params("10B"), 10.0)

    def test_effective_params(self):
        self.assertEqual(_parse_params("E2B"), 2.0)
        self.assertEqual(_parse_params("E4B"), 4.0)

    def test_size_tiers(self):
        self.assertEqual(_parse_params("nano"), 0.05)
        self.assertEqual(_parse_params("small"), 0.15)
        self.assertEqual(_parse_params("large"), 1.0)

    def test_compound_formats(self):
        self.assertEqual(_parse_params("35B / ~3B active"), 35.0)
        self.assertEqual(_parse_params("809M / ~1.5GB"), 0.809)
        self.assertEqual(_parse_params("2B (BitNet b1.58)"), 2.0)

    def test_unknown(self):
        self.assertEqual(_parse_params("unknown"), float("inf"))
        self.assertEqual(_parse_params("not_published"), float("inf"))


class TestInstaller(unittest.TestCase):

    def test_get_model_dir_none(self):
        d = get_model_dir(None)
        self.assertIsInstance(d, Path)

    def test_get_model_dir_non_string(self):
        d = get_model_dir(123)
        self.assertIsInstance(d, Path)

    def test_get_model_dir_path_traversal(self):
        """Path traversal attempts must be sanitized (no directory escape)."""
        evil = "../../../tmp/evil"
        d = get_model_dir(evil)
        resolved = d.resolve()
        # The model_id should be sanitized to a flat directory name
        models_dir = (Path.home() / ".coreai-catalog" / "models").resolve()
        try:
            resolved.relative_to(models_dir)
            # ✅ Stays within models dir
        except ValueError:
            self.fail(f"Path traversal: {evil} resolves to {resolved} (escapes MODELS_DIR)")

    def test_uninstall_none(self):
        self.assertFalse(uninstall_model(None, verbose=False))

    def test_uninstall_non_string(self):
        self.assertFalse(uninstall_model(123, verbose=False))

    def test_uninstall_nonexistent(self):
        self.assertFalse(uninstall_model("nonexistent-model-xyz", verbose=False))

    def test_parse_artifact_size_none(self):
        self.assertIsNone(_parse_artifact_size_gb(None))

    def test_parse_artifact_size_empty(self):
        self.assertIsNone(_parse_artifact_size_gb(""))

    def test_parse_artifact_size_garbage(self):
        self.assertIsNone(_parse_artifact_size_gb("abc"))


class TestMCPTools(unittest.TestCase):
    """MCP server tools must return JSON strings, never crash."""

    def setUp(self):
        from mcp_server.server import (
            search_models, get_model, compare_models, recommend_model,
            check_license, get_benchmarks, get_artifact, explain_term,
            get_capabilities, get_tasks, get_version,
        )
        self.search_models = search_models
        self.get_model = get_model
        self.compare_models = compare_models
        self.recommend_model = recommend_model
        self.check_license = check_license
        self.get_benchmarks = get_benchmarks
        self.get_artifact = get_artifact
        self.explain_term = explain_term
        self.get_capabilities = get_capabilities
        self.get_tasks = get_tasks
        self.get_version = get_version

    def _expect_json(self, result):
        import json
        self.assertIsInstance(result, str, "MCP tool must return a JSON string")
        data = json.loads(result)  # Must be valid JSON
        return data

    def test_search_none_capability(self):
        self._expect_json(self.search_models(capability=None))

    def test_search_limit_none(self):
        self._expect_json(self.search_models(limit=None))

    def test_search_limit_zero(self):
        data = self._expect_json(self.search_models(limit=0))
        self.assertEqual(data["count"], 0)

    def test_search_limit_negative(self):
        data = self._expect_json(self.search_models(limit=-5))
        self.assertEqual(data["count"], 0)

    def test_get_model_empty(self):
        data = self._expect_json(self.get_model(""))
        self.assertIn("error", data)

    def test_get_model_nonexistent(self):
        data = self._expect_json(self.get_model("nonexistent"))
        self.assertIn("error", data)

    def test_compare_empty(self):
        data = self._expect_json(self.compare_models([]))
        self.assertIn("error", data)

    def test_compare_single(self):
        data = self._expect_json(self.compare_models(["a"]))
        self.assertIn("error", data)

    def test_compare_nonexistent(self):
        data = self._expect_json(self.compare_models(["a", "b"]))
        # Should return comparison with error entries, not crash
        self.assertIn("comparison", data)

    def test_recommend_empty_task(self):
        data = self._expect_json(self.recommend_model(""))
        self.assertEqual(data["recommendations"], [])

    def test_recommend_none_task(self):
        data = self._expect_json(self.recommend_model(None))
        self.assertEqual(data["recommendations"], [])

    def test_check_license_nonexistent(self):
        data = self._expect_json(self.check_license("nonexistent"))
        self.assertIn("error", data)

    def test_get_benchmarks_nonexistent(self):
        data = self._expect_json(self.get_benchmarks("nonexistent"))
        self.assertIn("error", data)

    def test_get_artifact_nonexistent(self):
        data = self._expect_json(self.get_artifact("nonexistent"))
        self.assertIn("error", data)

    def test_explain_term_empty(self):
        data = self._expect_json(self.explain_term(""))
        self.assertIn("error", data)

    def test_explain_term_nonexistent(self):
        data = self._expect_json(self.explain_term("nonexistent"))
        self.assertIn("error", data)

    def test_get_capabilities(self):
        data = self._expect_json(self.get_capabilities())
        self.assertIn("capabilities", data)
        self.assertGreater(len(data["capabilities"]), 0)

    def test_get_tasks(self):
        data = self._expect_json(self.get_tasks())
        self.assertIn("tasks", data)
        self.assertGreater(len(data["tasks"]), 40)

    def test_get_version(self):
        data = self._expect_json(self.get_version())
        self.assertIn("version", data)
        self.assertIn("model_count", data)


if __name__ == "__main__":
    unittest.main()
