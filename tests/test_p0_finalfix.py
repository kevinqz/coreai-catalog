#!/usr/bin/env python3
"""
P0 tests — final-fixer pass (adversarial-review findings on the P0 work).

Covers:
- scripts/audit.py fabric↔external group pairing: a `source_group: fabric`
  model whose artifact has `group: external` passes the cross-reference
  audit (the advertised fabric contribution lane is completable), and the
  category-10 guard rejects `license_terms: permissive` on unverified
  (trust=needs_review / owner=unknown) upstreams
- coreai_catalog/contribute.py open_contribution_pr: the branch is pushed
  (`git push -u origin <branch>`) BEFORE `gh pr create`, and a failing step
  returns the user to the original branch with an actionable message
- coreai_catalog/cli.py `install --json`: exits 1 on download_failed /
  verification_failed (sha256 mismatch) and includes the manifest's
  verification block in the JSON output
- .github/workflows/benchmark-validate.yml enforces the CONTRIBUTING claim
  that a benchmark PR touches benchmarks.jsonl and nothing else
- scripts/doc_test.py retired-reference guard: discovery surfaces are clean
  today, and a reintroduced `benchmarks.yaml` mention is caught
- upstreams.yaml: no unverified original_model_source claims permissive
  license_terms; their models do not claim commercial_use=likely

Run: python -m pytest tests/test_p0_finalfix.py -v
"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import types
import unittest
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

import audit  # noqa: E402  (scripts/audit.py)
import doc_test  # noqa: E402  (scripts/doc_test.py)
from coreai_catalog import cli, contribute  # noqa: E402


class TestFabricGroupPairing(unittest.TestCase):
    """Finding 1 (critical): audit must accept fabric model ↔ external artifact."""

    def test_identity_pairings_still_ok(self):
        for group in ("zoo", "official", "external", "unknown"):
            self.assertTrue(audit.group_pairing_ok(group, group))

    def test_fabric_pairs_with_external_only(self):
        self.assertTrue(audit.group_pairing_ok("fabric", "external"))
        self.assertFalse(audit.group_pairing_ok("fabric", "zoo"))
        self.assertFalse(audit.group_pairing_ok("fabric", "official"))
        self.assertFalse(audit.group_pairing_ok("fabric", "unknown"))

    def test_mismatches_still_flagged(self):
        self.assertFalse(audit.group_pairing_ok("zoo", "external"))
        self.assertFalse(audit.group_pairing_ok("external", "zoo"))

    def test_contribute_mapping_agrees_with_audit(self):
        # build_artifact_entry maps fabric → external; the audit must accept
        # exactly that pairing (shared field contract, no drift).
        fields = {
            "id": "fabric-model-x",
            "source_group": "fabric",
            "hf_owner": "someone",
            "hf_repo": "fabric-model-x",
        }
        entry = contribute.build_artifact_entry(fields)
        self.assertEqual(entry["group"], "external")
        self.assertTrue(audit.group_pairing_ok("fabric", entry["group"]))
        self.assertFalse(entry["officiality"]["apple_export_recipe"])

    def test_full_audit_green_with_fabric_model(self):
        """End-to-end: a fabric model + external artifact passes audit.main()."""
        import copy
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            catalog = yaml.safe_load((_ROOT / "catalog.yaml").read_text())
            artifacts = yaml.safe_load((_ROOT / "artifacts.yaml").read_text())

            model = copy.deepcopy(catalog["models"][0])
            artifact = copy.deepcopy(
                next(a for a in artifacts["artifacts"] if a["id"] == model["artifact_ref"])
            )
            model["id"] = "fabric-test-model"
            model["artifact_ref"] = "fabric-test-model"
            model["source_group"] = "fabric"
            artifact["id"] = "fabric-test-model"
            artifact["group"] = "external"
            artifact["officiality"] = {
                "apple_export_recipe": False,
                "apple_hosted_artifact": False,
                "community_packaged": True,
            }
            catalog["models"].append(model)
            artifacts["artifacts"].append(artifact)
            artifacts.setdefault("metadata", {})["count"] = len(artifacts["artifacts"])

            (tmp_root / "catalog.yaml").write_text(yaml.safe_dump(catalog))
            (tmp_root / "artifacts.yaml").write_text(yaml.safe_dump(artifacts))
            for name in ("terms.yaml", "upstreams.yaml", "sources.yaml",
                         "benchmarks.jsonl"):
                (tmp_root / name).write_text((_ROOT / name).read_text())

            original_root = audit.ROOT
            audit.ROOT = tmp_root
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = audit.main()
            finally:
                audit.ROOT = original_root
            self.assertEqual(
                rc, 0,
                f"audit flagged the fabric model:\n{buf.getvalue()}",
            )


class TestOpenContributionPrPushesBeforePr(unittest.TestCase):
    """Finding 2 (major): the branch must be pushed before gh pr create."""

    def _run_with_fake_subprocess(self, fail_on=None):
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            result = types.SimpleNamespace(returncode=0, stdout="", stderr="")
            if cmd[:2] == ["git", "rev-parse"]:
                result.stdout = "main\n"
            if fail_on and cmd[: len(fail_on)] == fail_on:
                result.returncode = 1
                result.stderr = "remote: permission denied"
            return result

        original = contribute.subprocess.run
        contribute.subprocess.run = fake_run
        try:
            ok, message = contribute.open_contribution_pr(
                _ROOT, "test-model", ["catalog.yaml"], ["evidence line"]
            )
        finally:
            contribute.subprocess.run = original
        return ok, message, calls

    def test_push_step_present_and_before_pr_create(self):
        ok, message, calls = self._run_with_fake_subprocess()
        self.assertTrue(ok, message)
        push_idx = next(
            (i for i, c in enumerate(calls) if c[:2] == ["git", "push"]), None
        )
        pr_idx = next(
            (i for i, c in enumerate(calls) if c[:3] == ["gh", "pr", "create"]), None
        )
        self.assertIsNotNone(push_idx, f"no git push in steps: {calls}")
        self.assertIsNotNone(pr_idx, f"no gh pr create in steps: {calls}")
        self.assertLess(push_idx, pr_idx, "push must run before gh pr create")
        push_cmd = calls[push_idx]
        self.assertEqual(push_cmd[:4], ["git", "push", "-u", "origin"])
        self.assertNotIn("--force", push_cmd)

    def test_push_failure_reports_hint_and_restores_branch(self):
        ok, message, calls = self._run_with_fake_subprocess(
            fail_on=["git", "push"]
        )
        self.assertFalse(ok)
        self.assertIn("git push", message)
        self.assertIn("gh auth status", message)
        # Never reaches gh pr create.
        self.assertFalse(any(c[:3] == ["gh", "pr", "create"] for c in calls))
        # Returns the user to the branch they started on.
        self.assertIn(["git", "checkout", "main"], calls)


class TestInstallJsonExitCodes(unittest.TestCase):
    """Finding 5 (major): install --json must not exit 0 on failed installs."""

    MODEL_ID = "qwen3-5-0-8b"  # real catalog entry

    def _run_install_json(self, file_layout, verification=None):
        manifest = {
            "verified": {"file_layout": file_layout},
            "verification": verification
            or {"status": "unavailable", "files_verified": 0},
        }
        originals = (cli.install_model, cli.is_installed)
        cli.install_model = lambda **kwargs: manifest
        cli.is_installed = lambda model_id: False
        try:
            parser = cli.build_parser()
            args = parser.parse_args(["install", self.MODEL_ID, "--json"])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = args.func(args)
        finally:
            cli.install_model, cli.is_installed = originals
        return rc, json.loads(buf.getvalue())

    def test_verification_failed_exits_1_with_verification_block(self):
        verification = {
            "status": "failed",
            "files_verified": 3,
            "mismatched": ["model.aimodel/weights.bin"],
            "missing": [],
        }
        rc, out = self._run_install_json("verification_failed", verification)
        self.assertEqual(rc, 1)
        self.assertEqual(out["status"], "verification_failed")
        self.assertEqual(out["verification"]["status"], "failed")
        self.assertEqual(
            out["verification"]["mismatched"], ["model.aimodel/weights.bin"]
        )

    def test_download_failed_exits_1(self):
        rc, out = self._run_install_json("download_failed")
        self.assertEqual(rc, 1)
        self.assertEqual(out["status"], "download_failed")

    def test_downloaded_and_manual_required_exit_0(self):
        for layout in ("downloaded", "manual_required"):
            rc, out = self._run_install_json(layout)
            self.assertEqual(rc, 0, f"file_layout={layout} should exit 0")
            self.assertEqual(out["status"], layout)


class TestBenchmarkLaneEnforcement(unittest.TestCase):
    """Finding 4 (major): the 'touch no other file' claim must be enforced."""

    WORKFLOW = _ROOT / ".github" / "workflows" / "benchmark-validate.yml"

    def test_workflow_rejects_prs_touching_other_files(self):
        text = self.WORKFLOW.read_text()
        self.assertIn("Check PR touches only benchmarks.jsonl", text)
        # The step diffs ALL changed files (not just benchmarks.jsonl) and
        # fails when anything else changed.
        self.assertIn("git diff --name-only", text)
        self.assertIn("grep -v '^benchmarks\\.jsonl$'", text)
        self.assertIn("exit 1", text)

    def test_contributing_claim_matches_enforcement(self):
        contributing = (_ROOT / "CONTRIBUTING.md").read_text()
        self.assertIn("makes the PR unmergeable", contributing)


class TestRetiredReferenceGuard(unittest.TestCase):
    """Finding 3 (major): stale discovery docs + a guard against recurrence."""

    def test_current_discovery_surfaces_are_clean(self):
        count, errors = doc_test.check_retired_references()
        self.assertGreater(count, 0)
        self.assertEqual(errors, [], "\n".join(errors))

    def test_specific_surfaces_no_longer_reference_retired_stores(self):
        for rel in ("README.md", "llms.txt", "llms-full.txt",
                    ".github/copilot-instructions.md", "PROJECT_PHILOSOPHY.md",
                    "docs/generated-files.md"):
            text = (_ROOT / rel).read_text().lower()
            for line in text.splitlines():
                if "benchmarks.yaml" in line or "check_sources.sh" in line:
                    self.assertTrue(
                        any(m in line for m in doc_test.RETIRED_ALLOW_MARKERS),
                        f"{rel} still references a retired store: {line!r}",
                    )

    def test_guard_catches_reintroduced_reference(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            (tmp_root / "README.md").write_text(
                "Add your row to `benchmarks.yaml` (append-only).\n"
            )
            original_root = doc_test.ROOT
            doc_test.ROOT = tmp_root
            try:
                _, errors = doc_test.check_retired_references()
            finally:
                doc_test.ROOT = original_root
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("benchmarks.yaml", errors[0])
        self.assertIn("README.md:1", errors[0])

    def test_guard_allows_retirement_notes(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            (tmp_root / "README.md").write_text(
                "The legacy benchmarks.yaml store is retired; use benchmarks.jsonl.\n"
            )
            original_root = doc_test.ROOT
            doc_test.ROOT = tmp_root
            try:
                _, errors = doc_test.check_retired_references()
            finally:
                doc_test.ROOT = original_root
        self.assertEqual(errors, [])


class TestUnverifiedUpstreamLicenseTerms(unittest.TestCase):
    """Finding 6 (major): unverified upstreams must not claim permissive."""

    @classmethod
    def setUpClass(cls):
        cls.upstreams = yaml.safe_load((_ROOT / "upstreams.yaml").read_text())
        cls.catalog = yaml.safe_load((_ROOT / "catalog.yaml").read_text())
        cls.models = {m["id"]: m for m in cls.catalog["models"]}

    def _unverified_original_sources(self):
        for u in self.upstreams.get("original_model_sources", []) or []:
            if u.get("trust") == "needs_review" or u.get("owner") == "unknown":
                yield u

    def test_no_unverified_upstream_claims_permissive(self):
        offenders = [
            u["id"] for u in self._unverified_original_sources()
            if u.get("license_terms") == "permissive"
        ]
        self.assertEqual(offenders, [])

    def test_models_of_unverified_upstreams_use_check_license(self):
        for u in self._unverified_original_sources():
            for model_id in u.get("applies_to", []) or []:
                model = self.models.get(model_id)
                self.assertIsNotNone(model, f"{u['id']} → unknown model {model_id}")
                self.assertEqual(
                    model["license"]["commercial_use"], "check_license",
                    f"model {model_id} (upstream {u['id']} unverified) must "
                    "not claim commercial_use=likely",
                )

    def test_audit_guard_flags_permissive_on_needs_review(self):
        """The audit category-10 guard fires on a violating upstream."""
        import copy
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            upstreams = copy.deepcopy(self.upstreams)
            for u in upstreams["original_model_sources"]:
                if u["id"] == "nanbeige":
                    u["license_terms"] = "permissive"
            (tmp_root / "upstreams.yaml").write_text(yaml.safe_dump(upstreams))
            for name in ("catalog.yaml", "artifacts.yaml", "terms.yaml",
                         "sources.yaml", "benchmarks.jsonl"):
                (tmp_root / name).write_text((_ROOT / name).read_text())

            original_root = audit.ROOT
            audit.ROOT = tmp_root
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = audit.main()
            finally:
                audit.ROOT = original_root
        self.assertEqual(rc, 1)
        self.assertIn("nanbeige", buf.getvalue())
        self.assertIn("review_required", buf.getvalue())

    def test_full_audit_is_green(self):
        result = subprocess.run(
            [sys.executable, str(_ROOT / "scripts" / "audit.py")],
            capture_output=True, text=True, cwd=str(_ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
