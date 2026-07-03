#!/usr/bin/env python3
"""P1 integration tests — CLI wiring, MCP write tools, sanitizer, surfaces.

Covers the integrator work package (spec §4 P1: rows for bench/discover
CLI wiring, §3.1 MCP write tools, D6 sanitizer wiring, F9 surface sync):

1. `coreai-catalog bench run|draft` — actionable errors on this OS
   (macOS < 27 has no runner), candidate drafting from a runner-output
   fixture (fixture shape imported from tests.test_p1_bench — WP-A's
   single-sourced manifest/trials fixtures).
2. `coreai-catalog discover` — wired subcommand; run_discovery against
   injected fixtures (no network).
3. `coreai-catalog install --no-verify` — flag → installer no_verify
   kwarg; verification state surfaced in output (JSON + human).
4. MCP get_integration_snippet — install-free, contract-driven snippet
   for unlimited-ocr with a real image code path (C1/C8).
5. MCP draft_model / submit_model — aggregated errors, would-be diff,
   refusal without confirm=true, refusal on invalid payloads; zero writes
   in every refusal path.
6. Sanitizer (D6) — every documented free-text field in MCP outputs is
   wrapped in UNTRUSTED_CATALOG_DATA delimiters.
7. Surface sync (F9) — agent.json tool count matches the live server
   (the exact assertion CI's smoke test runs), write_tools exist,
   llms.txt / llms-full.txt / AGENTS.md / openapi.yaml mention the new
   surfaces, and the benchmark-record fact matches benchmarks.jsonl.

Run: python3 -m pytest tests/test_p1_integration.py -q
     python3 -m unittest tests.test_p1_integration -v
"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coreai_catalog import bench, cli, discover  # noqa: E402
from mcp_server.sanitize import BEGIN_MARKER  # noqa: E402
from tests.test_p1_bench import (  # noqa: E402  (WP-A's fixtures, single-sourced)
    make_manifest,
    make_trials,
    write_run_output,
)


def run_cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "coreai_catalog", *argv],
        capture_output=True, text=True, cwd=str(ROOT), timeout=120,
    )


def call_cmd(func, *argv: str) -> tuple[int, str]:
    """Parse argv with the real parser and run a cmd_* function in-process."""
    args = cli.build_parser().parse_args(list(argv))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = func(args)
    return rc, buf.getvalue()


VALID_MODEL_PAYLOAD = {
    # A schema-valid draft payload. Enum values verified against
    # schema/model.schema.json + schema/artifact.schema.json; the source id
    # exists in sources.yaml. Synthetic ids — never written by these tests.
    "id": "p1-integration-test-model",
    "name": "P1 Integration Test Model",
    "family": "Test",
    "source_group": "zoo",
    "source_path": "https://github.com/john-rocky/coreai-model-zoo",
    "capabilities": ["chat"],
    "input_modalities": ["text"],
    "output_modalities": ["text"],
    "artifact_format": "aimodel",
    "availability": "available",
    "parameters": "0.5B",
    "precision": "int8",
    "quantization": "int8lin",
    "artifact_size": "500MB",
    "runtime_name": "apple-core-ai",
    "runner": "CoreAIRunner",
    "stock_runtime": True,
    "custom_kernel": False,
    "patch_required": False,
    "tokenizer_required": True,
    "processor_required": False,
    "aot_required": False,
    "iphone": True,
    "ipad": "unknown",
    "mac": True,
    "mac_only": False,
    "license_name": "Apache-2.0",
    "commercial_use": "likely",
    "status": "confirmed",
    "maturity": "experimental",
    "confidence": "medium",
    "sources": ["coreai-model-zoo"],
    "hf_owner": "someone",
    "hf_repo": "some-repo",
}


# ── 1. bench CLI ──


class TestBenchCLI(unittest.TestCase):
    def test_bench_subcommands_registered(self):
        parser = cli.build_parser()
        args = parser.parse_args(["bench", "run", "some-model"])
        self.assertIs(args.func, cli.cmd_bench_run)
        self.assertEqual(args.model_id, "some-model")
        args = parser.parse_args(["bench", "draft", "some-dir"])
        self.assertIs(args.func, cli.cmd_bench_draft)
        self.assertEqual(args.out_dir, "some-dir")

    def test_bench_without_action_is_actionable(self):
        result = run_cli("bench")
        self.assertEqual(result.returncode, 1)
        self.assertIn("run | draft", result.stdout)

    def test_bench_run_uninstalled_model_is_actionable(self):
        mid = "qwen3-embedding-0-6b"
        from coreai_catalog.installer import get_model_dir
        if (get_model_dir(mid) / "manifest.json").exists():
            self.skipTest(f"{mid} happens to be installed on this machine")
        result = run_cli("bench", "run", mid)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not installed", result.stdout)
        self.assertIn(f"coreai-catalog install {mid}", result.stdout)

    def test_runner_missing_error_is_os_aware(self):
        """On this Mac (macOS < 27) the error must say WHY benchmarks
        cannot run here, citing the upstream macOS 27 requirement."""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(bench.BenchError) as ctx:
                bench.locate_runner(root=Path(tmp), env={})
        msg = str(ctx.exception)
        self.assertIn("macOS 27", msg)
        self.assertIn("swift build -c release", msg)
        major = bench.macos_major_version()
        if major is not None and major < 27:
            self.assertIn("cannot run here", msg)

    def test_bench_run_cli_surfaces_bench_error(self):
        with mock.patch.object(
            bench, "bench_run", side_effect=bench.BenchError("fixture failure"),
        ):
            rc, out = call_cmd(cli.cmd_bench_run, "bench", "run", "any-model")
        self.assertEqual(rc, 1)
        self.assertIn("fixture failure", out)

    def test_bench_run_json_error_shape(self):
        with mock.patch.object(
            bench, "bench_run", side_effect=bench.BenchError("fixture failure"),
        ):
            rc, out = call_cmd(
                cli.cmd_bench_run, "bench", "run", "any-model", "--json",
            )
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)["error"], "fixture failure")

    def test_bench_draft_from_runner_output_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            write_run_output(out_dir, make_manifest(), make_trials())
            rc, out = call_cmd(
                cli.cmd_bench_draft, "bench", "draft", str(out_dir), "--json",
            )
            self.assertEqual(rc, 0, out)
            data = json.loads(out)
            line = data["line"]
            self.assertEqual(line["extraction_method"], "app_benchmark_protocol")
            self.assertEqual(line["verification_tier"], "unverified")
            self.assertEqual(line["value"], 200.0)
            # Not installed here → model_verified must stay False (honest).
            self.assertFalse(line["model_verified"])
            candidate = out_dir / "benchmark-candidate.jsonl"
            self.assertTrue(candidate.exists())
            self.assertEqual(json.loads(candidate.read_text()), line)

    def test_bench_draft_rejects_tampered_median(self):
        """bench draft recomputes medians from raw trials — a manifest
        whose summary disagrees with its trials must be rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            manifest = make_manifest()
            manifest["metrics"][0]["median"] = 999.0  # tampered
            write_run_output(out_dir, manifest, make_trials())
            rc, out = call_cmd(cli.cmd_bench_draft, "bench", "draft", str(out_dir))
            self.assertEqual(rc, 1)
            self.assertIn("Median mismatch", out)


