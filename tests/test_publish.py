#!/usr/bin/env python3
"""
Tests for the publish workflow helpers (version bumping + pre-flight logic).

These tests cover the pure logic in ``coreai_catalog.publish`` — they do
NOT hit PyPI, git, or the network.  Subprocess execution is mocked via
monkeypatching ``coreai_catalog.publish._run``.

Run: env -u PYTHONPATH .venv/bin/python -m pytest tests/test_publish.py -v
"""
from __future__ import annotations

import subprocess
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from coreai_catalog import publish
from coreai_catalog.publish import (
    PreflightError,
    bump_version_in_catalog_yaml,
    bump_version_in_pyproject,
    build_dist,
    git_commit_and_tag,
    git_push,
    read_catalog_version,
    read_pyproject_version,
    run_preflight_checks,
    suggest_next_version,
    upload_to_pypi,
    validate_version,
)


# ── validate_version ────────────────────────────────────────────────────


class TestValidateVersion(unittest.TestCase):
    """validate_version accepts valid semver and rejects junk."""

    def test_valid_versions(self):
        for v in ["0.0.0", "1.0.0", "2.1.0", "10.20.30", "99.99.99"]:
            self.assertEqual(validate_version(v), v)

    def test_strips_whitespace(self):
        self.assertEqual(validate_version("  2.1.0  "), "2.1.0")

    def test_reject_non_string(self):
        with self.assertRaises(ValueError):
            validate_version(None)  # type: ignore
        with self.assertRaises(ValueError):
            validate_version(210)  # type: ignore

    def test_reject_two_components(self):
        with self.assertRaises(ValueError):
            validate_version("2.1")

    def test_reject_pre_release(self):
        with self.assertRaises(ValueError):
            validate_version("2.1.0-rc1")
        with self.assertRaises(ValueError):
            validate_version("2.1.0+build5")

    def test_reject_leading_zeros(self):
        with self.assertRaises(ValueError):
            validate_version("02.1.0")

    def test_reject_alpha(self):
        with self.assertRaises(ValueError):
            validate_version("abc")
        with self.assertRaises(ValueError):
            validate_version("")


# ── suggest_next_version ────────────────────────────────────────────────


class TestSuggestNextVersion(unittest.TestCase):

    def test_patch_bump(self):
        self.assertEqual(suggest_next_version("2.1.0", "patch"), "2.1.1")

    def test_minor_bump(self):
        self.assertEqual(suggest_next_version("2.1.0", "minor"), "2.2.0")

    def test_major_bump(self):
        self.assertEqual(suggest_next_version("2.1.0", "major"), "3.0.0")

    def test_carry_over_high_values(self):
        self.assertEqual(suggest_next_version("1.9.9", "minor"), "1.10.0")
        self.assertEqual(suggest_next_version("1.9.9", "patch"), "1.9.10")

    def test_zero_after_major(self):
        v = suggest_next_version("5.3.7", "major")
        self.assertEqual(v, "6.0.0")

    def test_default_is_patch(self):
        self.assertEqual(suggest_next_version("1.0.0"), "1.0.1")

    def test_invalid_current(self):
        with self.assertRaises(ValueError):
            suggest_next_version("bad", "patch")

    def test_invalid_bump_type(self):
        with self.assertRaises(ValueError):
            suggest_next_version("1.0.0", "hotfix")


# ── bump_version_in_catalog_yaml ────────────────────────────────────────


