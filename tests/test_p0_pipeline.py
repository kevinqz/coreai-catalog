"""
P0 pipeline-core tests (redteam findings A5, B6, D2, D5, F7, F9-partial).

Covers:
1. Single benchmark store — benchmarks.jsonl is the one source of truth:
   exports/audit read JSONL, device_class is preserved into exports,
   benchmarks.yaml is retired and audit fails if it reappears.
2. License-upstream join — audit fails when a model claims likely
   commercial use while its upstream's license_terms is
   restricted/review_required.
3. Version single-sourcing — publish bumps all version surfaces
   (catalog.yaml, pyproject.toml, agent.json, openapi.yaml, README.md)
   and hints when CHANGELOG.md lacks the release section.
"""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _load_audit_module():
    """Import scripts/audit.py as a module (scripts/ is not a package)."""
    return importlib.import_module("audit")


def _write_minimal_repo(root: Path, *, models=None, artifacts=None,
                        upstreams=None, benchmarks_jsonl_lines=None) -> None:
    """Write the minimal file set audit.py expects into *root*."""
    (root / "catalog.yaml").write_text(yaml.dump({
        "metadata": {"version": "0.0.1"},
        "models": models or [],
    }))
    (root / "artifacts.yaml").write_text(yaml.dump({
        "metadata": {"count": len(artifacts or [])},
        "artifacts": artifacts or [],
    }))
    (root / "terms.yaml").write_text(yaml.dump({"terms": []}))
    (root / "sources.yaml").write_text(yaml.dump({"sources": []}))
    (root / "upstreams.yaml").write_text(yaml.dump(upstreams or {}))
    lines = benchmarks_jsonl_lines or []
    (root / "benchmarks.jsonl").write_text(
        "".join(json.dumps(l) + "\n" for l in lines)
    )


def _minimal_model(**overrides) -> dict:
    m = {
        "id": "m1",
        "name": "Model One",
        "source_group": "zoo",
        "artifact_ref": "a1",
        "capabilities": [],
        "modalities": {"input": [], "output": []},
        "license": {"name": "Apache-2.0", "commercial_use": "likely"},
    }
    m.update(overrides)
    return m


def _minimal_artifact(**overrides) -> dict:
    a = {
        "id": "a1",
        "group": "zoo",
        "officiality": {
            "apple_export_recipe": False,
            "apple_hosted_artifact": False,
            "community_packaged": True,
        },
    }
    a.update(overrides)
    return a


def _run_audit_in(root: Path) -> int:
    audit = _load_audit_module()
    original_root = audit.ROOT
    try:
        audit.ROOT = root
        return audit.main()
    finally:
        audit.ROOT = original_root