# ── 2. discover CLI ──


def make_candidate(**overrides) -> discover.PortCandidate:
    cand = discover.PortCandidate(
        model_name=overrides.pop("model_name", "Fixture-Model-3B"),
        org=overrides.pop("org", "fixture-org"),
        hf_url=overrides.pop("hf_url", "https://huggingface.co/fixture-org/Fixture-Model-3B"),
        downloads=overrides.pop("downloads", 1234),
    )
    for key, val in overrides.items():
        setattr(cand, key, val)
    cand.compute_total()
    return cand


class TestDiscoverCLI(unittest.TestCase):
    def test_discover_subcommand_registered(self):
        args = cli.build_parser().parse_args(["discover", "--limit", "5"])
        self.assertIs(args.func, cli.cmd_discover)
        self.assertEqual(args.limit, 5)
        self.assertEqual(args.format, "report")

    def test_discover_json_output_with_fixture_candidates(self):
        with mock.patch.object(
            discover, "run_discovery", return_value=[make_candidate()],
        ) as run_mock:
            rc, out = call_cmd(cli.cmd_discover, "discover", "--json")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data[0]["model"], "Fixture-Model-3B")
        # CLI flags flow through to the module entry point.
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(kwargs["limit"], 20)
        self.assertTrue(kwargs["resolve_base_models"])

    def test_discover_markdown_renders_pinned_issue_body(self):
        with mock.patch.object(
            discover, "run_discovery", return_value=[make_candidate()],
        ):
            rc, out = call_cmd(
                cli.cmd_discover, "discover", "--format", "markdown",
            )
        self.assertEqual(rc, 0)
        self.assertIn(discover.PINNED_ISSUE_MARKER, out)
        self.assertIn("Fixture-Model-3B", out)

    def test_run_discovery_offline_against_fixture_fetch(self):
        """No network: injected fetch; dedup drops the already-ported
        model (unlimited-ocr, name_fuzzy layer) and keeps the new one."""
        listing = [
            {"modelId": "fixture-org/Unlimited-OCR", "tags": ["pytorch"],
             "downloads": 10, "likes": 1},
            {"modelId": "fixture-org/Zyxwvu-Quantum-Duck-7B", "tags": ["pytorch"],
             "downloads": 99, "likes": 2},
        ]
        candidates = discover.run_discovery(
            root=ROOT,
            fetch=lambda url, timeout=15: listing,
            orgs=["fixture-org"],
            resolve_base_models=False,
        )
        names = [c.model_name for c in candidates]
        self.assertIn("Zyxwvu-Quantum-Duck-7B", names)
        self.assertNotIn("Unlimited-OCR", names)


