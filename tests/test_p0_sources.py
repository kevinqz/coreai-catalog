#!/usr/bin/env python3
"""
P0 tests — WP5 "sources-links" (findings A8, D8, E2, E8).

Covers:
- schema/source.schema.json validates sources.yaml (and rejects junk)
- scripts/validate_sources.py checker interface
- scripts/validate_links.py unit logic with mocked responses (no live network)
- scripts/sync_upstream.py removed_from_upstream logic (E2 dead-code fix)

Run: python -m pytest tests/test_p0_sources.py -v
Or:  python -m unittest tests.test_p0_sources -v
"""
from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

import yaml
from jsonschema import Draft202012Validator

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

import sync_upstream  # noqa: E402
import validate_links  # noqa: E402
import validate_sources  # noqa: E402


def _load_sources() -> list[dict]:
    data = yaml.safe_load((_ROOT / "sources.yaml").read_text()) or {}
    return data.get("sources", [])


def _load_schema() -> dict:
    return json.loads((_ROOT / "schema" / "source.schema.json").read_text())


class TestSourceSchema(unittest.TestCase):
    """schema/source.schema.json must accept sources.yaml and reject junk."""

    @classmethod
    def setUpClass(cls):
        cls.schema = _load_schema()
        cls.validator = Draft202012Validator(cls.schema)
        cls.sources = _load_sources()
        cls.valid_entry = {
            "id": "example-source",
            "title": "example/source",
            "type": "github_repository",
            "url": "https://github.com/example/source",
            "owner": "example",
            "repo": "source",
            "trust": "community_secondary",
            "volatility": "medium",
            "last_checked": "2026-07-03",
            "notes": "Example.",
        }

    def _errors(self, entry: dict) -> list:
        return list(self.validator.iter_errors(entry))

    def test_schema_is_valid_jsonschema(self):
        Draft202012Validator.check_schema(self.schema)

    def test_all_sources_validate(self):
        for source in self.sources:
            errors = self._errors(source)
            self.assertEqual(
                errors, [],
                f"source {source.get('id')} invalid: {[e.message for e in errors]}",
            )

    def test_no_duplicate_ids(self):
        ids = [s["id"] for s in self.sources]
        self.assertEqual(len(ids), len(set(ids)))

    def test_valid_entry_accepted(self):
        self.assertEqual(self._errors(self.valid_entry), [])

    def test_invented_trust_rejected(self):
        entry = dict(self.valid_entry, trust="totally_legit")
        self.assertTrue(self._errors(entry))

    def test_invented_volatility_rejected(self):
        entry = dict(self.valid_entry, volatility="extreme")
        self.assertTrue(self._errors(entry))

    def test_invented_type_rejected(self):
        entry = dict(self.valid_entry, type="original_model_source")
        self.assertTrue(self._errors(entry))

    def test_untrusted_host_rejected(self):
        entry = dict(self.valid_entry, url="https://evil.example.com/example/source")
        self.assertTrue(self._errors(entry))

    def test_untrusted_host_prefix_trick_rejected(self):
        # github.com.evil.com must not satisfy the allowlist pattern
        entry = dict(self.valid_entry, url="https://github.com.evil.com/x")
        self.assertTrue(self._errors(entry))

    def test_http_rejected(self):
        entry = dict(self.valid_entry, url="http://github.com/example/source")
        self.assertTrue(self._errors(entry))

    def test_trusted_hosts_accepted(self):
        for url in (
            "https://github.com/apple/coreai-models",
            "https://huggingface.co/mlboydaisuke",
            "https://developer.apple.com/documentation/coreai",
            "https://machinelearning.apple.com/research/core-ai",
            "https://arxiv.org/abs/2406.00001",
        ):
            entry = dict(self.valid_entry, url=url)
            self.assertEqual(self._errors(entry), [], f"{url} should be allowed")

    def test_additional_properties_rejected(self):
        entry = dict(self.valid_entry, description="legacy field")
        self.assertTrue(self._errors(entry))

    def test_missing_required_fields_rejected(self):
        for field in ("id", "title", "type", "url", "owner", "trust",
                      "volatility", "last_checked", "notes"):
            entry = dict(self.valid_entry)
            del entry[field]
            self.assertTrue(self._errors(entry), f"missing {field} should fail")

    def test_bad_last_checked_rejected(self):
        entry = dict(self.valid_entry, last_checked="July 3rd 2026")
        self.assertTrue(self._errors(entry))

    def test_fabric_source_present(self):
        by_id = {s["id"]: s for s in self.sources}
        self.assertIn("coreai-fabric", by_id)
        fabric = by_id["coreai-fabric"]
        self.assertEqual(fabric["type"], "github_repository")
        self.assertEqual(fabric["owner"], "kevinqz")
        self.assertEqual(fabric["repo"], "coreai-fabric")
        self.assertEqual(fabric["trust"], "maintainer_primary")
        self.assertEqual(fabric["volatility"], "low")
        self.assertEqual(fabric["url"], "https://github.com/kevinqz/coreai-fabric")

    def test_vjepa2_entry_fixed(self):
        by_id = {s["id"]: s for s in self.sources}
        vjepa = by_id["vjepa2-upstream"]
        self.assertEqual(vjepa["type"], "huggingface_model")
        self.assertEqual(vjepa["owner"], "facebook")
        self.assertNotIn("name", vjepa)
        self.assertNotIn("description", vjepa)