class TestSingleBenchmarkStore(unittest.TestCase):
    """A5/B6/D5/F7 — benchmarks.jsonl is the single source of truth."""

    def test_benchmarks_yaml_is_retired(self):
        self.assertFalse((REPO_ROOT / "benchmarks.yaml").exists(),
                         "benchmarks.yaml must stay deleted")
        self.assertFalse(
            (REPO_ROOT / "coreai_catalog" / "data" / "benchmarks.yaml").exists(),
            "packaged benchmarks.yaml must stay deleted")
        self.assertTrue((REPO_ROOT / "benchmarks.jsonl").exists())

    def test_audit_fails_if_benchmarks_yaml_reappears(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_repo(root)
            self.assertEqual(_run_audit_in(root), 0)
            (root / "benchmarks.yaml").write_text("benchmarks: []\n")
            self.assertEqual(_run_audit_in(root), 1,
                             "audit must fail when benchmarks.yaml reappears")

    def test_audit_fails_if_benchmarks_jsonl_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_repo(root)
            (root / "benchmarks.jsonl").unlink()
            self.assertEqual(_run_audit_in(root), 1)

    def test_audit_catches_duplicate_jsonl_benchmark_ids(self):
        row = {"id": "bm-1", "model_id": "m1", "metric": "decode_throughput",
               "value": 10, "unit": "tokens_per_second", "device_class": "M4",
               "os_major": "27", "compute_unit": "GPU",
               "extraction_method": "upstream_readme_manual",
               "confidence": "medium", "observed_date": "2026-06-25",
               "source": "s1"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_repo(
                root,
                models=[_minimal_model(
                    license={"name": "Apache-2.0", "commercial_use": "likely"})],
                artifacts=[_minimal_artifact()],
                upstreams={"framework_sources": [
                    {"id": "s1", "title": "S", "category": "framework",
                     "trust": "official_primary"},
                ]},
                benchmarks_jsonl_lines=[row, row],
            )
            self.assertEqual(_run_audit_in(root), 1,
                             "duplicate JSONL benchmark IDs must fail audit")

    def test_audit_catches_bad_jsonl_observed_date(self):
        row = {"id": "bm-1", "model_id": "m1", "metric": "decode_throughput",
               "value": 10, "unit": "tokens_per_second", "device_class": "M4",
               "os_major": "27", "compute_unit": "GPU",
               "extraction_method": "upstream_readme_manual",
               "confidence": "medium", "observed_date": "June 25 2026",
               "source": "s1"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_repo(
                root,
                models=[_minimal_model()],
                artifacts=[_minimal_artifact()],
                upstreams={"framework_sources": [
                    {"id": "s1", "title": "S", "category": "framework",
                     "trust": "official_primary"},
                ]},
                benchmarks_jsonl_lines=[row],
            )
            self.assertEqual(_run_audit_in(root), 1,
                             "non-ISO observed_date must fail audit")

    def test_export_json_builds_benchmarks_from_jsonl(self):
        from coreai_catalog.exports import export_json

        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            export_json(REPO_ROOT, dist)
            data = json.loads((dist / "benchmarks.json").read_text())

            jsonl_count = sum(
                1 for l in (REPO_ROOT / "benchmarks.jsonl").read_text().splitlines()
                if l.strip() and not l.strip().startswith("#")
            )
            self.assertEqual(len(data["benchmarks"]), jsonl_count)
            self.assertEqual(data["metadata"]["count"], jsonl_count)
            self.assertEqual(data["metadata"]["source"], "benchmarks.jsonl")
            # JSONL schema-v2 fields survive into the export
            self.assertIn("device_class", data["benchmarks"][0])
            self.assertIn("observed_date", data["benchmarks"][0])

            # Bundle carries the same benchmarks
            bundle = json.loads((dist / "coreai-catalog.json").read_text())
            self.assertEqual(len(bundle["benchmarks"]["benchmarks"]), jsonl_count)

    def test_leaderboard_device_not_null(self):
        """A5 — the JSONL→export reshape must not drop device_class."""
        from coreai_catalog.exports import export_leaderboard

        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            output = export_leaderboard(REPO_ROOT, dist)
            metrics_seen = 0
            for entry in output["leaderboard"]:
                for metric in entry["best_metrics"].values():
                    metrics_seen += 1
                    self.assertIsNotNone(
                        metric["device"],
                        f"{entry['id']} leaderboard device is null "
                        "(device_class dropped in reshape)")
            self.assertGreater(metrics_seen, 0,
                               "leaderboard should contain benchmark metrics")

    def test_reshape_benchmark_aliases_v2_fields(self):
        from coreai_catalog.formatters import reshape_benchmark

        v2 = {"metric": "decode_throughput", "unit": "tokens_per_second",
              "value": 71.9, "device_class": "A18 Pro",
              "observed_date": "2026-06-25", "compute_unit": "GPU",
              "confidence": "medium"}
        out = reshape_benchmark(v2)
        self.assertEqual(out["device"], "A18 Pro")
        self.assertEqual(out["device_class"], "A18 Pro")
        self.assertEqual(out["observed"], "2026-06-25")

        compact = reshape_benchmark(v2, include_extras=False)
        self.assertEqual(compact["device"], "A18 Pro")
        self.assertNotIn("notes", compact)

    def test_catalog_has_no_yaml_fallback(self):
        """Missing JSONL means no benchmarks — never legacy YAML data."""
        from coreai_catalog.catalog import Catalog

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "catalog.yaml").write_text(yaml.dump({
                "metadata": {"version": "test"},
                "models": [{"id": "m1", "capabilities": []}],
            }))
            (root / "benchmarks.yaml").write_text(yaml.dump({
                "benchmarks": [{"id": "b1", "model_id": "m1", "value": 1}],
            }))
            cat = Catalog(root)
            self.assertEqual(cat.benchmarks, [])


class TestLicenseUpstreamJoin(unittest.TestCase):
    """D2 — permissive claims over restricted/review_required upstreams fail."""

    UPSTREAMS = {
        "original_model_sources": [
            {"id": "u1", "title": "Upstream One", "category": "original_model",
             "trust": "original_model_primary",
             "license_terms": "review_required", "applies_to": ["m1"]},
        ],
    }

    def test_likely_over_review_required_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_repo(
                root,
                models=[_minimal_model(
                    license={"name": "Apache-2.0", "commercial_use": "likely"})],
                artifacts=[_minimal_artifact()],
                upstreams=self.UPSTREAMS,
            )
            self.assertEqual(_run_audit_in(root), 1,
                             "likely commercial use over a review_required "
                             "upstream must fail audit")

    def test_likely_over_restricted_fails(self):
        upstreams = {
            "original_model_sources": [
                {"id": "u1", "title": "U", "category": "original_model",
                 "trust": "original_model_primary",
                 "license_terms": "restricted", "applies_to": ["m1"]},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_repo(
                root,
                models=[_minimal_model()],
                artifacts=[_minimal_artifact()],
                upstreams=upstreams,
            )
            self.assertEqual(_run_audit_in(root), 1)

    def test_check_license_over_review_required_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_repo(
                root,
                models=[_minimal_model(
                    license={"name": "Gemma Terms",
                             "commercial_use": "check_license"})],
                artifacts=[_minimal_artifact()],
                upstreams=self.UPSTREAMS,
            )
            self.assertEqual(_run_audit_in(root), 0)

    def test_likely_over_permissive_passes(self):
        upstreams = {
            "original_model_sources": [
                {"id": "u1", "title": "U", "category": "original_model",
                 "trust": "original_model_primary",
                 "license_terms": "permissive", "applies_to": ["m1"]},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_repo(
                root,
                models=[_minimal_model()],
                artifacts=[_minimal_artifact()],
                upstreams=upstreams,
            )
            self.assertEqual(_run_audit_in(root), 0)

    def test_all_original_model_sources_have_license_terms(self):
        """Every model-source upstream record carries a valid license_terms."""
        upstreams = yaml.safe_load((REPO_ROOT / "upstreams.yaml").read_text())
        valid = {"permissive", "weak_copyleft", "restricted", "review_required"}
        for u in upstreams.get("original_model_sources", []):
            self.assertIn(u.get("license_terms"), valid,
                          f"upstream {u['id']} missing/invalid license_terms")


class TestVersionSurfaces(unittest.TestCase):
    """F9 (partial) — publish bumps every version surface."""

    def _make_repo(self, tmp: Path) -> Path:
        (tmp / "catalog.yaml").write_text(yaml.dump({
            "metadata": {"version": "2.1.0"}, "models": [],
        }))
        (tmp / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "2.1.0"\n')
        (tmp / "agent.json").write_text(json.dumps({
            "name": "coreai-catalog", "version": "2.1.0",
            "other": {"version": "not-semver"},
        }, indent=2))
        (tmp / "openapi.yaml").write_text(
            "openapi: 3.1.0\n"
            "info:\n"
            "  title: Core AI Catalog API\n"
            "  version: 2.1.0\n"
            "components:\n"
            "  schemas:\n"
            "    VersionInfo:\n"
            "      properties:\n"
            "        version: { type: string }\n")
        (tmp / "README.md").write_text(
            "# Title\n\n**Version:** v2.1.0 — [PyPI](https://example.com)\n")
        (tmp / "CHANGELOG.md").write_text("# Changelog\n\n## [2.1.0] — 2026-07-02\n")
        return tmp

    def test_bump_all_version_surfaces(self):
        from coreai_catalog.publish import bump_all_version_surfaces

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = self._make_repo(Path(tmpdir))
            results = bump_all_version_surfaces(tmp, "2.2.0")

            cat = yaml.safe_load((tmp / "catalog.yaml").read_text())
            self.assertEqual(cat["metadata"]["version"], "2.2.0")
            self.assertIn('version = "2.2.0"', (tmp / "pyproject.toml").read_text())

            agent = json.loads((tmp / "agent.json").read_text())
            self.assertEqual(agent["version"], "2.2.0")
            self.assertEqual(agent["other"]["version"], "not-semver",
                             "only the semver version field is bumped")

            openapi = (tmp / "openapi.yaml").read_text()
            self.assertIn("  version: 2.2.0", openapi)
            self.assertIn("version: { type: string }", openapi,
                          "schema property line must be untouched")

            self.assertIn("**Version:** v2.2.0", (tmp / "README.md").read_text())

            # CHANGELOG has no 2.2.0 section yet → hint reported
            self.assertTrue(any("CHANGELOG.md missing" in r for r in results))
            self.assertEqual(
                len([r for r in results if "→ 2.2.0" in r]), 5,
                f"expected 5 bumped surfaces, got: {results}")

    def test_changelog_hint_positive(self):
        from coreai_catalog.publish import check_changelog_has_version

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = self._make_repo(Path(tmpdir))
            self.assertTrue(check_changelog_has_version(tmp / "CHANGELOG.md", "2.1.0"))
            self.assertFalse(check_changelog_has_version(tmp / "CHANGELOG.md", "9.9.9"))

    def test_openapi_bump_requires_exactly_one_match(self):
        from coreai_catalog.publish import bump_version_in_openapi_yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "openapi.yaml"
            path.write_text("info:\n  version: 1.0.0\nother:\n  version: 2.0.0\n")
            with self.assertRaises(ValueError):
                bump_version_in_openapi_yaml(path, "3.0.0")

    def test_real_surfaces_currently_agree(self):
        """All live version surfaces carry the same version string."""
        from coreai_catalog.publish import read_catalog_version, read_pyproject_version

        version = read_catalog_version(REPO_ROOT / "catalog.yaml")
        self.assertEqual(read_pyproject_version(REPO_ROOT / "pyproject.toml"), version)
        agent = json.loads((REPO_ROOT / "agent.json").read_text())
        self.assertEqual(agent["version"], version)
        openapi = yaml.safe_load((REPO_ROOT / "openapi.yaml").read_text())
        self.assertEqual(openapi["info"]["version"], version)
        self.assertIn(f"**Version:** v{version}", (REPO_ROOT / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