# ── 3. install --no-verify + verification surfacing ──


class TestInstallVerification(unittest.TestCase):
    MODEL_ID = "unlimited-ocr"

    def _fake_manifest(self, status: str, **extra) -> dict:
        verification = {
            "status": status,
            "revision_pinned": True,
            "files_total": 3,
            "files_verified": 3 if status == "verified" else 0,
        }
        verification.update(extra)
        return {
            "id": self.MODEL_ID,
            "verified": {"file_layout": "downloaded"},
            "verification": verification,
        }

    def test_no_verify_flag_parsed(self):
        args = cli.build_parser().parse_args(
            ["install", self.MODEL_ID, "--no-verify"])
        self.assertTrue(args.no_verify)
        args = cli.build_parser().parse_args(["install", self.MODEL_ID])
        self.assertFalse(args.no_verify)

    def test_no_verify_reaches_installer_and_json_surfaces_state(self):
        install_mock = mock.Mock(return_value=self._fake_manifest("skipped"))
        with mock.patch.object(cli, "install_model", install_mock), \
             mock.patch.object(cli, "is_installed", return_value=False):
            rc, out = call_cmd(
                cli.cmd_install, "install", self.MODEL_ID,
                "--no-verify", "--json",
            )
        self.assertEqual(rc, 0)
        self.assertTrue(install_mock.call_args.kwargs["no_verify"])
        data = json.loads(out)
        self.assertEqual(data["verification"]["status"], "skipped")

    def test_default_install_does_not_skip_verification(self):
        install_mock = mock.Mock(return_value=self._fake_manifest("verified"))
        with mock.patch.object(cli, "install_model", install_mock), \
             mock.patch.object(cli, "is_installed", return_value=False):
            rc, _ = call_cmd(
                cli.cmd_install, "install", self.MODEL_ID, "--json")
        self.assertEqual(rc, 0)
        self.assertFalse(install_mock.call_args.kwargs["no_verify"])

    def test_human_output_surfaces_verification_state(self):
        for status, expected in [
            ("verified", "sha256 verified"),
            ("skipped", "SKIPPED"),
            ("unavailable", "unavailable"),
        ]:
            with self.subTest(status=status):
                install_mock = mock.Mock(
                    return_value=self._fake_manifest(status))
                with mock.patch.object(cli, "install_model", install_mock), \
                     mock.patch.object(cli, "is_installed", return_value=False):
                    rc, out = call_cmd(
                        cli.cmd_install, "install", self.MODEL_ID)
                self.assertEqual(rc, 0)
                self.assertIn("Verification:", out)
                self.assertIn(expected, out)