class TestValidateSourcesChecker(unittest.TestCase):
    """scripts/validate_sources.validate_sources(root) -> list[str]."""

    def test_repo_sources_valid(self):
        self.assertEqual(validate_sources.validate_sources(_ROOT), [])

    def test_bad_entry_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "schema").mkdir()
            (root / "schema" / "source.schema.json").write_text(
                (_ROOT / "schema" / "source.schema.json").read_text()
            )
            bad = {
                "sources": [
                    {
                        "id": "bad-source",
                        "title": "bad",
                        "type": "github_repository",
                        "url": "https://evil.example.com/bad",
                        "owner": "bad",
                        "trust": "invented_trust",
                        "volatility": "high",
                        "last_checked": "2026-07-03",
                        "notes": None,
                    },
                    {
                        "id": "bad-source",
                        "title": "dupe",
                        "type": "github_repository",
                        "url": "https://github.com/x/y",
                        "owner": "x",
                        "trust": "community_primary",
                        "volatility": "low",
                        "last_checked": "2026-07-03",
                        "notes": None,
                    },
                ]
            }
            (root / "sources.yaml").write_text(yaml.safe_dump(bad))
            errors = validate_sources.validate_sources(root)
            self.assertTrue(any("url" in e for e in errors))
            self.assertTrue(any("trust" in e for e in errors))
            self.assertTrue(any("duplicate id" in e for e in errors))

    def test_errors_are_aggregated_not_fail_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "schema").mkdir()
            (root / "schema" / "source.schema.json").write_text(
                (_ROOT / "schema" / "source.schema.json").read_text()
            )
            bad = {"sources": [{"id": "a"}, {"id": "b"}]}
            (root / "sources.yaml").write_text(yaml.safe_dump(bad))
            errors = validate_sources.validate_sources(root)
            # Both invalid entries must be reported in a single pass
            self.assertTrue(any(e.startswith("source a:") for e in errors))
            self.assertTrue(any(e.startswith("source b:") for e in errors))


def _http_error(url: str, code: int) -> HTTPError:
    return HTTPError(url, code, f"HTTP {code}", hdrs=None, fp=io.BytesIO(b""))


