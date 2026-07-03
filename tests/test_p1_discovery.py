#!/usr/bin/env python3
"""
P1 tests — WP-E "discovery-governance" (findings E4-partial, F4, F5, F6).

Covers:
- coreai_catalog/discover.py dedup (the F4 fix): the authored upstream_repo
  layer, HF base_model lineage layer, and normalized-name fuzzy fallback —
  including the org/name-vs-bare-name case the old scripts/discover.py
  could never match
- run_discovery with an injected fetch (fixtures only, no network)
- pinned-issue markdown renderer + JSON renderer
- model-request issue FORM: template labels stay in sync with the parse
  contract (FORM_FIELDS), every dropdown equals its schema enum
  (regeneration guard), and a full form-parse → build → validate round-trip
- scripts/source_monitor.py candidate stubs + pinned-issue report marker

Run: python -m pytest tests/test_p1_discovery.py -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

import source_monitor  # noqa: E402  (scripts/source_monitor.py)
from coreai_catalog import contribute, discover  # noqa: E402


# ── Fixtures ──

FIXTURE_CATALOG = {
    "models": [
        {
            "id": "qwen3-5-0-8b",
            "name": "Qwen3.5-0.8B",
            # Authored upstream lineage (org/name of the ORIGINAL repo)
            "upstream_repo": "Qwen/Qwen3.5-0.8B",
        },
        {
            # No upstream_repo — dedup must fall back to fuzzy name
            "id": "gemma-3-4b-it",
            "name": "Gemma 3 4B IT",
        },
        {
            # Converted-name differs entirely from the upstream name —
            # only the HF base_model lineage layer can catch this one
            "id": "unlimited-ocr",
            "name": "Unlimited OCR",
        },
        {
            "id": "qwen3-vl-2b",
            "name": "Qwen3-VL 2B",
        },
    ]
}

FIXTURE_ARTIFACTS = {
    "artifacts": [
        {
            "id": "qwen3-5-0-8b",
            "huggingface": {"owner": "mlboydaisuke", "repo": "qwen3.5-0.8B-CoreAI"},
        },
        {
            "id": "gemma-3-4b-it",
            "huggingface": {
                "owner": "mlboydaisuke",
                "repo": "gemma-3-4B-it-CoreAI-official",
            },
        },
        {
            "id": "unlimited-ocr",
            "huggingface": {"owner": "mlboydaisuke", "repo": "Unlimited-OCR-CoreAI"},
        },
    ]
}

# base_model lineage as the HF API would report it for the artifact repos
FIXTURE_BASE_MODELS = {"nanonets/nanonets-ocr-s"}


def build_index(**overrides) -> discover.CatalogIndex:
    kwargs = dict(
        catalog=FIXTURE_CATALOG,
        artifacts=FIXTURE_ARTIFACTS,
        base_models=FIXTURE_BASE_MODELS,
    )
    kwargs.update(overrides)
    return discover.build_catalog_index(**kwargs)


class TestDedupF4(unittest.TestCase):
    """F4: dedup must match candidates the old membership test never could."""

    def test_old_org_name_vs_bare_name_membership_never_matched(self):
        # The exact broken comparison from the old scripts/discover.py:
        # candidate 'org/name' key tested against converted HF repo names
        # stored WITHOUT an owner prefix. It can never be a member.
        index = build_index()
        repo_key = "qwen/qwen3.5-0.8b"
        old_style_bare_repos = {
            a["huggingface"]["repo"].lower()
            for a in FIXTURE_ARTIFACTS["artifacts"]
        }
        self.assertNotIn(repo_key, old_style_bare_repos)  # the F4 bug
        # The fixed dedup catches it via the authored upstream_repo field.
        self.assertEqual(
            discover.match_candidate("Qwen", "Qwen3.5-0.8B", index),
            "upstream_repo",
        )

    def test_upstream_repo_match_is_case_insensitive(self):
        index = build_index()
        self.assertEqual(
            discover.match_candidate("qwen", "QWEN3.5-0.8B", index),
            "upstream_repo",
        )

    def test_hf_base_model_layer(self):
        # 'Nanonets-OCR-s' shares no name fragment with 'unlimited-ocr':
        # only the base_model lineage layer can identify it as ported.
        index = build_index()
        self.assertEqual(
            discover.match_candidate("nanonets", "Nanonets-OCR-s", index),
            "hf_base_model",
        )

    def test_fuzzy_name_fallback(self):
        # No upstream_repo on gemma-3-4b-it; upstream name normalizes to
        # the same string as the catalog name ('gemma34bit').
        index = build_index()
        self.assertEqual(
            discover.match_candidate("google", "Gemma-3-4b-it", index),
            "name_fuzzy",
        )

    def test_fuzzy_containment_needs_min_length(self):
        # 'VL' normalizes to 2 chars — must NOT swallow qwen3-vl-2b.
        index = build_index()
        self.assertIsNone(discover.match_candidate("someorg", "VL", index))

    def test_genuinely_new_model_is_not_matched(self):
        index = build_index()
        self.assertIsNone(
            discover.match_candidate("mistralai", "Voxtral-Mini-3B", index)
        )

    def test_normalize_name(self):
        self.assertEqual(
            discover.normalize_name("Qwen3.5-0.8B"),
            discover.normalize_name("qwen3-5-0-8b"),
        )

    def test_base_models_from_tags(self):
        # Tag shapes verified live against the HF API (2026-07-03).
        tags = [
            "core-ai",
            "base_model:deepreinforce-ai/Ornith-1.0-9B",
            "base_model:finetune:deepreinforce-ai/Ornith-1.0-9B",
            "license:mit",
        ]
        self.assertEqual(
            discover.base_models_from_tags(tags),
            {"deepreinforce-ai/ornith-1.0-9b"},
        )
        self.assertEqual(discover.base_models_from_tags([]), set())
        self.assertEqual(discover.base_models_from_tags(["base_model:"]), set())


class TestFetchArtifactBaseModels(unittest.TestCase):
    def test_one_call_per_owner_filtered_to_catalog_repos(self):
        calls: list[str] = []

        def fake_fetch(url, timeout=15):
            calls.append(url)
            return [
                {
                    "id": "mlboydaisuke/qwen3.5-0.8B-CoreAI",
                    "tags": ["base_model:Qwen/Qwen3.5-0.8B"],
                },
                {
                    # Not referenced by artifacts.yaml → must be ignored
                    "id": "mlboydaisuke/other-repo",
                    "tags": ["base_model:someorg/other-model"],
                },
            ]

        lineage = discover.fetch_artifact_base_models(FIXTURE_ARTIFACTS, fake_fetch)
        self.assertEqual(len(calls), 1)  # one owner → one API call
        self.assertIn("qwen/qwen3.5-0.8b", lineage)
        self.assertNotIn("someorg/other-model", lineage)

    def test_fetch_failure_yields_empty_set(self):
        lineage = discover.fetch_artifact_base_models(
            FIXTURE_ARTIFACTS, lambda url, timeout=15: None
        )
        self.assertEqual(lineage, set())


def fake_qwen_fetch(url, timeout=15):
    """Fixture-backed replacement for the HF org listing fetch."""
    if "author=Qwen" not in url:
        return []
    return [
        {  # already ported (upstream_repo) → must be filtered out
            "modelId": "Qwen/Qwen3.5-0.8B",
            "tags": ["safetensors"],
            "downloads": 999999,
        },
        {  # genuinely new small model
            "modelId": "Qwen/Qwen9-3B-Instruct",
            "tags": ["pytorch"],
            "downloads": 250000,
            "license": "apache-2.0",
            "lastModified": "2026-07-01T00:00:00.000Z",
        },
        {  # genuinely new but way too big for iPhone
            "modelId": "Qwen/Qwen9-72B-Instruct",
            "tags": ["pytorch"],
            "downloads": 50000,
        },
    ]


class TestRunDiscovery(unittest.TestCase):
    def test_dedup_scoring_and_ranking(self):
        index = build_index()
        candidates = discover.run_discovery(
            fetch=fake_qwen_fetch, orgs=["Qwen"], index=index
        )
        names = [c.model_name for c in candidates]
        self.assertNotIn("Qwen3.5-0.8B", names)  # deduped
        self.assertIn("Qwen9-3B-Instruct", names)
        self.assertIn("Qwen9-72B-Instruct", names)
        top = candidates[0]
        self.assertEqual(top.model_name, "Qwen9-3B-Instruct")
        self.assertGreater(top.total_score, 0)
        self.assertEqual(
            top.total_score,
            top.gap_score + top.edge_score + top.first_score
            + top.device_score + top.quality_score + top.community_score,
        )

    def test_device_filter_iphone(self):
        index = build_index()
        candidates = discover.run_discovery(
            fetch=fake_qwen_fetch, orgs=["Qwen"], index=index,
            device_filter="iphone",
        )
        names = [c.model_name for c in candidates]
        self.assertIn("Qwen9-3B-Instruct", names)
        self.assertNotIn("Qwen9-72B-Instruct", names)  # 72B > 12B ceiling

    def test_limit(self):
        index = build_index()
        candidates = discover.run_discovery(
            fetch=fake_qwen_fetch, orgs=["Qwen"], index=index, limit=1
        )
        self.assertEqual(len(candidates), 1)


class TestRenderers(unittest.TestCase):
    def _candidates(self):
        index = build_index()
        return discover.run_discovery(
            fetch=fake_qwen_fetch, orgs=["Qwen"], index=index
        )

    def test_render_markdown_pinned_issue_body(self):
        body = discover.render_markdown(
            self._candidates(), scan_date="2026-07-03", catalog_count=4
        )
        self.assertIn(discover.PINNED_ISSUE_MARKER, body)
        self.assertIn("# Porting candidates", body)
        self.assertIn("upserted in place", body)  # anti-F5 statement
        self.assertIn("Qwen9-3B-Instruct", body)
        self.assertIn("**Catalog:** 4 models", body)
        self.assertIn("2026-07-03", body)

    def test_render_markdown_empty(self):
        body = discover.render_markdown([], scan_date="2026-07-03")
        self.assertIn(discover.PINNED_ISSUE_MARKER, body)
        self.assertIn("No porting candidates found", body)

    def test_render_json_round_trips(self):
        data = json.loads(discover.render_json(self._candidates()))
        self.assertTrue(data)
        for row in data:
            self.assertIn("model", row)
            self.assertIn("score", row)
            self.assertIn("hf_url", row)


# ── Issue form (F6) ──

FORM_TEMPLATE = _ROOT / ".github" / "ISSUE_TEMPLATE" / "model-request.yml"

#: element id in model-request.yml → dotted field in model.schema.json
DROPDOWN_TO_SCHEMA_FIELD = {
    "source_group": "source_group",
    "artifact_format": "artifact.format",
    "availability": "artifact.availability",
    "runtime_name": "runtime.runtime_name",
    "runner": "runtime.runner",
    "stock_runtime": "runtime.stock_runtime",
    "custom_kernel": "runtime.custom_kernel",
    "patch_required": "runtime.patch_required",
    "tokenizer_required": "runtime.tokenizer_required",
    "processor_required": "runtime.processor_required",
    "aot_required": "runtime.aot_required",
    "iphone": "device_support.iphone",
    "ipad": "device_support.ipad",
    "mac": "device_support.mac",
    "mac_only": "device_support.mac_only",
    "commercial_use": "license.commercial_use",
    "status": "status",
    "maturity": "maturity",
    "confidence": "confidence",
}

SAMPLE_ANSWERS = {
    "Model ID": "test-p1-model-request",
    "Display name": "Test P1 Model Request",
    "Family": "TestFam",
    "Source group": "external",
    "Source path (URL)": "https://huggingface.co/tester/test-p1-model-request",
    "Artifact ref": "_No response_",
    "Capabilities": "chat, text-generation",
    "Input modalities": "text",
    "Output modalities": "text",
    "Artifact format": "aimodel",
    "Artifact availability": "available",
    "Parameters": "1B",
    "Precision": "int8",
    "Quantization": "int8lin",
    "Artifact size": "900MB",
    "Runtime name": "apple-core-ai",
    "Runner": "CoreAIRunner",
    "Stock runtime": "true",
    "Custom kernel required": "false",
    "Patch required": "false",
    "Tokenizer required": "true",
    "Processor required": "unknown",
    "AOT required": "false",
    "iPhone support": "true",
    "iPad support": "unknown",
    "Mac support": "true",
    "Mac only": "false",
    "License name": "Apache-2.0",
    "Commercial use": "likely",
    "Status": "confirmed",
    "Maturity": "active",
    "Confidence": "medium",
    "Sources": "coreai-model-zoo",
    "Upstream repo": "tester/Test-P1-Model",
    "Hugging Face owner": "tester",
    "Hugging Face repo": "test-p1-model-request-CoreAI",
    "GitHub owner": "_No response_",
    "GitHub repo": "_No response_",
    "GitHub path": "_No response_",
    "Notes": "_No response_",
}


def render_form_body(answers: dict) -> str:
    """Render a body exactly as GitHub renders a submitted issue form."""
    blocks = []
    for label, _, _ in discover.FORM_FIELDS:
        value = answers.get(label, "_No response_")
        blocks.append(f"### {label}\n\n{value}")
    return "\n\n".join(blocks)


class TestIssueFormTemplate(unittest.TestCase):
    """The template is the parse contract AND a schema mirror — pin both."""

    @classmethod
    def setUpClass(cls):
        cls.template = yaml.safe_load(FORM_TEMPLATE.read_text())
        cls.elements = [
            e for e in cls.template.get("body", []) if e.get("type") != "markdown"
        ]
        cls.model_schema = contribute.load_schema("model", _ROOT)

    def test_template_exists_and_old_markdown_template_is_gone(self):
        self.assertTrue(FORM_TEMPLATE.exists())
        self.assertFalse(
            (FORM_TEMPLATE.parent / "model-request.md").exists(),
            "free-form model-request.md must be replaced by the issue form",
        )

    def test_labels_match_parse_contract(self):
        template_labels = {e["attributes"]["label"] for e in self.elements}
        contract_labels = {label for label, _, _ in discover.FORM_FIELDS}
        self.assertEqual(
            template_labels, contract_labels,
            "model-request.yml labels and discover.FORM_FIELDS must stay in sync",
        )

    def test_every_dropdown_matches_its_schema_enum(self):
        # Regeneration guard: dropdown options are generated from the schema
        # enums — if a schema enum changes, this fails until the form is
        # regenerated (as the template header comment demands).
        dropdowns = {
            e["id"]: e for e in self.elements if e["type"] == "dropdown"
        }
        for element_id, dotted in DROPDOWN_TO_SCHEMA_FIELD.items():
            with self.subTest(field=element_id):
                self.assertIn(element_id, dropdowns)
                options = dropdowns[element_id]["attributes"]["options"]
                enum = contribute.schema_enum(self.model_schema, dotted)
                self.assertTrue(enum, f"no enum in schema for {dotted}")
                self.assertEqual(
                    [str(o).lower() for o in options],
                    [str(o).lower() for o in enum],
                    f"dropdown '{element_id}' drifted from schema enum {dotted}",
                )

    def test_every_dropdown_has_a_schema_mapping(self):
        template_dropdown_ids = {
            e["id"] for e in self.elements if e["type"] == "dropdown"
        }
        self.assertEqual(template_dropdown_ids, set(DROPDOWN_TO_SCHEMA_FIELD))

    def test_schema_required_fields_are_covered_by_the_form(self):
        # 1:1 mapping claim: every required model-schema field is collected
        # (last_verified is defaulted to the submission date by the parser).
        covered = {
            "id", "name", "family", "source_group", "source_path",
            "artifact_ref", "capabilities", "modalities", "artifact", "size",
            "runtime", "device_support", "license", "status", "maturity",
            "confidence", "sources", "notes",
        }
        required = set(self.model_schema["required"])
        self.assertEqual(required - covered, {"last_verified"})

    def test_template_declares_model_request_label(self):
        self.assertIn("model-request", self.template.get("labels", []))


class TestIssueFormRoundTrip(unittest.TestCase):
    def test_parse_issue_form(self):
        body = render_form_body(SAMPLE_ANSWERS)
        parsed = discover.parse_issue_form(body)
        self.assertEqual(parsed["Model ID"], "test-p1-model-request")
        self.assertEqual(parsed["Capabilities"], "chat, text-generation")
        self.assertNotIn("Notes", parsed)         # _No response_ dropped
        self.assertNotIn("Artifact ref", parsed)  # _No response_ dropped

    def test_form_to_fields_defaults_and_coercion(self):
        parsed = discover.parse_issue_form(render_form_body(SAMPLE_ANSWERS))
        fields, problems = discover.issue_form_to_fields(parsed)
        self.assertEqual(problems, [])
        self.assertEqual(fields["artifact_ref"], "test-p1-model-request")  # ← id
        self.assertIsNone(fields["notes"])
        self.assertIs(fields["stock_runtime"], True)
        self.assertIs(fields["custom_kernel"], False)
        self.assertEqual(fields["processor_required"], "unknown")
        self.assertEqual(fields["capabilities"], ["chat", "text-generation"])
        self.assertRegex(fields["last_verified"], r"^\d{4}-\d{2}-\d{2}$")

    def test_missing_fields_are_aggregated_never_fail_fast(self):
        answers = dict(SAMPLE_ANSWERS)
        del answers["Family"]
        answers["Hugging Face owner"] = "_No response_"
        answers["Hugging Face repo"] = "_No response_"
        parsed = discover.parse_issue_form(render_form_body(answers))
        _, problems = discover.issue_form_to_fields(parsed)
        self.assertEqual(len(problems), 2)
        self.assertTrue(any("Family" in p for p in problems))
        self.assertTrue(any("artifact host" in p for p in problems))

    def test_full_round_trip_validates_clean(self):
        # The workflow path: body → process_model_request → contribute
        # --dry-run semantics. Must be clean against the real repo data.
        body = render_form_body(SAMPLE_ANSWERS)
        result = discover.process_model_request(body, root=_ROOT)
        self.assertEqual(result["problems"], [])
        self.assertEqual(
            [contribute.format_error(e) for e in result["errors"]], []
        )
        self.assertTrue(result["ok"])
        model = result["model_entry"]
        artifact = result["artifact_entry"]
        self.assertEqual(model["id"], "test-p1-model-request")
        self.assertEqual(artifact["huggingface"]["owner"], "tester")
        # upstream_repo is only authored once the schema supports it
        schema_props = contribute.load_schema("model", _ROOT).get("properties", {})
        if "upstream_repo" in schema_props:
            self.assertEqual(model.get("upstream_repo"), "tester/Test-P1-Model")
        else:
            self.assertNotIn("upstream_repo", model)
        # entries re-validate independently (belt and braces)
        self.assertEqual(contribute.schema_errors("model", model, _ROOT), [])
        self.assertEqual(contribute.schema_errors("artifact", artifact, _ROOT), [])

    def test_duplicate_id_is_rejected(self):
        answers = dict(SAMPLE_ANSWERS)
        answers["Model ID"] = "qwen3-vl-2b"  # exists in the real catalog
        result = discover.process_model_request(
            render_form_body(answers), root=_ROOT
        )
        self.assertFalse(result["ok"])
        self.assertTrue(
            any(e["field"] == "id" and "already exists" in e["message"]
                for e in result["errors"])
        )

    def test_bad_enum_gets_hint(self):
        answers = dict(SAMPLE_ANSWERS)
        answers["Status"] = "unverified"  # the A3 trap value
        result = discover.process_model_request(
            render_form_body(answers), root=_ROOT
        )
        self.assertFalse(result["ok"])
        status_errors = [e for e in result["errors"] if e["field"] == "status"]
        self.assertTrue(status_errors)
        self.assertIn("valid values", status_errors[0]["hint"] or "")


# ── Source monitor (F5) ──

class TestSourceMonitorStubs(unittest.TestCase):
    def _detected(self) -> dict:
        m = {
            "account": "mlboydaisuke",
            "repo": "mlboydaisuke/Foo-2B-Instruct-CoreAI",
            "repo_short": "Foo-2B-Instruct-CoreAI",
            "last_modified": "2026-07-01",
            "is_new": True,
            "url": "https://huggingface.co/mlboydaisuke/Foo-2B-Instruct-CoreAI",
        }
        m.update(source_monitor.classify_model(m["repo_short"]))
        return m

    def test_build_candidate_stub(self):
        stub = source_monitor.build_candidate_stub(self._detected())
        self.assertEqual(stub["kind"], "model-candidate")
        self.assertEqual(stub["model"]["id"], "foo-2b-instruct")
        self.assertEqual(stub["model"]["source_group"], "zoo")
        self.assertEqual(stub["model"]["runtime"]["runner"], "CoreAIRunner")
        self.assertEqual(stub["artifact"]["huggingface"]["owner"], "mlboydaisuke")
        self.assertEqual(
            stub["artifact"]["officiality"]["apple_export_recipe"], False
        )
        # Never fabricate: unknowable facts stay absent / listed as missing
        self.assertNotIn("license", stub["model"])
        self.assertNotIn("size", stub["model"])
        self.assertIn("family", stub["missing_required"])
        self.assertIn("license.name", stub["missing_required"])
        self.assertEqual(stub["model"]["device_support"]["iphone"], "unknown")

    def test_official_repo_maps_to_stock_runner(self):
        m = {
            "account": "mlboydaisuke",
            "repo": "mlboydaisuke/qwen3-4b-CoreAI-official",
            "repo_short": "qwen3-4b-CoreAI-official",
            "last_modified": "2026-07-01",
            "is_new": True,
            "url": "https://huggingface.co/mlboydaisuke/qwen3-4b-CoreAI-official",
        }
        m.update(source_monitor.classify_model(m["repo_short"]))
        stub = source_monitor.build_candidate_stub(m)
        self.assertEqual(stub["model"]["source_group"], "official")
        self.assertIs(stub["model"]["runtime"]["stock_runtime"], True)
        self.assertIs(
            stub["artifact"]["officiality"]["apple_export_recipe"], True
        )

    def test_report_embeds_stubs_and_upsert_marker(self):
        detected = self._detected()
        report = {
            "scan_time": "2026-07-03T00:00:00+00:00",
            "since_date": "2026-06-30",
            "catalog_count": 80,
            "hf_total_checked": 10,
            "hf_new_count": 1,
            "new_models": [detected],
            "candidate_stubs": [source_monitor.build_candidate_stub(detected)],
            "zoo_status": {"new": []},
        }
        text = source_monitor.format_report(report)
        self.assertIn(source_monitor.PINNED_ISSUE_MARKER, text)
        self.assertIn("candidate_stubs.json", text)
        self.assertIn("upserted in place", text)
        # the embedded JSON block round-trips
        block = text.split("```json\n", 1)[1].split("\n```", 1)[0]
        stubs = json.loads(block)
        self.assertEqual(stubs[0]["model"]["id"], "foo-2b-instruct")


class TestWorkflowFiles(unittest.TestCase):
    """The workflows exist and encode the single-pinned-issue upsert."""

    def test_discover_workflow(self):
        wf = yaml.safe_load(
            (_ROOT / ".github" / "workflows" / "discover.yml").read_text()
        )
        # PyYAML parses the `on:` key as boolean True
        triggers = wf.get("on", wf.get(True))
        self.assertIn("schedule", triggers)
        self.assertIn("workflow_dispatch", triggers)
        text = (_ROOT / ".github" / "workflows" / "discover.yml").read_text()
        self.assertIn("gh issue edit", text)   # upsert, not create-always
        self.assertIn("gh issue pin", text)
        self.assertIn("porting-candidates", text)

    def test_source_monitor_workflow_upserts(self):
        text = (_ROOT / ".github" / "workflows" / "source-monitor.yml").read_text()
        self.assertIn("gh issue edit", text)
        self.assertIn("gh issue pin", text)
        self.assertNotIn("$(date -u", text)  # no timestamped duplicate titles

    def test_model_request_workflow(self):
        path = _ROOT / ".github" / "workflows" / "model-request-to-pr.yml"
        wf = yaml.safe_load(path.read_text())
        triggers = wf.get("on", wf.get(True))
        self.assertIn("issues", triggers)
        text = path.read_text()
        self.assertIn("model-request", text)
        self.assertIn("process_model_request", text)
        self.assertIn("--draft", text)          # draft PR, human merges
        self.assertIn("gh issue comment", text)  # verdict always commented

    def test_governance_and_codeowners_exist(self):
        gov = (_ROOT / "GOVERNANCE.md").read_text()
        for rule in ("M1", "M2", "M3", "M4", "M5"):
            self.assertIn(rule, gov)
        owners = (_ROOT / ".github" / "CODEOWNERS").read_text()
        self.assertIn("@kevinqz", owners)
        self.assertIn("/catalog.yaml", owners)
        self.assertIn("/artifacts.yaml", owners)


if __name__ == "__main__":
    unittest.main(verbosity=2)