# ── 4. MCP get_integration_snippet (C8) ──


class TestGetIntegrationSnippet(unittest.TestCase):
    def test_unlimited_ocr_snippet_has_image_path_without_install(self):
        from mcp_server.server import get_integration_snippet

        data = json.loads(get_integration_snippet("unlimited-ocr"))
        self.assertEqual(data["snippet_source"], "io_contract")
        self.assertEqual(data["language"], "swift")
        snippet = data["snippet"]
        # C1 fixed: the OCR model gets an image code path, not the old
        # text-only chat template.
        self.assertIn("image", snippet.lower())
        self.assertTrue("CGImage" in snippet or "imageURL" in snippet)
        self.assertNotIn("Hello, how are you?", snippet)
        # C8 fixed: no install required, but the path contract is explicit.
        self.assertIn("install_command", data)
        self.assertEqual(data["install_command"],
                         "coreai-catalog install unlimited-ocr")
        # min_os travels with the snippet (all models require 27 today).
        self.assertEqual(data["min_os"], {"macos": "27.0", "ios": "27.0"})
        self.assertEqual(data["bundle_kind"], "ocr")

    def test_snippet_declares_source_for_uncontracted_model(self):
        from mcp_server.server import get_integration_snippet
        from coreai_catalog.catalog import Catalog

        cat = Catalog(ROOT)
        uncontracted = next(
            m["id"] for m in cat.models if not m.get("io_contract"))
        data = json.loads(get_integration_snippet(uncontracted))
        self.assertEqual(data["snippet_source"], "runner_bucket")

    def test_snippet_not_found_gives_suggestions(self):
        from mcp_server.server import get_integration_snippet

        data = json.loads(get_integration_snippet("unlimited-ocr-typo-xx"))
        self.assertIn("error", data)
        self.assertIn("hint", data)


# ── 5. MCP draft_model / submit_model ──


