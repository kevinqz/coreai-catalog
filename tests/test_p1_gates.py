"""
P1 sigstore + physics-gate tests (redteam findings B2, B3, B5, B9, D3, D4, F1).

Covers:
1. Physics math — bandwidth-ceiling arithmetic, parameter/precision
   parsing, tokens/elapsed consistency, unknown-chip skip semantics.
2. Thermal-gate tier inversion (B9) — missing telemetry FAILS the
   trusted tier and is tolerated in the curator lane.
3. Tier logic — evaluate_tier() maps the CI gates onto
   signed_plausible / unverified (replaces the impossible
   device_verified==true auto-merge gate, F1/B3). signed_plausible is a
   CI gate outcome, never the stored verification_tier: the
   community_verified rung of the trust ladder requires a SECOND
   identity's reproduction and is curator-granted.
3b. Duplicate gate — find_recent_duplicate() excludes the submitted row
   itself exactly once (the PR merge checkout already contains the added
   line; without self-exclusion every fresh submission matched itself
   and only stale >7-day results could auto-merge).
4. Device-coarsening table (B5) — Mac16,1 is base M4, NOT M4 Max;
   exact-match rows, no duplicate identifiers, docs agree.
5. Signature verification — legacy Ed25519 relay round-trip still works;
   crafted-invalid sigstore bundles are rejected cleanly; identity →
   github_login mapping.
6. Outlier check (B9/D3) — cohorts too small for statistics fall back to
   the physics gate instead of auto-passing.

Live Fulcio/Rekor signing requires an interactive OIDC identity and is
skipped unless SIGSTORE_LIVE=1 is set (see TestSigstoreLive).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import physics_check  # noqa: E402
import verify_benchmark_signature as vbs  # noqa: E402

try:
    import sigstore  # noqa: F401
    HAVE_SIGSTORE = True
except ImportError:
    HAVE_SIGSTORE = False


def _entry(**overrides) -> dict:
    """A minimal decode_throughput entry; overridable per test."""
    base = {
        "id": "bm-test-p1-gates",
        "model_id": "qwen3-5-0-8b",  # 0.8B int8 in catalog.yaml
        "metric": "decode_throughput",
        "value": 100.0,
        "unit": "tokens_per_second",
        "device_class": "M4 Max",
        "os_major": "27",
        "compute_unit": "GPU",
        "precision": "int8",
        "extraction_method": "app_benchmark_protocol",
        "confidence": "medium",
        "observed_date": "2026-07-03",
        "source": "test",
        "higher_is_better": True,
        "environment": {"thermal_state": "nominal"},
    }
    base.update(overrides)
    return base


class TestPhysicsMath(unittest.TestCase):
    """Bandwidth-ceiling arithmetic and parsers."""

    CHIPS = {"m4 max": 546.0, "m4": 120.0}
    MODELS = {
        "qwen3-5-0-8b": {"size": {"parameters": "0.8B", "precision": "int8"}},
        "moe-model": {"size": {"parameters": "35B / ~3B active", "precision": "int8"}},
    }

    def test_parse_param_count(self):
        cases = {
            "0.8B": 0.8e9,
            "2B": 2e9,
            "350M": 350e6,
            "35B / ~3B active": 3e9,  # MoE: decode streams active weights only
            "30B / ~3B active": 3e9,
        }
        for text, expected in cases.items():
            self.assertAlmostEqual(
                physics_check.parse_param_count(text), expected,
                msg=f"parse_param_count({text!r})")
        self.assertIsNone(physics_check.parse_param_count(None))
        self.assertIsNone(physics_check.parse_param_count("not_published"))

    def test_bytes_per_weight(self):
        # Precision strings observed in benchmarks.jsonl / catalog.yaml.
        cases = {
            "int8": 1.0,
            "inferred:int8": 1.0,
            "int8hu": 1.0,
            "sym8-gather": 1.0,
            "int4": 0.5,
            "inferred:int4": 0.5,
            "int4linsym": 0.5,
            "int4lin-QAT": 0.5,
            "official-QAT-int4": 0.5,
            "inferred:MXFP4": 0.53125,  # 4-bit + shared 8-bit scale per 32
            "1.58-bit ternary": 0.2,
            "fp16": 2.0,
            "bf16": 2.0,
            "fp32": 4.0,
        }
        for text, expected in cases.items():
            self.assertEqual(
                physics_check.bytes_per_weight(text), expected,
                msg=f"bytes_per_weight({text!r})")
        self.assertIsNone(physics_check.bytes_per_weight("unknown"))
        self.assertIsNone(physics_check.bytes_per_weight(None))

    def test_normalize_chip_accepts_slug_and_bare(self):
        self.assertEqual(physics_check.normalize_chip("M4 Max"), "m4 max")
        self.assertEqual(physics_check.normalize_chip("mac-m4-max"), "m4 max")
        self.assertEqual(physics_check.normalize_chip("iphone-a18-pro"), "a18 pro")

    def _check(self, entry, tier="curator"):
        return physics_check.check_entry(entry, self.CHIPS, self.MODELS, tier=tier)

    def test_ceiling_rejects_implausible_throughput(self):
        # 0.8B int8 on M4 Max: ceiling = 546e9 / (0.8e9 * 1) = 682.5 tok/s.
        # 0.95 margin -> anything above 648.4 tok/s is implausible.
        passed, checks = self._check(_entry(value=700.0))
        self.assertFalse(passed)
        ceiling = [c for c in checks if c["check"] == "bandwidth_ceiling"][0]
        self.assertEqual(ceiling["status"], "fail")

    def test_ceiling_accepts_plausible_throughput(self):
        passed, checks = self._check(_entry(value=210.0))
        self.assertTrue(passed)
        ceiling = [c for c in checks if c["check"] == "bandwidth_ceiling"][0]
        self.assertEqual(ceiling["status"], "pass")

    def test_base_m4_ceiling_is_much_lower_than_m4_max(self):
        # The B5 misclassification in numbers: 400 tok/s on 0.8B int8 is
        # plausible on M4 Max (682 ceiling) but impossible on base M4
        # (150 ceiling) — coarsening Mac16,1 into M4 Max would have let
        # this fabrication through.
        entry = _entry(value=400.0, device_class="M4")
        passed, _ = self._check(entry)
        self.assertFalse(passed)
        entry = _entry(value=400.0, device_class="M4 Max")
        passed, _ = self._check(entry)
        self.assertTrue(passed)

    def test_unknown_chip_skips_ceiling_not_fail(self):
        # A18 Pro has no publicly grounded bandwidth -> skip, never guess.
        passed, checks = self._check(_entry(device_class="A18 Pro"))
        ceiling = [c for c in checks if c["check"] == "bandwidth_ceiling"][0]
        self.assertEqual(ceiling["status"], "skip")
        self.assertTrue(passed)

    def test_non_throughput_metric_skips_ceiling(self):
        entry = _entry(metric="time_to_first_token", unit="milliseconds", value=120)
        _, checks = self._check(entry)
        ceiling = [c for c in checks if c["check"] == "bandwidth_ceiling"][0]
        self.assertEqual(ceiling["status"], "skip")

    def test_tokens_elapsed_consistency(self):
        env = {"thermal_state": "nominal",
               "generation_tokens": 256, "elapsed_seconds": 2.0}  # implies 128 tok/s
        passed, checks = self._check(_entry(value=128.0, environment=env))
        cons = [c for c in checks if c["check"] == "tokens_elapsed_consistency"][0]
        self.assertEqual(cons["status"], "pass")
        self.assertTrue(passed)

        passed, checks = self._check(_entry(value=200.0, environment=env))
        cons = [c for c in checks if c["check"] == "tokens_elapsed_consistency"][0]
        self.assertEqual(cons["status"], "fail")
        self.assertFalse(passed)


class TestThermalTierInversion(unittest.TestCase):
    """B9 fix: absence of telemetry can no longer pass the trusted tier."""

    CHIPS: dict = {}
    MODELS: dict = {}

    def _thermal(self, entry, tier):
        _, checks = physics_check.check_entry(entry, self.CHIPS, self.MODELS, tier=tier)
        return [c for c in checks if c["check"] == "thermal_telemetry"][0]["status"]

    def test_trusted_fails_on_unknown(self):
        entry = _entry(environment={"thermal_state": "unknown"})
        self.assertEqual(self._thermal(entry, "trusted"), "fail")

    def test_trusted_fails_on_missing(self):
        self.assertEqual(self._thermal(_entry(environment={}), "trusted"), "fail")

    def test_trusted_passes_on_nominal_and_fair(self):
        for state in ("nominal", "fair"):
            entry = _entry(environment={"thermal_state": state})
            self.assertEqual(self._thermal(entry, "trusted"), "pass")

    def test_trusted_fails_on_throttling(self):
        for state in ("serious", "critical"):
            entry = _entry(environment={"thermal_state": state})
            self.assertEqual(self._thermal(entry, "trusted"), "fail")

    def test_curator_tolerates_absence_but_not_throttling(self):
        self.assertEqual(self._thermal(_entry(environment={}), "curator"), "pass")
        entry = _entry(environment={"thermal_state": "unknown"})
        self.assertEqual(self._thermal(entry, "curator"), "pass")
        entry = _entry(environment={"thermal_state": "serious"})
        self.assertEqual(self._thermal(entry, "curator"), "fail")


class TestTierLogic(unittest.TestCase):
    """evaluate_tier drives auto-merge in benchmark-validate.yml."""

    ALL_PASS = {g: True for g in physics_check.TIER_GATES}

    def test_all_gates_pass_earns_signed_plausible(self):
        self.assertEqual(physics_check.evaluate_tier(dict(self.ALL_PASS)),
                         "signed_plausible")

    def test_any_gate_failure_stays_unverified(self):
        for gate in physics_check.TIER_GATES:
            gates = dict(self.ALL_PASS)
            gates[gate] = False
            self.assertEqual(physics_check.evaluate_tier(gates), "unverified",
                             msg=f"gate {gate} should block auto-merge")

    def test_missing_gate_is_a_failure(self):
        gates = dict(self.ALL_PASS)
        del gates["identity_matches_author"]
        self.assertEqual(physics_check.evaluate_tier(gates), "unverified")

    def test_ci_never_claims_community_verified(self):
        # community_verified means "reproduced by a second identity"
        # (docs/benchmark-protocol.md, benchmark.schema.json). A single
        # n=1 submission — the only thing this gate table evaluates —
        # must never earn that label, no matter which gates pass.
        for bits in range(2 ** len(physics_check.TIER_GATES)):
            gates = {g: bool(bits >> i & 1)
                     for i, g in enumerate(physics_check.TIER_GATES)}
            self.assertNotEqual(physics_check.evaluate_tier(gates),
                                "community_verified")

    def test_tier_names_match_schema_enum(self):
        schema = json.loads((REPO_ROOT / "schema" / "benchmark.schema.json").read_text())
        enum = schema["properties"]["verification_tier"]["enum"]
        self.assertIn("community_verified", enum)
        self.assertIn("unverified", enum)
        # signed_plausible is deliberately NOT a verification_tier: it is
        # the CI merge outcome; the merged row stays 'unverified' (n=1).
        self.assertNotIn("signed_plausible", enum)


class TestDuplicateGate(unittest.TestCase):
    """find_recent_duplicate: the not_duplicate gate, self-exclusion fix.

    CI runs on the pull_request MERGE checkout, so benchmarks.jsonl
    already contains the submitted line. The regression this guards:
    a fresh submission (observed_date within 7 days) matched ITSELF,
    set not_duplicate=False, and could never auto-merge — only stale
    >7-day results could (inverted freshness incentive).
    """

    TODAY = __import__("datetime").date(2026, 7, 3)

    def _store(self, *entries: dict) -> list[str]:
        return [json.dumps(e) for e in entries]

    def _signed_raw(self, entry: dict) -> str:
        signed = dict(entry)
        signed["_signature"] = "ab" * 64
        return json.dumps(signed)

    def test_fresh_submission_does_not_match_itself(self):
        # The store contains exactly the just-added (signed) line.
        entry = _entry(observed_date="2026-07-03")
        raw = self._signed_raw(entry)
        dup = physics_check.find_recent_duplicate(
            entry, [raw], submitted_raw=raw, today=self.TODAY)
        self.assertIsNone(dup, "a submission must never be its own duplicate")

    def test_fresh_submission_with_diff_plus_prefix(self):
        # /tmp/new_lines.txt lines come from `git diff` and carry a '+'.
        entry = _entry(observed_date="2026-07-03")
        raw = self._signed_raw(entry)
        dup = physics_check.find_recent_duplicate(
            entry, [raw], submitted_raw="+" + raw, today=self.TODAY)
        self.assertIsNone(dup)

    def test_recent_same_cohort_row_is_still_a_duplicate(self):
        entry = _entry(id="bm-new", observed_date="2026-07-03")
        raw = self._signed_raw(entry)
        other = _entry(id="bm-old", observed_date="2026-06-30")
        store = self._store(other) + [raw]
        dup = physics_check.find_recent_duplicate(
            entry, store, submitted_raw=raw, today=self.TODAY)
        self.assertIsNotNone(dup)
        self.assertEqual(dup["id"], "bm-old")

    def test_stale_same_cohort_row_is_not_a_duplicate(self):
        entry = _entry(id="bm-new", observed_date="2026-07-03")
        raw = self._signed_raw(entry)
        old = _entry(id="bm-old", observed_date="2026-06-01")  # >7 days
        dup = physics_check.find_recent_duplicate(
            entry, self._store(old) + [raw], submitted_raw=raw,
            today=self.TODAY)
        self.assertIsNone(dup)

    def test_different_cohort_is_not_a_duplicate(self):
        entry = _entry(id="bm-new", observed_date="2026-07-03")
        raw = self._signed_raw(entry)
        for field, value in (("model_id", "other-model"),
                             ("device_class", "M4"),
                             ("metric", "time_to_first_token")):
            other = _entry(id="bm-other", observed_date="2026-07-02",
                           **{field: value})
            dup = physics_check.find_recent_duplicate(
                entry, self._store(other) + [raw], submitted_raw=raw,
                today=self.TODAY)
            self.assertIsNone(dup, msg=f"differing {field} is not a dup")

    def test_self_excluded_exactly_once(self):
        # If a byte-identical line was ALREADY in the store, resubmitting
        # it adds a second copy — the pre-existing one must still count.
        entry = _entry(observed_date="2026-07-03")
        raw = self._signed_raw(entry)
        dup = physics_check.find_recent_duplicate(
            entry, [raw, raw], submitted_raw=raw, today=self.TODAY)
        self.assertIsNotNone(dup)

    def test_id_fallback_when_raw_line_unavailable(self):
        entry = _entry(id="bm-self", observed_date="2026-07-03")
        store = self._store(entry)
        dup = physics_check.find_recent_duplicate(
            entry, store, submitted_raw=None, today=self.TODAY)
        self.assertIsNone(dup, "id fallback must exclude the row itself")
        # ...but only ONCE: a second equal-id recent row still counts.
        dup = physics_check.find_recent_duplicate(
            entry, store + self._store(entry), submitted_raw=None,
            today=self.TODAY)
        self.assertIsNotNone(dup)

    def test_comments_and_blank_lines_ignored(self):
        entry = _entry(observed_date="2026-07-03")
        raw = self._signed_raw(entry)
        store = ["# header comment", "", "   ", "not json {", raw]
        dup = physics_check.find_recent_duplicate(
            entry, store, submitted_raw=raw, today=self.TODAY)
        self.assertIsNone(dup)

    def test_workflow_scenario_end_to_end(self):
        # The exact CI shape: merge-checkout store = full file including
        # the new signed line; gate feeds evaluate_tier. Fresh submission
        # with all other gates green must auto-merge (signed_plausible).
        entry = _entry(observed_date=self.TODAY.isoformat())
        raw = self._signed_raw(entry)
        preexisting = [
            _entry(id="bm-a", model_id="other", observed_date="2026-07-01"),
            _entry(id="bm-b", observed_date="2026-05-10"),
        ]
        store = self._store(*preexisting) + [raw]
        gates = {g: True for g in physics_check.TIER_GATES}
        gates["not_duplicate"] = physics_check.find_recent_duplicate(
            entry, store, submitted_raw=raw, today=self.TODAY) is None
        self.assertEqual(physics_check.evaluate_tier(gates),
                         "signed_plausible")


class TestChipsYaml(unittest.TestCase):
    """chips.yaml: grounded, sourced, sane."""

    @classmethod
    def setUpClass(cls):
        cls.data = yaml.safe_load((REPO_ROOT / "chips.yaml").read_text())

    def test_every_row_has_source_and_quote(self):
        for row in self.data["chips"]:
            self.assertTrue(row.get("chip"))
            self.assertGreater(row.get("peak_memory_bandwidth_gbps", 0), 0)
            self.assertTrue(str(row.get("source", "")).startswith("https://"),
                            msg=f"{row.get('chip')} needs a public source URL")
            self.assertTrue(row.get("quote"), msg=f"{row.get('chip')} needs a verbatim quote")

    def test_apple_published_figures(self):
        bw = {row["chip"]: row["peak_memory_bandwidth_gbps"] for row in self.data["chips"]}
        # Apple newsroom, October 2024 (M4 family).
        self.assertEqual(bw["M4"], 120)
        self.assertEqual(bw["M4 Pro"], 273)
        self.assertEqual(bw["M4 Max"], 546)
        # Apple newsroom, June 2022 (M2).
        self.assertEqual(bw["M2"], 100)

    def test_ungrounded_chips_are_omitted(self):
        # Apple has never published absolute bandwidth for these — they
        # must be absent, and physics_check must skip them (tested above).
        chips = {row["chip"] for row in self.data["chips"]}
        for missing in ("M1", "A16", "A17 Pro", "A18", "A18 Pro", "A19", "A19 Pro"):
            self.assertNotIn(missing, chips)

    def test_loader_normalizes_keys(self):
        chips = physics_check.load_chip_bandwidth(REPO_ROOT / "chips.yaml")
        self.assertEqual(chips.get("m4 max"), 546.0)
        self.assertEqual(chips.get("m4"), 120.0)


class TestDeviceCoarsening(unittest.TestCase):
    """B5 fix: exact-identifier coarsening, Mac16,1 == base M4."""

    @classmethod
    def setUpClass(cls):
        cfg = json.loads((REPO_ROOT / "benchmarks" / "protocol-config.json").read_text())
        cls.coarsening = cfg["device_coarsening"]
        cls.by_id = {}
        for row in cls.coarsening["mapping"]:
            for ident in row["raw_models"]:
                cls.by_id[ident] = row

    def test_exact_match_semantics(self):
        self.assertEqual(self.coarsening.get("match"), "exact")
        for row in self.coarsening["mapping"]:
            self.assertNotIn("raw_prefix", row,
                             msg="prefix rows are the B5 bug; use raw_models")
            self.assertTrue(row.get("source"), msg=f"{row['raw_models']} needs a citation")

    def test_no_duplicate_identifiers(self):
        seen = []
        for row in self.coarsening["mapping"]:
            seen.extend(row["raw_models"])
        self.assertEqual(len(seen), len(set(seen)))

    def test_mac16_1_is_base_m4_not_m4_max(self):
        # THE B5 finding: Mac16,1 = MacBook Pro 14-inch (2024) with base
        # M4 (120 GB/s), previously binned as M4 Max (546 GB/s).
        row = self.by_id["Mac16,1"]
        self.assertEqual(row["chip_family"], "M4")
        self.assertEqual(row["device_class"], "mac-m4")

    def test_m4_generation_bin_splits(self):
        # Verified against Apple support 108052 + AppleDB/EveryMac splits.
        self.assertEqual(self.by_id["Mac16,8"]["chip_family"], "M4 Pro")
        self.assertEqual(self.by_id["Mac16,7"]["chip_family"], "M4 Pro")
        self.assertEqual(self.by_id["Mac16,6"]["chip_family"], "M4 Max")
        self.assertEqual(self.by_id["Mac16,5"]["chip_family"], "M4 Max")
        self.assertEqual(self.by_id["Mac16,9"]["chip_family"], "M4 Max")   # Mac Studio 2025
        self.assertEqual(self.by_id["Mac16,10"]["chip_family"], "M4")      # Mac mini 2024
        self.assertEqual(self.by_id["Mac16,11"]["chip_family"], "M4 Pro")  # Mac mini 2024

    def test_m3_generation_not_all_max(self):
        # The old 'Mac15 -> M3 Max' prefix row binned MacBook Airs as Max.
        self.assertEqual(self.by_id["Mac15,3"]["chip_family"], "M3")
        self.assertEqual(self.by_id["Mac15,12"]["chip_family"], "M3")
        self.assertEqual(self.by_id["Mac15,6"]["chip_family"], "M3 Pro")
        self.assertEqual(self.by_id["Mac15,10"]["chip_family"], "M3 Max")
        self.assertEqual(self.by_id["Mac15,14"]["chip_family"], "M3 Ultra")

    def test_non_m_series_tablets_and_phones(self):
        # iPad14,1/2 are the A15 iPad mini, not M2; iPad16,1/2 are the
        # A17 Pro iPad mini, not M4 (AppleDB).
        self.assertEqual(self.by_id["iPad14,1"]["chip_family"], "A15")
        self.assertEqual(self.by_id["iPad16,1"]["chip_family"], "A17 Pro")
        self.assertEqual(self.by_id["iPad16,3"]["chip_family"], "M4")
        self.assertEqual(self.by_id["iPhone17,1"]["chip_family"], "A18 Pro")
        self.assertEqual(self.by_id["iPhone17,3"]["chip_family"], "A18")

    def test_docs_agree_with_config(self):
        doc = (REPO_ROOT / "docs" / "benchmark-protocol.md").read_text()
        self.assertIn("| Mac16,1 (MacBook Pro 14\", 2024) | mac-m4 | M4 |", doc)
        self.assertNotIn("| Mac16,1 | mac-m4-max", doc)

    def test_chip_families_resolve_in_physics_chips_or_are_known_omissions(self):
        chips = physics_check.load_chip_bandwidth(REPO_ROOT / "chips.yaml")
        known_omissions = {"m1", "a15", "a16", "a17 pro", "a18", "a18 pro",
                           "a19", "a19 pro"}
        for row in self.coarsening["mapping"]:
            key = physics_check.normalize_chip(row["chip_family"])
            self.assertTrue(key in chips or key in known_omissions,
                            msg=f"{row['chip_family']} neither grounded nor a known omission")


class TestEd25519Legacy(unittest.TestCase):
    """The legacy relay path must keep working (spec deliverable)."""

    @classmethod
    def setUpClass(cls):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PublicFormat)
        cls.privkey = Ed25519PrivateKey.generate()
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.pubkey_path = Path(cls.tmpdir.name) / "pubkey.pem"
        cls.pubkey_path.write_bytes(
            cls.privkey.public_key().public_bytes(
                Encoding.PEM, PublicFormat.SubjectPublicKeyInfo))

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def _sign(self, entry: dict) -> str:
        payload = json.dumps(entry, sort_keys=True).encode()
        signed = dict(entry)
        signed["_signature"] = self.privkey.sign(payload).hex()
        return json.dumps(signed)

    def test_round_trip(self):
        line = self._sign(_entry())
        r = vbs.verify_line_detailed(line, pubkey_path=self.pubkey_path)
        self.assertTrue(r["valid"], r["message"])
        self.assertEqual(r["scheme"], "ed25519")
        self.assertIsNone(r["github_login"])

    def test_tampered_value_rejected(self):
        line = self._sign(_entry())
        tampered = json.loads(line)
        tampered["value"] = 999999.0
        r = vbs.verify_line_detailed(json.dumps(tampered), pubkey_path=self.pubkey_path)
        self.assertFalse(r["valid"])

    def test_missing_signature_rejected_with_hint(self):
        r = vbs.verify_line_detailed(json.dumps(_entry()), pubkey_path=self.pubkey_path)
        self.assertFalse(r["valid"])
        self.assertIn("sign_benchmark.py", r["message"])

    def test_canonical_payload_key_order_invariant(self):
        entry = _entry()
        shuffled = dict(reversed(list(entry.items())))
        self.assertEqual(vbs.canonical_payload(entry), vbs.canonical_payload(shuffled))
        # And identical to the legacy relay serialization.
        self.assertEqual(vbs.canonical_payload(entry),
                         json.dumps(entry, sort_keys=True).encode())


@unittest.skipUnless(HAVE_SIGSTORE, "sigstore package not installed")
class TestSigstoreBundleRejection(unittest.TestCase):
    """Crafted-invalid bundles must be rejected cleanly (no traceback)."""

    def test_garbage_bundle_dict_rejected(self):
        entry = _entry()
        entry["_signature"] = {"garbage": True}
        r = vbs.verify_line_detailed(json.dumps(entry))
        self.assertFalse(r["valid"])
        self.assertEqual(r["scheme"], "sigstore")
        self.assertIn("Invalid sigstore bundle", r["message"])

    def test_empty_bundle_rejected(self):
        entry = _entry()
        entry["_signature"] = {}
        r = vbs.verify_line_detailed(json.dumps(entry))
        self.assertFalse(r["valid"])

    def test_wrong_media_type_rejected(self):
        entry = _entry()
        entry["_signature"] = {
            "mediaType": "application/vnd.not-a-bundle+json",
            "verificationMaterial": {},
            "messageSignature": {},
        }
        r = vbs.verify_line_detailed(json.dumps(entry))
        self.assertFalse(r["valid"])
        self.assertEqual(r["scheme"], "sigstore")

    def test_unsupported_signature_type_rejected(self):
        entry = _entry()
        entry["_signature"] = 12345  # neither hex string nor bundle dict
        r = vbs.verify_line_detailed(json.dumps(entry))
        self.assertFalse(r["valid"])
        self.assertIn("Unsupported _signature type", r["message"])


class TestIdentityMapping(unittest.TestCase):
    """Fulcio SAN -> GitHub login derivation used by the CI author gate."""

    def test_actions_workflow_identity(self):
        san = ("https://github.com/kevinqz/coreai-bench/"
               ".github/workflows/bench.yml@refs/heads/main")
        self.assertEqual(vbs.github_login_from_identity(san), "kevinqz")

    def test_email_identity_has_no_login(self):
        self.assertIsNone(vbs.github_login_from_identity("kevin@example.com"))

    def test_non_github_uri_has_no_login(self):
        self.assertIsNone(vbs.github_login_from_identity(
            "https://gitlab.com/kevinqz/repo/thing@ref"))
        self.assertIsNone(vbs.github_login_from_identity(None))


class TestOutlierPhysicsFallback(unittest.TestCase):
    """B9/D3 fix: small cohorts run the physics gate, never auto-pass."""

    def _run(self, entry: dict, cohort: list[dict]) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "input.jsonl"
            inp.write_text(json.dumps(entry) + "\n")
            cat = Path(tmp) / "catalog.jsonl"
            cat.write_text("".join(json.dumps(e) + "\n" for e in cohort))
            return subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "outlier_check.py"),
                 "--input", str(inp), "--catalog", str(cat)],
                capture_output=True, text=True)

    def test_small_cohort_implausible_value_fails(self):
        # 0.8B int8 on M4 Max: theoretical ceiling 682.5 tok/s; 5000 is
        # physically impossible. Old behavior: cohort<5 => auto-pass.
        result = self._run(_entry(value=5000.0), cohort=[])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("PHYSICS-FALLBACK FAIL", result.stdout)

    def test_small_cohort_plausible_value_passes(self):
        result = self._run(_entry(value=210.0), cohort=[])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PHYSICS-FALLBACK PASS", result.stdout)

    def test_degenerate_mad_zero_cohort_uses_physics(self):
        cohort = [_entry(id=f"bm-{i}", value=210.0) for i in range(6)]
        result = self._run(_entry(value=5000.0), cohort=cohort)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_healthy_cohort_still_uses_mad(self):
        values = [200.0, 205.0, 210.0, 215.0, 220.0, 212.0]
        cohort = [_entry(id=f"bm-{i}", value=v) for i, v in enumerate(values)]
        result = self._run(_entry(value=211.0), cohort=cohort)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS (z=", result.stdout)
        # And a statistical outlier is still caught the classic way.
        result = self._run(_entry(value=600.0), cohort=cohort)
        self.assertEqual(result.returncode, 1)
        self.assertIn("OUTLIER", result.stdout)


class TestPhysicsCheckCLI(unittest.TestCase):
    """scripts/physics_check.py end-to-end against the real catalog."""

    def _run(self, entry: dict, tier: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "input.jsonl"
            inp.write_text(json.dumps(entry) + "\n")
            return subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "physics_check.py"),
                 "--input", str(inp), "--tier", tier],
                capture_output=True, text=True)

    def test_trusted_tier_rejects_missing_thermal(self):
        entry = _entry(environment={"thermal_state": "unknown"})
        result = self._run(entry, "trusted")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("thermal", result.stdout)

    def test_curator_tier_tolerates_missing_thermal(self):
        entry = _entry(environment={"thermal_state": "unknown"})
        result = self._run(entry, "curator")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_trusted_tier_accepts_clean_plausible_entry(self):
        result = self._run(_entry(value=210.0), "trusted")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@unittest.skipUnless(os.environ.get("SIGSTORE_LIVE"),
                     "live Fulcio/Rekor signing needs an interactive OIDC "
                     "identity (browser or CI id-token); set SIGSTORE_LIVE=1 "
                     "to run")
class TestSigstoreLive(unittest.TestCase):
    """Full keyless sign -> verify round-trip against sigstore staging.

    Deliberately opt-in: it opens a browser (or consumes an ambient CI
    credential) and needs network access to Fulcio/Rekor.
    """

    def test_sign_and_verify_round_trip(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import sign_benchmark

        entry = _entry()
        signed = sign_benchmark.sign_entry(entry, staging=True)
        self.assertIsInstance(signed["_signature"], dict)
        # NOTE: verification against staging needs the staging trust root;
        # verify_line_detailed uses production, so here we only assert the
        # bundle parses and carries an identity.
        from sigstore.models import Bundle
        bundle = Bundle.from_json(json.dumps(signed["_signature"]))
        self.assertIsNotNone(bundle.signing_certificate)


if __name__ == "__main__":
    unittest.main()