class TestLinkChecker(unittest.TestCase):
    """validate_links unit logic with mocked responses — no live network."""

    ENTRY = {"file": "sources.yaml", "id": "x", "field": "url",
             "url": "https://github.com/x/y"}

    def test_collect_urls_reads_local_yaml(self):
        urls = validate_links.collect_urls()
        self.assertGreater(len(urls), 50)
        seen = set()
        for u in urls:
            self.assertIn("url", u)
            self.assertIn("file", u)
            self.assertNotIn(u["url"], seen)  # deduplicated
            seen.add(u["url"])
        # The fabric source URL must be watched
        self.assertIn("https://github.com/kevinqz/coreai-fabric", seen)

    def test_check_url_ok(self):
        with mock.patch.object(validate_links, "_fetch_status", return_value=200):
            result = validate_links.check_url(dict(self.ENTRY))
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["attempts"], 1)

    def test_check_url_404_no_retry(self):
        with mock.patch.object(
            validate_links, "_fetch_status",
            side_effect=_http_error(self.ENTRY["url"], 404),
        ) as fetch:
            result = validate_links.check_url(dict(self.ENTRY), retries=3)
        self.assertFalse(result["ok"])
        self.assertFalse(result["rate_limited"])
        self.assertEqual(result["status"], 404)
        self.assertEqual(fetch.call_count, 1)  # 404 is permanent, no retries

    def test_check_url_transient_then_ok(self):
        with mock.patch.object(
            validate_links, "_fetch_status",
            side_effect=[_http_error(self.ENTRY["url"], 503), 200],
        ), mock.patch.object(validate_links.time, "sleep"):
            result = validate_links.check_url(dict(self.ENTRY), retries=2)
        self.assertTrue(result["ok"])
        self.assertEqual(result["attempts"], 2)

    def test_check_url_rate_limited_not_regression(self):
        with mock.patch.object(
            validate_links, "_fetch_status",
            side_effect=_http_error(self.ENTRY["url"], 429),
        ), mock.patch.object(validate_links.time, "sleep"):
            result = validate_links.check_url(dict(self.ENTRY), retries=1)
        self.assertFalse(result["ok"])
        self.assertTrue(result["rate_limited"])
        report = validate_links.build_report([result])
        self.assertEqual(report["broken"], 0)
        self.assertEqual(report["rate_limited"], 1)

    def test_check_url_network_error_retries_then_broken(self):
        with mock.patch.object(
            validate_links, "_fetch_status",
            side_effect=URLError("connection refused"),
        ) as fetch, mock.patch.object(validate_links.time, "sleep"):
            result = validate_links.check_url(dict(self.ENTRY), retries=2)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], 0)
        self.assertEqual(fetch.call_count, 3)  # 1 attempt + 2 retries
        self.assertIn("connection refused", result["error"])

    def test_build_report_counts(self):
        ok = {"ok": True, "rate_limited": False}
        broken = {"ok": False, "rate_limited": False}
        limited = {"ok": False, "rate_limited": True}
        report = validate_links.build_report([dict(ok), dict(broken), dict(limited)])
        self.assertEqual(report["total"], 3)
        self.assertEqual(report["ok"], 1)
        self.assertEqual(report["broken"], 1)
        self.assertEqual(report["rate_limited"], 1)

    def test_build_issue_body_lists_only_broken(self):
        results = [
            {"file": "catalog.yaml", "id": "good", "field": "source_path",
             "url": "https://github.com/x/good", "ok": True, "rate_limited": False,
             "status": 200},
            {"file": "artifacts.yaml", "id": "gone", "field": "huggingface.url",
             "url": "https://huggingface.co/x/gone", "ok": False,
             "rate_limited": False, "status": 404, "error": "HTTP 404"},
        ]
        report = validate_links.build_report(results)
        body = validate_links.build_issue_body(report)
        self.assertIn("# Availability regression", body)
        self.assertIn("https://huggingface.co/x/gone", body)
        self.assertNotIn("https://github.com/x/good", body)
        self.assertIn("do not open duplicates", body)