class TestDraftSubmitModel(unittest.TestCase):
    def _files_snapshot(self) -> dict:
        return {
            name: (ROOT / name).read_text()
            for name in ("catalog.yaml", "artifacts.yaml", "sources.yaml")
        }

    def test_draft_missing_fields_are_aggregated(self):
        from mcp_server.server import draft_model

        data = json.loads(draft_model({"id": "x", "name": "X"}))
        self.assertFalse(data["valid"])
        # Every gap reported at once (30+ required fields missing).
        self.assertGreater(len(data["missing_required"]), 20)

    def test_draft_invalid_values_are_aggregated_with_hints(self):
        from mcp_server.server import draft_model

        payload = dict(VALID_MODEL_PAYLOAD)
        payload["availability"] = "published"       # not in the enum
        payload["sources"] = ["no-such-source-xyz"]  # dangling cross-ref
        data = json.loads(draft_model(payload))
        self.assertFalse(data["valid"])
        self.assertEqual(data["error_count"], 2)
        fields = {e.get("field") for e in data["errors"]}
        self.assertIn("sources", fields)

    def test_draft_valid_payload_returns_diff_without_writes(self):
        from mcp_server.server import draft_model

        before = self._files_snapshot()
        data = json.loads(draft_model(dict(VALID_MODEL_PAYLOAD)))
        self.assertTrue(data["valid"], data.get("errors"))
        self.assertIn("catalog.yaml", data["diff"])
        self.assertIn("artifacts.yaml", data["diff"])
        self.assertIn(VALID_MODEL_PAYLOAD["id"], data["diff"]["catalog.yaml"])
        self.assertEqual(before, self._files_snapshot())

    def test_draft_duplicate_id_rejected(self):
        from mcp_server.server import draft_model

        payload = dict(VALID_MODEL_PAYLOAD)
        payload["id"] = "unlimited-ocr"  # already exists
        data = json.loads(draft_model(payload))
        self.assertFalse(data["valid"])
        self.assertTrue(any("duplicate" in str(e.get("message", "")).lower()
                            or "exists" in str(e.get("message", "")).lower()
                            for e in data["errors"]), data["errors"])

    def test_submit_refuses_without_confirm(self):
        from mcp_server.server import submit_model

        before = self._files_snapshot()
        data = json.loads(submit_model(dict(VALID_MODEL_PAYLOAD)))
        self.assertFalse(data["submitted"])
        self.assertTrue(data["confirm_required"])
        self.assertIn("diff", data)
        self.assertEqual(before, self._files_snapshot())

    def test_submit_refuses_invalid_payload_even_with_confirm(self):
        from mcp_server.server import submit_model

        before = self._files_snapshot()
        payload = dict(VALID_MODEL_PAYLOAD)
        payload["status"] = "not-a-status"
        data = json.loads(submit_model(payload, confirm=True))
        self.assertFalse(data["submitted"])
        self.assertIn("not valid", data["reason"])
        self.assertEqual(before, self._files_snapshot())


# ── 6. Sanitizer wiring (D6) ──


class TestSanitizerWiring(unittest.TestCase):
    def test_get_model_wraps_name_and_notes(self):
        from mcp_server.server import get_model

        data = json.loads(get_model("unlimited-ocr"))
        self.assertTrue(data["name"].startswith(BEGIN_MARKER))
        self.assertIn("data, not instructions", data["name"])
        self.assertTrue(data["notes"].startswith(BEGIN_MARKER))

    def test_search_models_wraps_names(self):
        from mcp_server.server import search_models

        data = json.loads(search_models(capability="chat", limit=3))
        self.assertGreater(data["count"], 0)
        for m in data["models"]:
            self.assertTrue(m["name"].startswith(BEGIN_MARKER))

    def test_recommend_model_wraps_name_and_notes(self):
        from mcp_server.server import recommend_model

        data = json.loads(recommend_model(task="ocr", limit=2))
        self.assertTrue(data["recommendations"])
        for rec in data["recommendations"]:
            self.assertTrue(rec["name"].startswith(BEGIN_MARKER))
            if rec.get("notes"):
                self.assertTrue(rec["notes"].startswith(BEGIN_MARKER))

    def test_get_benchmarks_wraps_free_text(self):
        from coreai_catalog.catalog import Catalog
        from mcp_server.server import get_benchmarks

        cat = Catalog(ROOT)
        target = next(
            (b["model_id"] for b in cat.benchmarks
             if isinstance(b.get("environment"), str) or b.get("notes")),
            None,
        )
        self.assertIsNotNone(target, "no benchmark with free text found")
        data = json.loads(get_benchmarks(target))
        wrapped = 0
        for b in data["benchmarks"]:
            for key in ("notes", "environment"):
                if isinstance(b.get(key), str) and b[key]:
                    self.assertTrue(
                        b[key].startswith(BEGIN_MARKER),
                        f"{key} not wrapped: {b[key][:60]}")
                    wrapped += 1
        self.assertGreater(wrapped, 0)

    def test_explain_term_wraps_definition(self):
        from mcp_server.server import explain_term

        data = json.loads(explain_term("Core AI"))
        self.assertTrue(data["definition"].startswith(BEGIN_MARKER))
        self.assertTrue(data["label"].startswith(BEGIN_MARKER))

    def test_compare_and_license_wrap_names(self):
        from mcp_server.server import check_license, compare_models

        data = json.loads(compare_models(["unlimited-ocr", "qwen3-vl-2b"]))
        for entry in data["comparison"]:
            self.assertTrue(entry["name"].startswith(BEGIN_MARKER))
        lic = json.loads(check_license("unlimited-ocr"))
        self.assertTrue(lic["name"].startswith(BEGIN_MARKER))