class TestBumpCatalogYaml(unittest.TestCase):
    """bump_version_in_catalog_yaml updates metadata.version correctly."""

    def _write_catalog(self, tmp_path: Path, version: str) -> Path:
        p = tmp_path / "catalog.yaml"
        p.write_text(textwrap.dedent(f"""\
            metadata:
              name: Core AI Catalog
              version: {version}
              last_verified: '2026-07-01'
            models:
            - id: test-model
              name: Test
        """))
        return p

    def test_updates_version(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = self._write_catalog(Path(td), "2.1.0")
            bump_version_in_catalog_yaml(p, "2.2.0")
            self.assertEqual(read_catalog_version(p), "2.2.0")

    def test_preserves_other_keys(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = self._write_catalog(Path(td), "2.1.0")
            bump_version_in_catalog_yaml(p, "2.2.0")
            import yaml
            data = yaml.safe_load(p.read_text())
            self.assertEqual(data["metadata"]["name"], "Core AI Catalog")
            self.assertEqual(data["metadata"]["last_verified"], "2026-07-01")
            self.assertEqual(len(data["models"]), 1)

    def test_rejects_invalid_version(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = self._write_catalog(Path(td), "2.1.0")
            with self.assertRaises(ValueError):
                bump_version_in_catalog_yaml(p, "not-a-version")
            # File should be unchanged since we validate before writing
            self.assertEqual(read_catalog_version(p), "2.1.0")

    def test_missing_metadata_raises(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "catalog.yaml"
            p.write_text("models: []\n")
            with self.assertRaises(ValueError):
                bump_version_in_catalog_yaml(p, "2.2.0")


# ── bump_version_in_pyproject ───────────────────────────────────────────


class TestBumpPyproject(unittest.TestCase):

    _TEMPLATE = textwrap.dedent("""\
        [build-system]
        requires = ["setuptools>=68.0", "wheel"]
        build-backend = "setuptools.build_meta"

        [project]
        name = "coreai-catalog"
        version = "2.1.0"
        description = "Discover, compare, and install Core AI models."
    """)

    def test_updates_version(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "pyproject.toml"
            p.write_text(self._TEMPLATE)
            bump_version_in_pyproject(p, "2.2.0")
            self.assertEqual(read_pyproject_version(p), "2.2.0")

    def test_preserves_rest_of_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "pyproject.toml"
            original = self._TEMPLATE
            p.write_text(original)
            bump_version_in_pyproject(p, "3.0.0")
            content = p.read_text()
            # Everything except the version line should be preserved
            self.assertIn('[build-system]', content)
            self.assertIn('name = "coreai-catalog"', content)
            self.assertIn('build-backend = "setuptools.build_meta"', content)

    def test_rejects_invalid_version(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "pyproject.toml"
            p.write_text(self._TEMPLATE)
            with self.assertRaises(ValueError):
                bump_version_in_pyproject(p, "2.2")
            # Unchanged
            self.assertEqual(read_pyproject_version(p), "2.1.0")

    def test_handles_single_quotes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "pyproject.toml"
            content = self._TEMPLATE.replace('"2.1.0"', "'2.1.0'")
            p.write_text(content)
            bump_version_in_pyproject(p, "2.2.0")
            self.assertEqual(read_pyproject_version(p), "2.2.0")

    def test_missing_version_raises(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "pyproject.toml"
            p.write_text("[project]\nname = \"x\"\n")
            with self.assertRaises(ValueError):
                bump_version_in_pyproject(p, "2.2.0")


# ── run_preflight_checks ────────────────────────────────────────────────


class TestPreflightChecks(unittest.TestCase):
    """run_preflight_calls runs validate.py + pytest, fails on non-zero exit."""

    def setUp(self):
        self.repo = Path("/fake/repo")
        # Patch _run so no real subprocesses fire
        self._patcher = patch("coreai_catalog.publish._run")
        self.mock_run = self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_all_pass(self):
        self.mock_run.return_value = MagicMock(returncode=0)
        results = run_preflight_checks(self.repo)
        self.assertEqual(len(results), 2)
        self.assertIn("validate.py passed", results[0])
        self.assertIn("pytest passed", results[1])
        self.assertEqual(self.mock_run.call_count, 2)

    def test_validate_fails_raises(self):
        def side_effect(cmd, **kwargs):
            if "validate.py" in " ".join(cmd):
                raise subprocess.CalledProcessError(1, cmd)
            return MagicMock(returncode=0)
        self.mock_run.side_effect = side_effect

        with self.assertRaises(PreflightError) as ctx:
            run_preflight_checks(self.repo)
        self.assertIn("validate.py", str(ctx.exception))

    def test_pytest_fails_raises(self):
        call_count = {"n": 0}

        def side_effect(cmd, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:  # second call is pytest
                raise subprocess.CalledProcessError(1, cmd)
            return MagicMock(returncode=0)
        self.mock_run.side_effect = side_effect

        with self.assertRaises(PreflightError) as ctx:
            run_preflight_checks(self.repo)
        self.assertIn("pytest", str(ctx.exception))

    def test_custom_runner(self):
        self.mock_run.return_value = MagicMock(returncode=0)
        custom = ["/custom/python"]
        run_preflight_checks(self.repo, runner=custom)
        # Check first call uses custom runner
        first_call_args = self.mock_run.call_args_list[0][0][0]
        self.assertEqual(first_call_args[0], "/custom/python")

    def test_uses_sys_executable_by_default(self):
        self.mock_run.return_value = MagicMock(returncode=0)
        run_preflight_checks(self.repo)
        first_call_args = self.mock_run.call_args_list[0][0][0]
        self.assertEqual(first_call_args[0], __import__("sys").executable)


# ── git_commit_and_tag ──────────────────────────────────────────────────


class TestGitCommitAndTag(unittest.TestCase):

    def setUp(self):
        self._patcher = patch("coreai_catalog.publish._run")
        self.mock_run = self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_creates_tag(self):
        self.mock_run.return_value = MagicMock(returncode=0)
        tag = git_commit_and_tag(Path("/repo"), "2.2.0")
        self.assertEqual(tag, "v2.2.0")
        # Should call: git add, git commit, git tag
        self.assertEqual(self.mock_run.call_count, 3)
        # Third call is git tag v2.2.0
        tag_cmd = self.mock_run.call_args_list[2][0][0]
        self.assertEqual(tag_cmd, ["git", "tag", "v2.2.0"])

    def test_custom_message(self):
        self.mock_run.return_value = MagicMock(returncode=0)
        git_commit_and_tag(Path("/repo"), "2.2.0", message="custom msg")
        commit_cmd = self.mock_run.call_args_list[1][0][0]
        self.assertEqual(commit_cmd, ["git", "commit", "-m", "custom msg"])

    def test_default_message(self):
        self.mock_run.return_value = MagicMock(returncode=0)
        git_commit_and_tag(Path("/repo"), "2.2.0")
        commit_cmd = self.mock_run.call_args_list[1][0][0]
        self.assertEqual(commit_cmd, ["git", "commit", "-m", "Release v2.2.0"])

    def test_invalid_version_raises(self):
        with self.assertRaises(ValueError):
            git_commit_and_tag(Path("/repo"), "bad")


# ── build_dist ──────────────────────────────────────────────────────────


class TestBuildDist(unittest.TestCase):

    def setUp(self):
        self._patcher = patch("coreai_catalog.publish._run")
        self.mock_run = self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_calls_python_build(self):
        self.mock_run.return_value = MagicMock(returncode=0)
        build_dist(Path("/repo"))
        cmd = self.mock_run.call_args[0][0]
        self.assertIn("-m", cmd)
        self.assertIn("build", cmd)


# ── upload_to_pypi ──────────────────────────────────────────────────────


class TestUploadToPypi(unittest.TestCase):

    def setUp(self):
        self._patcher = patch("coreai_catalog.publish._run")
        self.mock_run = self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_missing_token_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                upload_to_pypi(Path("/repo"))
            self.assertIn("PYPI_API_TOKEN", str(ctx.exception))

    def test_with_token_calls_twine(self):
        self.mock_run.return_value = MagicMock(returncode=0)
        with patch.dict("os.environ", {"PYPI_API_TOKEN": "pypi-test-token"}):
            upload_to_pypi(Path("/repo"))
        cmd = self.mock_run.call_args[0][0]
        self.assertEqual(cmd[0], "twine")
        self.assertEqual(cmd[1], "upload")


# ── git_push ────────────────────────────────────────────────────────────


class TestGitPush(unittest.TestCase):

    def setUp(self):
        self._patcher = patch("coreai_catalog.publish._run")
        self.mock_run = self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_calls_push_follow_tags(self):
        self.mock_run.return_value = MagicMock(returncode=0)
        git_push(Path("/repo"))
        cmd = self.mock_run.call_args[0][0]
        self.assertEqual(cmd, ["git", "push", "--follow-tags"])


# ── CLI integration (argparse wiring) ───────────────────────────────────


class TestPublishCLIWiring(unittest.TestCase):
    """Verify the publish subparser is registered with expected flags."""

    def test_publish_subcommand_exists(self):
        from coreai_catalog.cli import build_parser
        parser = build_parser()
        # Parse publish with --dry-run
        args = parser.parse_args(["publish", "--dry-run"])
        self.assertTrue(hasattr(args, "func"))
        self.assertEqual(args.func.__name__, "cmd_publish")
        self.assertTrue(args.dry_run)

    def test_publish_version_flag(self):
        from coreai_catalog.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["publish", "--version", "2.5.0"])
        self.assertEqual(args.version, "2.5.0")

    def test_publish_push_flag(self):
        from coreai_catalog.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["publish", "--push"])
        self.assertTrue(args.push)

    def test_publish_yes_flag(self):
        from coreai_catalog.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["publish", "-y"])
        self.assertTrue(args.yes)

    def test_publish_defaults(self):
        from coreai_catalog.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["publish"])
        self.assertFalse(args.dry_run)
        self.assertFalse(args.push)
        self.assertFalse(args.yes)
        self.assertIsNone(args.version)


if __name__ == "__main__":
    unittest.main()
