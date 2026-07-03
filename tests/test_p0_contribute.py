#!/usr/bin/env python3
"""
P0 tests — WP3 "contribute-tooling" (findings A6, A9, F3, F9, F10).

Covers:
- coreai_catalog/contribute.py shared validation core: aggregated errors,
  enum fix hints, cross-references, duplicate ids, near-miss suggestions
- scripts/validate.py: aggregation across entity categories, --json report,
  GitHub annotations, sources.yaml wiring, green on current repo data
- CLI `coreai-catalog contribute model --dry-run` emits schema-valid YAML
- CLI `coreai-catalog contribute benchmark` drafts a schema-valid JSONL
  line and explains the curator lane
- MCP validate_entry tool + dynamic instruction count + near-miss errors

Run: python -m pytest tests/test_p0_contribute.py -v
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

import validate  # noqa: E402  (scripts/validate.py)
from coreai_catalog import contribute  # noqa: E402
from coreai_catalog.catalog import Catalog  # noqa: E402
from coreai_catalog.cli import build_parser  # noqa: E402


def _valid_model_flags(model_id: str = "test-model-p0") -> list[str]:
    return [
        "contribute", "model", "--dry-run", "--non-interactive",
        "--id", model_id, "--name", "Test Model P0", "--family", "TestFam",
        "--source-group", "external",
        "--source-path", f"https://huggingface.co/tester/{model_id}",
        "--capabilities", "chat,text-generation",
        "--input", "text", "--output", "text",
        "--artifact-format", "aimodel", "--availability", "available",
        "--parameters", "1B", "--precision", "int8",
        "--quantization", "int8lin", "--artifact-size", "900MB",
        "--runtime-name", "apple-core-ai", "--runner", "CoreAIRunner",
        "--stock-runtime", "true", "--custom-kernel", "false",
        "--patch-required", "false", "--tokenizer-required", "true",
        "--processor-required", "false", "--aot-required", "false",
        "--iphone", "true", "--ipad", "unknown", "--mac", "true",
        "--mac-only", "false",
        "--license-name", "Apache-2.0", "--commercial-use", "likely",
        "--status", "confirmed", "--maturity", "active",
        "--confidence", "medium",
        "--sources", "coreai-model-zoo",
        "--last-verified", "2026-07-03",
        "--hf-owner", "tester", "--hf-repo", model_id,
    ]


def _run_cli(argv: list[str]) -> tuple[int, str]:
    parser = build_parser()
    args = parser.parse_args(argv)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = args.func(args)
    return code, buf.getvalue()


class TestValidationCoreAggregation(unittest.TestCase):
    """A9/F3: validation must aggregate ALL errors, never fail-fast."""

    def test_multiple_errors_reported_at_once(self):
        payload = {
            "id": "broken-model",
            "name": "Broken",
            "family": "X",
            "source_group": "offical",          # bad enum (typo)
            "source_path": "http://insecure",   # bad pattern
            "artifact_ref": "no-such-artifact",  # dangling cross-ref
            "capabilities": ["chat"],
            "modalities": {"input": ["text"], "output": ["text"]},
            "artifact": {"format": "aimodel", "availability": "availble"},  # bad enum
            "size": {"parameters": "1B", "precision": "int8",
                     "quantization": "int8lin", "artifact_size": "1MB"},
            "runtime": {"runtime_name": "apple-core-ai", "runner": "CoreAIRunner",
                        "stock_runtime": True, "custom_kernel": False,
                        "patch_required": False, "tokenizer_required": True,
                        "processor_required": False, "aot_required": False},
            "device_support": {"iphone": True, "ipad": True, "mac": True,
                               "mac_only": False},
            "license": {"name": "MIT", "commercial_use": "likely"},
            "status": "confirmed", "maturity": "active", "confidence": "high",
            "sources": ["not-a-real-source"],   # dangling cross-ref
            "last_verified": "2026-07-03",
            "notes": None,
        }
        errors = contribute.validate_entry("model", payload, root=_ROOT)
        self.assertGreaterEqual(len(errors), 5)
        fields = {e["field"] for e in errors}
        self.assertIn("source_group", fields)
        self.assertIn("artifact.availability", fields)
        self.assertIn("source_path", fields)
        self.assertIn("artifact_ref", fields)
        self.assertIn("sources", fields)
        for err in errors:
            self.assertEqual(err["file"], "catalog.yaml")
            self.assertEqual(err["entity_id"], "broken-model")
            self.assertTrue(err["field"])
            self.assertTrue(err["message"])

    def test_bad_enum_gets_nearest_value_hint(self):
        errors = contribute.validate_entry(
            "model", {"id": "x", "source_group": "offical"}, root=_ROOT,
        )
        enum_errors = [e for e in errors if e["field"] == "source_group"]
        self.assertEqual(len(enum_errors), 1)
        self.assertIn("did you mean 'official'", enum_errors[0]["hint"])
        self.assertIn("valid values:", enum_errors[0]["hint"])

    def test_unknown_property_hint_suggests_nearest_field(self):
        errors = contribute.validate_entry(
            "benchmark",
            {"id": "b", "model_id": "qwen3-5-0-8b", "metric": "decode_throughput",
             "value": 10, "unit": "tokens_per_second", "device_class": "M4 Max",
             "os_major": "26", "compute_unit": "GPU",
             "extraction_method": "upstream_readme_manual",
             "confidence": "medium", "observed_date": "2026-07-03",
             "source": "coreai-model-zoo-readme",
             "observedd_date": "2026-07-03"},  # typo'd extra property
            root=_ROOT,
        )
        add_prop = [e for e in errors if "observedd_date" in e["message"]]
        self.assertEqual(len(add_prop), 1)
        self.assertIn("observed_date", add_prop[0]["hint"])

    def test_duplicate_id_flagged_for_candidates(self):
        cat = Catalog(_ROOT)
        existing_id = cat.models[0]["id"]
        errors = contribute.validate_entry(
            "model", {"id": existing_id}, root=_ROOT,
        )
        dup = [e for e in errors if "already exists" in e["message"]]
        self.assertEqual(len(dup), 1)

    def test_missing_required_fields_all_listed(self):
        errors = contribute.validate_entry("model", {"id": "x"}, root=_ROOT)
        required_errors = [e for e in errors if "required property" in e["message"]]
        # model schema has 19 required fields; all but id must be reported
        self.assertGreaterEqual(len(required_errors), 15)

    def test_unknown_kind_raises_with_valid_kinds(self):
        with self.assertRaises(ValueError) as ctx:
            contribute.validate_entry("nonsense", {}, root=_ROOT)
        self.assertIn("model", str(ctx.exception))

    def test_suggest_near_miss(self):
        self.assertEqual(
            contribute.suggest("offical", ["official", "zoo", "external"])[0],
            "official",
        )
        self.assertEqual(contribute.suggest("", ["a"]), [])


class TestValidateScript(unittest.TestCase):
    """scripts/validate.py — aggregated, --json, --github, sources wired."""

    def test_current_repo_is_green(self):
        result = subprocess.run(
            [sys.executable, "scripts/validate.py"],
            cwd=str(_ROOT), capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK:", result.stdout)
        self.assertIn("sources", result.stdout)

    def test_json_report_shape(self):
        result = subprocess.run(
            [sys.executable, "scripts/validate.py", "--json"],
            cwd=str(_ROOT), capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["errors"], [])
        cat = Catalog(_ROOT)
        self.assertEqual(report["counts"]["models"], len(cat.models))
        self.assertGreater(report["counts"]["sources"], 0)
        self.assertGreater(report["counts"]["benchmarks"], 0)

    def test_collect_errors_aggregates_across_categories(self):
        """Multiple coexisting errors in DIFFERENT entity categories are all
        reported in one run (the old validator exited at the first one)."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copytree(_ROOT / "schema", root / "schema")
            (root / "catalog.yaml").write_text(yaml.dump({
                "models": [{"id": "m1", "source_group": "offical"}],
            }))
            (root / "artifacts.yaml").write_text(yaml.dump({
                "metadata": {"count": 1},
                "artifacts": [{"id": "a1", "group": "external"}],  # no gh/hf
            }))
            (root / "sources.yaml").write_text(yaml.dump({
                "sources": [
                    {"id": "s1", "title": "t", "type": "github_repository",
                     "url": "https://github.com/x/y", "owner": "x",
                     "trust": "community_primary", "volatility": "low",
                     "last_checked": "2026-07-03", "notes": None},
                    {"id": "s1", "title": "t", "type": "github_repository",
                     "url": "https://github.com/x/y", "owner": "x",
                     "trust": "community_primary", "volatility": "low",
                     "last_checked": "2026-07-03", "notes": None},
                ],
            }))
            (root / "upstreams.yaml").write_text("{}\n")
            (root / "terms.yaml").write_text("{}\n")
            (root / "benchmarks.jsonl").write_text(
                '{"id": "b1", "model_id": "missing-model", "metric": "decode_throughput", '
                '"value": 1, "unit": "tokens_per_second", "device_class": "M4", '
                '"os_major": "26", "compute_unit": "GPU", '
                '"extraction_method": "upstream_readme_manual", "confidence": "low", '
                '"observed_date": "2026-07-01", "source": "s1"}\n'
                "this is not json\n"
            )
            errors, counts = validate.collect_errors(root)
            files = {e["file"] for e in errors}
            # Errors from at least 4 different entity categories, one pass:
            self.assertIn("catalog.yaml", files)      # bad enum + missing fields
            self.assertIn("artifacts.yaml", files)    # anyOf(github, huggingface)
            self.assertIn("sources.yaml", files)      # duplicate id
            self.assertIn("benchmarks.jsonl", files)  # bad JSON + dangling model_id
            self.assertGreaterEqual(len(errors), 6)
            dup = [e for e in errors if e["message"] == "duplicate id"]
            self.assertEqual(len(dup), 1)
            dangling = [e for e in errors if "missing-model" in e["message"]]
            self.assertEqual(len(dangling), 1)
            self.assertIsNotNone(dangling[0]["hint"])
            self.assertEqual(counts["models"], 1)

    def test_find_entity_line_yaml_and_jsonl(self):
        cat = Catalog(_ROOT)
        model_id = cat.models[0]["id"]
        line = validate.find_entity_line(
            _ROOT, {"file": "catalog.yaml", "entity_id": model_id},
        )
        self.assertIsNotNone(line)
        lines = (_ROOT / "catalog.yaml").read_text().splitlines()
        self.assertIn(f"id: {model_id}", lines[line - 1])
        bench_id = cat.benchmarks[0]["id"]
        line = validate.find_entity_line(
            _ROOT, {"file": "benchmarks.jsonl", "entity_id": bench_id},
        )
        self.assertIsNotNone(line)

    def test_github_annotation_format(self):
        err = contribute.make_error(
            "catalog.yaml", "qwen3-5-0-8b", "source_group", "bad value", "try official",
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            validate.emit_github_annotations([err], _ROOT)
        output = buf.getvalue()
        self.assertTrue(output.startswith("::error file=catalog.yaml,line="))
        self.assertIn("qwen3-5-0-8b: source_group: bad value", output)
        self.assertIn("hint: try official", output)


class TestContributeModelCLI(unittest.TestCase):
    """A6: `coreai-catalog contribute model` — draft → validate → dry-run."""

    def test_dry_run_emits_schema_valid_yaml(self):
        code, output = _run_cli(_valid_model_flags())
        self.assertEqual(code, 0, output)
        sections = output.split("# ──")
        self.assertGreaterEqual(len(sections), 3)
        model_block = "\n".join(sections[1].splitlines()[1:])
        artifact_block = "\n".join(sections[2].splitlines()[1:])
        model_entry = yaml.safe_load(model_block)[0]
        artifact_entry = yaml.safe_load(artifact_block)[0]

        model_schema = json.loads((_ROOT / "schema" / "model.schema.json").read_text())
        artifact_schema = json.loads((_ROOT / "schema" / "artifact.schema.json").read_text())
        self.assertEqual(
            list(Draft202012Validator(model_schema).iter_errors(model_entry)), [],
        )
        self.assertEqual(
            list(Draft202012Validator(artifact_schema).iter_errors(artifact_entry)), [],
        )
        self.assertEqual(model_entry["id"], "test-model-p0")
        self.assertEqual(model_entry["artifact_ref"], artifact_entry["id"])
        self.assertEqual(
            artifact_entry["huggingface"]["url"],
            "https://huggingface.co/tester/test-model-p0",
        )

    def test_dry_run_writes_nothing(self):
        before_cat = (_ROOT / "catalog.yaml").read_text()
        before_art = (_ROOT / "artifacts.yaml").read_text()
        code, _ = _run_cli(_valid_model_flags())
        self.assertEqual(code, 0)
        self.assertEqual((_ROOT / "catalog.yaml").read_text(), before_cat)
        self.assertEqual((_ROOT / "artifacts.yaml").read_text(), before_art)

    def test_missing_fields_all_reported_at_once(self):
        code, output = _run_cli(["contribute", "model", "--non-interactive"])
        self.assertEqual(code, 1)
        self.assertIn("--id", output)
        self.assertIn("--source-group", output)
        self.assertIn("--commercial-use", output)
        self.assertIn("--hf-owner", output)

    def test_invalid_enum_rejected_with_hint(self):
        flags = _valid_model_flags()
        idx = flags.index("--source-group")
        flags[idx + 1] = "offical"
        code, output = _run_cli(flags)
        self.assertEqual(code, 1)
        self.assertIn("did you mean 'official'", output)

    def test_duplicate_model_id_rejected(self):
        cat = Catalog(_ROOT)
        code, output = _run_cli(_valid_model_flags(model_id=cat.models[0]["id"]))
        self.assertEqual(code, 1)
        self.assertIn("already exists", output)

    def test_fabric_source_group_maps_artifact_group_external(self):
        flags = _valid_model_flags()
        idx = flags.index("--source-group")
        flags[idx + 1] = "fabric"
        code, output = _run_cli(flags)
        self.assertEqual(code, 0, output)
        artifact_block = "\n".join(output.split("# ──")[2].splitlines()[1:])
        artifact_entry = yaml.safe_load(artifact_block)[0]
        self.assertEqual(artifact_entry["group"], "external")


class TestContributeBenchmarkCLI(unittest.TestCase):
    """B8-adjacent: draft a schema-valid benchmark line + curator-lane docs."""

    BENCH_FLAGS = [
        "contribute", "benchmark", "--non-interactive",
        "--model-id", "qwen3-5-0-8b", "--metric", "decode_throughput",
        "--value", "42.5", "--unit", "tokens_per_second",
        "--device-class", "M4 Max", "--os-major", "26",
        "--compute-unit", "GPU",
        "--extraction-method", "upstream_readme_manual",
        "--confidence", "medium", "--observed-date", "2026-07-03",
        "--source", "coreai-model-zoo-readme", "--higher-is-better",
    ]

    def test_draft_is_schema_valid_and_explains_curator_lane(self):
        code, output = _run_cli(self.BENCH_FLAGS)
        self.assertEqual(code, 0, output)
        json_lines = [l for l in output.splitlines() if l.startswith("{")]
        self.assertEqual(len(json_lines), 1)
        entry = json.loads(json_lines[0])
        schema = json.loads((_ROOT / "schema" / "benchmark.schema.json").read_text())
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(entry)), [])
        self.assertEqual(entry["model_id"], "qwen3-5-0-8b")
        self.assertEqual(entry["value"], 42.5)
        self.assertTrue(entry["higher_is_better"])
        # Curator lane explained, and it does not push
        self.assertIn("curator", output.lower())
        self.assertIn("benchmark-curator-review", output)
        self.assertIn("ONE added line", output)
        self.assertIn("does NOT push", output)

    def test_draft_does_not_write_by_default(self):
        before = (_ROOT / "benchmarks.jsonl").read_text()
        code, _ = _run_cli(self.BENCH_FLAGS)
        self.assertEqual(code, 0)
        self.assertEqual((_ROOT / "benchmarks.jsonl").read_text(), before)

    def test_dangling_model_id_rejected_with_near_miss(self):
        flags = list(self.BENCH_FLAGS)
        idx = flags.index("--model-id")
        flags[idx + 1] = "qwen3-5-0-8b-typo"
        code, output = _run_cli(flags)
        self.assertEqual(code, 1)
        self.assertIn("did you mean 'qwen3-5-0-8b'", output)


