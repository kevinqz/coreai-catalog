"""
Unit tests for the multi-host provenance policy (select_primary_artifact):
choosing among independent conversions of the same upstream model.

Grounds the policy in the real VibeVoice-1.5B case: gafiatulin (int8, ~5.4GB,
integrity-pinned) vs bryanbblewis11 (fp16, ~13.9GB). See
docs/concepts/multi-host-provenance.md.
"""

import unittest

from coreai_catalog.catalog import artifact_host_key, select_primary_artifact


def _art(aid, size_bytes, *, integrity=True, verified=False, apple=False):
    if integrity:
        hf = {"revision": "a" * 40,
              "files": [{"path": "x.mlirb", "sha256": "h" * 64, "size_bytes": size_bytes}]}
    else:
        hf = {"revision": None, "files": []}
    return {
        "id": aid,
        "huggingface": hf,
        "officiality": {"apple_hosted_artifact": apple},
        "verification": {"status": "verified" if verified else "unverified"},
    }


class TestHostPolicy(unittest.TestCase):
    def test_integrity_beats_bigger_unverified(self):
        # gafiatulin (int8 5.4GB, integrity) vs bryanbblewis11 (fp16 13.9GB, no integrity)
        by_id = {"g": _art("g", 5_400_000_000, integrity=True),
                 "b": _art("b", 13_900_000_000, integrity=False)}
        model = {"artifact_ref": "g", "alternate_artifacts": ["b"]}
        self.assertEqual(select_primary_artifact(model, by_id)["id"], "g")

    def test_verification_outranks_size(self):
        # verified 9GB beats unverified 5GB — trust before fit
        by_id = {"v": _art("v", 9_000_000_000, verified=True),
                 "s": _art("s", 5_000_000_000, verified=False)}
        model = {"artifact_ref": "s", "alternate_artifacts": ["v"]}
        self.assertEqual(select_primary_artifact(model, by_id)["id"], "v")

    def test_on_device_fit_smaller_wins_when_otherwise_tied(self):
        by_id = {"small": _art("small", 5_000_000_000), "big": _art("big", 14_000_000_000)}
        model = {"artifact_ref": "big", "alternate_artifacts": ["small"]}
        self.assertEqual(select_primary_artifact(model, by_id)["id"], "small")

    def test_popularity_is_only_a_tiebreaker(self):
        # identical on stable criteria → downloads breaks the tie
        by_id = {"a": _art("a", 5_000_000_000), "z": _art("z", 5_000_000_000)}
        model = {"artifact_ref": "a", "alternate_artifacts": ["z"]}
        signals = {"a": {"downloads": 10}, "z": {"downloads": 9999}}
        self.assertEqual(select_primary_artifact(model, by_id, signals)["id"], "z")

    def test_popularity_never_overrides_integrity(self):
        # a huge download count cannot promote a non-integrity host over an integrity one
        by_id = {"a": _art("a", 5_000_000_000, integrity=True),
                 "z": _art("z", 5_000_000_000, integrity=False)}
        model = {"artifact_ref": "a", "alternate_artifacts": ["z"]}
        signals = {"z": {"downloads": 10 ** 9}}
        self.assertEqual(select_primary_artifact(model, by_id, signals)["id"], "a")

    def test_single_and_missing(self):
        by_id = {"only": _art("only", 5_000_000_000)}
        self.assertEqual(select_primary_artifact({"artifact_ref": "only"}, by_id)["id"], "only")
        self.assertIsNone(select_primary_artifact({"artifact_ref": "nope"}, by_id))

    def test_host_key_is_deterministic_tuple(self):
        k = artifact_host_key(_art("x", 1000, integrity=True, verified=True, apple=True))
        self.assertEqual(k[:3], (0, 0, 0))  # integrity, verified, apple-hosted all best


if __name__ == "__main__":
    unittest.main()
