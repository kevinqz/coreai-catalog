"""C8 — mobile robot-brain suitability as an EVIDENCE-SCOPED tuple (RFC-0200 §14.1).
A device_support boolean alone is insufficient; absent evidence stays 'unknown'."""

import unittest

from coreai_catalog.catalog import mobile_robot_brain_facets


class TestMobileRobotBrainFacets(unittest.TestCase):
    def test_absent_block_is_all_unknown_and_not_evidence_scoped(self):
        f = mobile_robot_brain_facets({"device_support": {"iphone": True}})
        # a bare iphone:true does NOT make it mobile-robot-brain suitable.
        self.assertFalse(f["evidence_scoped"])
        for k in ("device", "chip", "os", "provider", "aot_required",
                  "measured_peak_memory_bytes", "planner_capable",
                  "action_policy_capable", "gateway_compatible"):
            self.assertEqual(f[k], "unknown")
        self.assertEqual(f["coexistence_sets"], [])
        self.assertEqual(f["evidence_roots"], [])

    def test_full_evidence_block_surfaces_the_tuple(self):
        m = {"mobile_robot_brain": {
            "artifact_root": "sha256:" + "a" * 64, "app_version": "1.0.0",
            "device": "iPhone17,1", "chip": "A19-Pro", "os": "ios",
            "provider": "coreaikit-community", "aot_required": True,
            "memory_entitlement_required": True, "installed_bytes": 2_000_000_000,
            "measured_peak_memory_bytes": 3_500_000_000, "cold_load_ms": 1800,
            "warm_load_ms": 300, "sustained_latency_ms_after_soak": 42,
            "coexistence_sets": [["gemma4-e2b", "act-so101"]],
            "planner_capable": True, "action_policy_capable": True,
            "gateway_compatible": True, "evidence_roots": ["sha256:" + "b" * 64]}}
        f = mobile_robot_brain_facets(m)
        self.assertTrue(f["evidence_scoped"])
        self.assertEqual(f["device"], "iPhone17,1")
        self.assertEqual(f["chip"], "A19-Pro")
        self.assertEqual(f["coexistence_sets"], [["gemma4-e2b", "act-so101"]])
        self.assertTrue(f["planner_capable"] and f["action_policy_capable"])
        self.assertEqual(f["evidence_roots"], ["sha256:" + "b" * 64])

    def test_partial_block_without_artifact_root_is_not_evidence_scoped(self):
        f = mobile_robot_brain_facets({"mobile_robot_brain": {"device": "iPhone17,1"}})
        self.assertFalse(f["evidence_scoped"])   # no artifact root → not a real claim
        self.assertEqual(f["device"], "iPhone17,1")


if __name__ == "__main__":
    unittest.main()
