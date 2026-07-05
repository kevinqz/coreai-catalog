"""
Unit tests for the decomposed suitability facets (SotA readiness reshape):
deployability_facets(), lifecycle_of(), entry_completeness().

These replace the single readiness_score composite as the headline signal —
per-axis, honest, and NOT a model-quality claim.
"""

import unittest

from coreai_catalog.catalog import (
    deployability_facets,
    entry_completeness,
    lifecycle_of,
)


class TestDeployabilityFacets(unittest.TestCase):
    def test_runtime_collapses_four_flags_to_one_axis(self):
        self.assertEqual(deployability_facets({"runtime": {"stock_runtime": True}})["runtime"], "stock")
        self.assertEqual(deployability_facets({"runtime": {"stock_runtime": False}})["runtime"], "patched")
        self.assertEqual(deployability_facets({"runtime": {"stock_runtime": "unknown"}})["runtime"], "unknown")
        self.assertEqual(deployability_facets({})["runtime"], "unknown")

    def test_facet_shape_and_measured_flag(self):
        m = {
            "artifact": {"availability": "available"},
            "device_support": {"mac": True, "iphone": False, "ipad": "unknown"},
            "license": {"name": "Apache-2.0", "commercial_use": "likely"},
            "runtime": {"stock_runtime": False},
        }
        f = deployability_facets(m, has_bench=True)
        self.assertEqual(f["obtainable"], "available")
        self.assertEqual(f["device_fit"], {"mac": True, "iphone": False, "ipad": "unknown"})
        self.assertEqual(f["license"]["commercial_use"], "likely")
        self.assertTrue(f["measured"])
        self.assertFalse(deployability_facets(m, has_bench=False)["measured"])


class TestLifecycle(unittest.TestCase):
    def test_derived_stages(self):
        self.assertEqual(lifecycle_of({"status": "deprecated"})["stage"], "deprecated")
        self.assertEqual(
            lifecycle_of({"source_group": "official", "status": "confirmed"})["stage"], "official")
        self.assertEqual(
            lifecycle_of({"source_group": "fabric", "status": "needs_review"})["stage"], "community")
        self.assertEqual(lifecycle_of({"status": "needs_review"})["stage"], "community")
        self.assertEqual(
            lifecycle_of({"status": "confirmed", "maturity": "stable"})["stage"], "verified")
        # confirmed but experimental maturity is 'experimental', not 'community'
        self.assertEqual(
            lifecycle_of({"status": "confirmed", "maturity": "experimental"})["stage"], "experimental")

    def test_explicit_lifecycle_wins(self):
        m = {"lifecycle": {"stage": "verified"}, "status": "needs_review"}
        self.assertEqual(lifecycle_of(m)["stage"], "verified")

    def test_carries_verification_and_confidence(self):
        lc = lifecycle_of({
            "status": "confirmed", "maturity": "stable",
            "confidence": "high", "last_verified": "2026-01-01",
        })
        self.assertEqual(lc["verification"], "confirmed")
        self.assertEqual(lc["curator_confidence"], "high")
        self.assertEqual(lc["last_verified"], "2026-01-01")


class TestEntryCompleteness(unittest.TestCase):
    def test_full_coverage(self):
        full = {
            "artifact": {"availability": "available"},
            "device_support": {"mac": True},
            "runtime": {"stock_runtime": False},
            "license": {"commercial_use": "likely"},
            "io_contract": {"entrypoint": {}},
        }
        c = entry_completeness(full, has_bench=True)
        self.assertEqual(c["present"], 6)
        self.assertEqual(c["of"], 6)
        self.assertEqual(c["pct"], 1.0)

    def test_unknowns_lower_coverage_not_a_hidden_score(self):
        sparse = {
            "device_support": {"mac": "unknown"},
            "artifact": {"availability": "unknown"},
        }
        c = entry_completeness(sparse, has_bench=False)
        self.assertEqual(c["present"], 0)
        self.assertFalse(c["fields"]["device_support_known"])
        self.assertFalse(c["fields"]["benchmarked"])


if __name__ == "__main__":
    unittest.main()