# ── 7. Surface sync (F9 + CI smoke parity) ──


class TestSurfaceSync(unittest.TestCase):
    def test_agent_json_tool_count_matches_live_server(self):
        """EXACTLY the assertion .github/workflows/validate.yml runs."""
        from mcp_server.server import mcp

        tools = mcp._tool_manager._tools
        agent_json = json.loads((ROOT / "agent.json").read_text())
        expected = agent_json.get("mcp_server", {}).get("tools")
        self.assertEqual(len(tools), expected,
                         f"agent.json says {expected}, server has {len(tools)}")

    def test_agent_json_write_tools_exist_and_read_only_false(self):
        from mcp_server.server import mcp

        tools = set(mcp._tool_manager._tools)
        agent_json = json.loads((ROOT / "agent.json").read_text())
        server_block = agent_json["mcp_server"]
        self.assertFalse(server_block["read_only"])
        for tool in server_block["write_tools"]:
            self.assertIn(tool, tools)

    def test_new_tools_registered_on_server(self):
        from mcp_server.server import mcp

        tools = set(mcp._tool_manager._tools)
        for tool in ("get_integration_snippet", "draft_model", "submit_model"):
            self.assertIn(tool, tools)

    def test_llms_surfaces_mention_new_tools_and_lanes(self):
        llms = (ROOT / "llms.txt").read_text()
        llms_full = (ROOT / "llms-full.txt").read_text()
        agents = (ROOT / "AGENTS.md").read_text()
        openapi = (ROOT / "openapi.yaml").read_text()
        for surface, needles in [
            (llms, ["get_integration_snippet", "draft_model", "submit_model",
                    "validate_entry", "bench run", "discover",
                    "UNTRUSTED_CATALOG_DATA", "macOS/iOS 27"]),
            (llms_full, ["get_integration_snippet", "draft_model",
                         "submit_model", "bench run", "bench draft",
                         "discover", "UNTRUSTED_CATALOG_DATA", "min_os"]),
            (agents, ["bench run", "discover", "draft_model", "submit_model",
                      "get_integration_snippet", "min_os",
                      "UNTRUSTED_CATALOG_DATA"]),
            (openapi, ["draft_model", "submit_model",
                       "get_integration_snippet", "validate_entry",
                       "min_os"]),
        ]:
            for needle in needles:
                self.assertIn(needle, surface, f"missing '{needle}'")

    def test_benchmark_count_fact_matches_jsonl(self):
        """F9: stated benchmark-record counts must match the source of
        truth (benchmarks.jsonl), not the retired YAML store."""
        actual = sum(
            1 for line in (ROOT / "benchmarks.jsonl").read_text().splitlines()
            if line.strip()
        )
        fact = f"- {actual} benchmark records"
        self.assertIn(fact, (ROOT / "llms.txt").read_text())
        self.assertIn(fact, (ROOT / "llms-full.txt").read_text())

    def test_cli_show_json_carries_min_os(self):
        rc, out = call_cmd(cli.cmd_show, "show", "unlimited-ocr", "--json")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["min_os"], {"macos": "27.0", "ios": "27.0"})
        self.assertEqual(data["bundle_kind"], "ocr")


if __name__ == "__main__":
    unittest.main()