class TestSyncUpstreamRemoved(unittest.TestCase):
    """sync_upstream removed_from_upstream logic (E2 fix) — pure functions only."""

    UPSTREAM = {f"model-{i}-coreai" for i in range(6)}

    def _model(self, mid: str, group: str = "zoo") -> dict:
        return {"id": mid, "source_group": group, "artifact_ref": f"{mid}-artifact"}

    def test_parse_zoo_readme(self):
        readme = (
            "| Model | Repo | License |\n"
            "|---|---|---|\n"
            "| **Qwen3 VL 2B** (vision-language) | [🤗 repo](https://huggingface.co/mlboydaisuke/qwen3-vl-2b-coreai) | Apache-2.0 |\n"
            "| not a model row | plain text |\n"
        )
        models = sync_upstream.parse_zoo_readme(readme)
        self.assertEqual(list(models), ["Qwen3 VL 2B"])
        self.assertEqual(models["Qwen3 VL 2B"]["hf_repo"], "mlboydaisuke/qwen3-vl-2b-coreai")

    def test_parse_zoo_readme_linked_name(self):
        # Regression: rows whose model name is a markdown link — `[**Name**](doc)`
        # — must parse just like bare `**Name**` rows. The zoo README uses this
        # form for ~half its models (Qwen3.5, Gemma 4 12B, LFM2.5, Parakeet…);
        # the old regex silently dropped them, flagging live models as removed.
        readme = (
            "| Model | Download | Run | License |\n"
            "|---|---|---|---|\n"
            "| [**Qwen3.5-0.8B**](zoo/qwen3.5.md) | "
            "[🤗 qwen3.5-0.8B-CoreAI](https://huggingface.co/mlboydaisuke/qwen3.5-0.8B-CoreAI) | "
            "[ChatDemo](x) | Apache-2.0 |\n"
            "| [**Gemma 4 12B**](zoo/gemma4-12b.md) (dense, Mac-only) | "
            "[🤗 Gemma-4-12B-CoreAI](https://huggingface.co/mlboydaisuke/Gemma-4-12B-CoreAI) | "
            "[ChatDemo](x) | Gemma |\n"
        )
        models = sync_upstream.parse_zoo_readme(readme)
        self.assertIn("Qwen3.5-0.8B", models)
        self.assertEqual(
            models["Qwen3.5-0.8B"]["hf_repo"], "mlboydaisuke/qwen3.5-0.8B-CoreAI"
        )
        self.assertIn("Gemma 4 12B", models)
        self.assertEqual(models["Gemma 4 12B"]["desc"], "dense, Mac-only")

    def test_extract_hf_repos_multi_repo_row(self):
        # A single row can list several artifacts (Qwen3-VL 2B/4B/8B). Removal
        # detection must see *every* repo, not just the first, or the extra
        # sizes get flagged as removed-from-upstream.
        readme = (
            "| [**Qwen3-VL**](zoo/qwen3-vl.md) | "
            "[🤗 2B](https://huggingface.co/mlboydaisuke/Qwen3-VL-2B-CoreAI) · "
            "[4B](https://huggingface.co/mlboydaisuke/Qwen3-VL-4B-CoreAI) · "
            "[8B](https://huggingface.co/mlboydaisuke/Qwen3-VL-8B-CoreAI) | VLChat | Apache-2.0 |\n"
        )
        repos = sync_upstream.extract_hf_repos(readme)
        self.assertEqual(
            repos,
            {"Qwen3-VL-2B-CoreAI", "Qwen3-VL-4B-CoreAI", "Qwen3-VL-8B-CoreAI"},
        )

    def test_repo_matches_fuzzy(self):
        self.assertTrue(sync_upstream.repo_matches("Qwen3-VL-2B-CoreAI",
                                                   {"qwen3-vl-2b-coreai-4bit"}))
        self.assertFalse(sync_upstream.repo_matches("gemma-4-12b", {"qwen3-vl-2b"}))

    def test_removed_model_detected(self):
        models = [self._model("model-0"), self._model("vanished")]
        artifact_repos = {
            "model-0-artifact": "model-0-coreai",
            "vanished-artifact": "vanished-coreai",
        }
        removed = sync_upstream.compute_removed(models, artifact_repos, self.UPSTREAM)
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["model_id"], "vanished")
        self.assertEqual(removed[0]["artifact_id"], "vanished-artifact")
        self.assertEqual(removed[0]["hf_repo"], "vanished-coreai")

    def test_external_models_not_flagged(self):
        models = [self._model("indie", group="external")]
        artifact_repos = {"indie-artifact": "indie-coreai"}
        removed = sync_upstream.compute_removed(models, artifact_repos, self.UPSTREAM)
        self.assertEqual(removed, [])

    def test_present_models_not_flagged(self):
        models = [self._model(f"model-{i}") for i in range(6)]
        artifact_repos = {f"model-{i}-artifact": f"model-{i}-coreai" for i in range(6)}
        removed = sync_upstream.compute_removed(models, artifact_repos, self.UPSTREAM)
        self.assertEqual(removed, [])

    def test_hf_repo_live_only_404_is_removed(self):
        # README-absence is a weak signal — models get indexed from conversion
        # scripts, Apple's repo, or prose mentions, so plenty of live artifacts
        # never appear in a README table. Only a definitive 404 means the
        # artifact is actually gone. 200 → live; 401 (gated) → live; network
        # hiccup → live (never false-flag a removal on a transient error).
        def opener_200(url, timeout=0):
            class R:
                status = 200
                def __enter__(self): return self
                def __exit__(self, *a): return False
            return R()

        def opener_404(url, timeout=0):
            raise HTTPError(url, 404, "Not Found", {}, None)

        def opener_401(url, timeout=0):
            raise HTTPError(url, 401, "Unauthorized", {}, None)

        def opener_boom(url, timeout=0):
            raise URLError("connection reset")

        self.assertTrue(sync_upstream.hf_repo_live("x/y", _opener=opener_200))
        self.assertFalse(sync_upstream.hf_repo_live("x/y", _opener=opener_404))
        self.assertTrue(sync_upstream.hf_repo_live("x/y", _opener=opener_401))
        self.assertTrue(sync_upstream.hf_repo_live("x/y", _opener=opener_boom))

    def test_parse_failure_guard(self):
        # An implausibly small upstream set (README format change / truncated
        # fetch) must not flag the whole catalog as removed.
        models = [self._model("model-0"), self._model("model-1")]
        artifact_repos = {
            "model-0-artifact": "model-0-coreai",
            "model-1-artifact": "model-1-coreai",
        }
        removed = sync_upstream.compute_removed(models, artifact_repos, {"something-else"})
        self.assertEqual(removed, [])

    def test_repo_catalog_has_no_removed_models_against_own_artifacts(self):
        # Sanity: with upstream == our own artifact repos, nothing is removed.
        catalog = yaml.safe_load((_ROOT / "catalog.yaml").read_text())
        artifacts = yaml.safe_load((_ROOT / "artifacts.yaml").read_text())
        repo_by_id = {
            a["id"]: (a.get("huggingface", {}) or {}).get("repo", "")
            for a in artifacts.get("artifacts", [])
        }
        upstream = {r for r in repo_by_id.values() if r}
        removed = sync_upstream.compute_removed(
            catalog.get("models", []), repo_by_id, upstream
        )
        self.assertEqual(removed, [])


if __name__ == "__main__":
    unittest.main()