class TestContributeHelpers(unittest.TestCase):
    def test_bump_artifact_count(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "artifacts.yaml").write_text(
                "metadata:\n  name: x\n  count: 80\nartifacts:\n- id: a\n  count: 5\n"
            )
            old, new = contribute.bump_artifact_count(root)
            self.assertEqual((old, new), (80, 81))
            text = (root / "artifacts.yaml").read_text()
            self.assertIn("  count: 81\n", text)
            self.assertIn("  count: 5\n", text)  # entry-level key untouched

    def test_append_yaml_entry_round_trips(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sources.yaml"
            path.write_text("sources:\n- id: existing\n  title: t\n")
            contribute.append_yaml_entry(path, {"id": "new-one", "title": "n"})
            data = yaml.safe_load(path.read_text())
            self.assertEqual([s["id"] for s in data["sources"]], ["existing", "new-one"])

    def test_derive_benchmark_id(self):
        bid = contribute.derive_benchmark_id({
            "model_id": "qwen3-5-0-8b", "device_class": "M4 Max",
            "compute_unit": "GPU", "metric": "decode_throughput",
        })
        self.assertEqual(bid, "qwen3-5-0-8b-m4max-gpu-decode-throughput")

    def test_schema_enum_rendered_from_schema(self):
        schema = contribute.load_schema("model", _ROOT)
        self.assertIn("fabric", contribute.schema_enum(schema, "source_group"))
        self.assertEqual(
            contribute.schema_enum(schema, "license.commercial_use"),
            ["likely", "check_license"],
        )
        self.assertEqual(contribute.schema_enum(schema, "no.such.field"), [])


class TestMCPServer(unittest.TestCase):
    """F9/F10 + validate_entry MCP tool."""

    @classmethod
    def setUpClass(cls):
        from mcp_server import server
        cls.server = server

    def test_instructions_contain_true_model_count(self):
        cat = Catalog(_ROOT)
        self.assertIn(f"{len(cat.models)} Apple Core AI models",
                      self.server.INSTRUCTIONS)
        self.assertNotIn("79 Apple Core AI models", self.server.INSTRUCTIONS)

    def test_get_model_not_found_has_near_miss_and_hint(self):
        result = json.loads(self.server.get_model("qwen3-vl-2b-typo"))
        self.assertIn("error", result)
        self.assertIn("qwen3-vl-2b", result.get("did_you_mean", []))
        self.assertIn("search_models", result["hint"])

    def test_check_license_and_artifact_not_found_hints(self):
        for tool in (self.server.check_license, self.server.get_artifact,
                     self.server.get_benchmarks):
            result = json.loads(tool("unlimited-ocr-typo"))
            self.assertIn("error", result)
            self.assertIn("hint", result)

    def test_compare_models_unknown_id_gets_suggestion(self):
        result = json.loads(
            self.server.compare_models(["qwen3-5-0-8b", "qwen3-5-2b-typo"])
        )
        bad = result["comparison"][1]
        self.assertEqual(bad["error"], "not found")
        self.assertIn("qwen3-5-2b", bad.get("did_you_mean", []))

    def test_validate_entry_bad_enum_with_hint(self):
        result = json.loads(
            self.server.validate_entry("model", {"id": "x", "source_group": "offical"})
        )
        self.assertFalse(result["valid"])
        self.assertGreater(result["error_count"], 1)  # aggregated, not one-at-a-time
        enum_errors = [e for e in result["errors"] if e["field"] == "source_group"]
        self.assertEqual(len(enum_errors), 1)
        self.assertIn("did you mean 'official'", enum_errors[0]["hint"])

    def test_validate_entry_valid_benchmark(self):
        result = json.loads(self.server.validate_entry("benchmark", {
            "id": "p0-test-bench", "model_id": "qwen3-5-0-8b",
            "metric": "decode_throughput", "value": 10.0,
            "unit": "tokens_per_second", "device_class": "M4 Max",
            "os_major": "26", "compute_unit": "GPU",
            "extraction_method": "upstream_readme_manual",
            "confidence": "medium", "observed_date": "2026-07-03",
            "source": "coreai-model-zoo-readme",
        }))
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["target_file"], "benchmarks.jsonl")

    def test_validate_entry_unknown_kind(self):
        result = json.loads(self.server.validate_entry("modle", {}))
        self.assertIn("error", result)
        self.assertIn("model", result["valid_kinds"])
        self.assertIn("model", result.get("did_you_mean", []))


if __name__ == "__main__":
    unittest.main()
