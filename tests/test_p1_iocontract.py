#!/usr/bin/env python3
"""
P1 tests — WP-C "io-contract" (redteam findings C1, C2, C5, C6, C7, E5).

Covers:
- schema/model.schema.json: io_contract / bundle_kind / min_os /
  superseded_by / deprecation / upstream_repo accept valid values and
  reject invalid ones (additionalProperties: false inside io_contract)
- catalog.yaml: every model carries an authored bundle_kind + min_os;
  unlimited-ocr is authored `ocr` (the C5 mis-bucket fix); authored
  values agree with the capability derivation
- coreai_catalog/exports.py: derive_bundle_kind / validate_bundle_kind
  (disagreement raises → generate fails); model-manifest and search-index
  carry bundle_kind / min_os / io_contract
- coreai_catalog/installer.py: io_contract-driven snippet for image-input
  models references the image input (C1), interpolates the resolved
  artifact path, and is labeled; contract-less models fall back to the
  labeled runner-bucket template
- scripts/bootstrap_io_contracts.py: tree classification and small-file
  selection logic (no network)

Run: python -m pytest tests/test_p1_iocontract.py -v
"""
from __future__ import annotations

import copy
import json
import shutil
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

import bootstrap_io_contracts  # noqa: E402  (scripts/)
from coreai_catalog.exports import (  # noqa: E402
    derive_bundle_kind,
    export_model_manifest,
    export_search_index,
    validate_bundle_kind,
)
from coreai_catalog.installer import (  # noqa: E402
    _generate_swift_snippet,
    get_model_dir,
    snippet_source,
)

MODEL_SCHEMA = json.loads((_ROOT / "schema" / "model.schema.json").read_text())
CATALOG = yaml.safe_load((_ROOT / "catalog.yaml").read_text())
ARTIFACTS = yaml.safe_load((_ROOT / "artifacts.yaml").read_text())
MODELS = {m["id"]: m for m in CATALOG["models"]}
ARTIFACTS_BY_ID = {a["id"]: a for a in ARTIFACTS["artifacts"]}


def _artifact_for(model: dict) -> dict:
    return ARTIFACTS_BY_ID[model.get("artifact_ref", model["id"])]


def _schema_errors(entry: dict) -> list[str]:
    validator = Draft202012Validator(MODEL_SCHEMA)
    return [e.message for e in validator.iter_errors(entry)]


class TestModelSchemaNewFields(unittest.TestCase):
    """Schema-level accept/reject for the WP-C additive fields."""

    def setUp(self):
        # A real, currently-valid entry as the mutation base.
        self.base = copy.deepcopy(MODELS["unlimited-ocr"])

    def test_current_catalog_entries_validate(self):
        for m in CATALOG["models"]:
            errs = _schema_errors(m)
            self.assertEqual(errs, [], f"{m['id']}: {errs}")

    def test_bundle_kind_rejects_unknown_value(self):
        self.base["bundle_kind"] = "chatbot"
        self.assertTrue(_schema_errors(self.base))

    def test_bundle_kind_accepts_ocr(self):
        self.base["bundle_kind"] = "ocr"
        self.assertEqual(_schema_errors(self.base), [])

    def test_min_os_rejects_non_version_string(self):
        self.base["min_os"] = {"macos": "Tahoe"}
        self.assertTrue(_schema_errors(self.base))

    def test_min_os_rejects_unknown_key(self):
        self.base["min_os"] = {"macos": "27.0", "watchos": "12.0"}
        self.assertTrue(_schema_errors(self.base))

    def test_io_contract_rejects_unknown_property(self):
        self.base["io_contract"] = {"entrypoint": {}, "made_up": True}
        self.assertTrue(_schema_errors(self.base))

    def test_io_contract_input_requires_name_and_modality(self):
        self.base["io_contract"] = {"inputs": [{"swift_type": "CGImage"}]}
        self.assertTrue(_schema_errors(self.base))

    def test_io_contract_input_rejects_unknown_preprocessing_key(self):
        self.base["io_contract"] = {
            "inputs": [
                {"name": "image", "modality": "image",
                 "preprocessing": {"gamma": "2.2"}}
            ]
        }
        self.assertTrue(_schema_errors(self.base))

    def test_deprecation_requires_date_and_reason(self):
        self.base["deprecation"] = {"date": "2026-07-01"}
        self.assertTrue(_schema_errors(self.base))
        self.base["deprecation"] = {"date": "2026-07-01", "reason": "superseded"}
        self.assertEqual(_schema_errors(self.base), [])

    def test_superseded_by_accepts_model_id(self):
        self.base["superseded_by"] = "some-newer-model"
        self.assertEqual(_schema_errors(self.base), [])

    def test_upstream_repo_rejects_non_org_name(self):
        self.base["upstream_repo"] = "just-a-name"
        self.assertTrue(_schema_errors(self.base))
        self.base["upstream_repo"] = "Qwen/Qwen3-0.6B"
        self.assertEqual(_schema_errors(self.base), [])


class TestAuthoredCatalogValues(unittest.TestCase):
    """The 80 models carry authored bundle_kind/min_os; C5 is fixed."""

    def test_every_model_has_bundle_kind(self):
        missing = [m["id"] for m in CATALOG["models"] if "bundle_kind" not in m]
        self.assertEqual(missing, [])

    def test_every_apple_core_ai_model_has_min_os_27(self):
        # Grounded in apple/coreai-models Package.swift:
        #   platforms: [.macOS("27.0"), .iOS("27.0")]
        for m in CATALOG["models"]:
            if m.get("runtime", {}).get("runtime_name") == "apple-core-ai":
                self.assertEqual(
                    m.get("min_os"), {"macos": "27.0", "ios": "27.0"}, m["id"]
                )

    def test_unlimited_ocr_is_ocr_not_llm(self):
        self.assertEqual(MODELS["unlimited-ocr"]["bundle_kind"], "ocr")

    def test_authored_kinds_agree_with_derivation(self):
        for m in CATALOG["models"]:
            self.assertEqual(
                m["bundle_kind"], derive_bundle_kind(m),
                f"{m['id']}: authored {m['bundle_kind']}"
            )

    def test_io_contracts_authored_for_priority_models(self):
        with_contract = {m["id"] for m in CATALOG["models"] if m.get("io_contract")}
        # C1 poster child + one exemplar per contractable bundle_kind.
        for mid in (
            "unlimited-ocr", "official-qwen3-0-6b", "minicpm-v-4-6",
            "rf-detr-nano", "depth-anything-3-base", "official-sam-3",
            "official-whisper-large-v3-turbo", "official-flux-2-klein-4b",
            "qwen3-embedding-0-6b", "qwen3-reranker-0-6b", "vjepa2-vitl-ssv2",
        ):
            self.assertIn(mid, with_contract)

    def test_unlimited_ocr_contract_declares_image_input(self):
        ioc = MODELS["unlimited-ocr"]["io_contract"]
        modalities = {i["modality"] for i in ioc["inputs"]}
        self.assertIn("image", modalities)

    def test_upstream_repo_values_look_like_org_name(self):
        for m in CATALOG["models"]:
            if "upstream_repo" in m:
                self.assertIn("/", m["upstream_repo"], m["id"])


class TestBundleKindValidator(unittest.TestCase):
    """The exports heuristic is demoted to a validator (C5)."""

    def _model(self, caps, inputs=("text",), authored=None):
        m = {
            "id": "test-model",
            "capabilities": list(caps),
            "modalities": {"input": list(inputs), "output": ["text"]},
        }
        if authored:
            m["bundle_kind"] = authored
        return m

    def test_disagreement_raises(self):
        m = self._model(["document-ocr"], inputs=["image"], authored="llm")
        with self.assertRaises(ValueError) as ctx:
            validate_bundle_kind(m)
        self.assertIn("disagreement", str(ctx.exception))

    def test_agreement_returns_authored(self):
        m = self._model(["document-ocr"], inputs=["image"], authored="ocr")
        self.assertEqual(validate_bundle_kind(m), "ocr")

    def test_missing_authored_returns_derived(self):
        m = self._model(["chat", "text-generation"])
        self.assertEqual(validate_bundle_kind(m), "llm")

    def test_image_input_language_model_is_vlm_not_llm(self):
        # The C5 failure mode: an image-input model bucketed `llm`.
        m = self._model(["chat", "text-generation"], inputs=["text", "image"])
        self.assertEqual(derive_bundle_kind(m), "vlm")

    def test_unmapped_capability_raises(self):
        m = self._model(["totally-new-capability"])
        with self.assertRaises(ValueError):
            derive_bundle_kind(m)

    def test_export_fails_on_catalog_with_disagreement(self):
        # Copy the real root's YAML into a tmp root, corrupt one authored
        # kind (enum-valid but capability-wrong), and expect the export —
        # and with it generate.py — to fail.
        tmp = Path(tempfile.mkdtemp(prefix="ioc-test-"))
        try:
            cat = copy.deepcopy(CATALOG)
            cat["models"][0]["bundle_kind"] = (
                "ocr" if cat["models"][0]["bundle_kind"] != "ocr" else "llm"
            )
            (tmp / "catalog.yaml").write_text(yaml.safe_dump(cat, sort_keys=False))
            shutil.copy2(_ROOT / "artifacts.yaml", tmp / "artifacts.yaml")
            with self.assertRaises(ValueError):
                export_model_manifest(tmp, dist=tmp / "dist")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestExportSurfaces(unittest.TestCase):
    """model-manifest + search-index carry the contract fields."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="ioc-dist-"))
        export_model_manifest(_ROOT, dist=cls.tmp)
        export_search_index(_ROOT, dist=cls.tmp)
        cls.manifest = json.loads((cls.tmp / "model-manifest.json").read_text())
        cls.index = json.loads((cls.tmp / "search-index.json").read_text())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_manifest_unlimited_ocr_bundle_kind(self):
        entry = next(e for e in self.manifest["models"] if e["id"] == "unlimited-ocr")
        self.assertEqual(entry["bundle_kind"], "ocr")
        self.assertEqual(entry["min_os"], {"macos": "27.0", "ios": "27.0"})
        self.assertTrue(entry["io_contract"])

    def test_manifest_carries_upstream_repo_when_authored(self):
        entry = next(
            e for e in self.manifest["models"] if e["id"] == "official-qwen3-0-6b"
        )
        self.assertEqual(entry["upstream_repo"], "Qwen/Qwen3-0.6B")

    def test_search_index_carries_contract_fields(self):
        entry = next(m for m in self.index["models"] if m["id"] == "unlimited-ocr")
        self.assertEqual(entry["bundle_kind"], "ocr")
        self.assertEqual(entry["min_os"], {"macos": "27.0", "ios": "27.0"})
        self.assertTrue(entry["io_contract"])


class TestContractSnippets(unittest.TestCase):
    """C1/C6: snippets are contract-driven when a contract exists."""

    def test_unlimited_ocr_snippet_references_image_input(self):
        m = MODELS["unlimited-ocr"]
        snippet = _generate_swift_snippet(m, _artifact_for(m))
        self.assertIn("Snippet source: io_contract", snippet)
        self.assertIn("document_image", snippet)
        self.assertIn("CGImage", snippet)
        # The C1 bug: a text-only chat template for a document-image model.
        self.assertNotIn("Hello, how are you?", snippet)
        # The resolved local artifact path is interpolated.
        self.assertIn(str(get_model_dir(m["id"]) / "artifacts"), snippet)

    def test_vlm_snippet_uses_real_image_api(self):
        m = MODELS["minicpm-v-4-6"]
        snippet = _generate_swift_snippet(m, _artifact_for(m))
        self.assertIn("Snippet source: io_contract", snippet)
        self.assertIn("encodeImage", snippet)

    def test_detector_snippet_interpolates_aimodel_path(self):
        m = MODELS["rf-detr-nano"]
        snippet = _generate_swift_snippet(m, _artifact_for(m))
        self.assertIn("ObjectDetector", snippet)
        self.assertIn("rfdetr-nano_float32.aimodel", snippet)
        self.assertNotIn("<install-dir>", snippet)

    def test_contract_less_model_falls_back_labeled(self):
        m = MODELS["qwen3-5-2b"]
        self.assertNotIn("io_contract", m)
        snippet = _generate_swift_snippet(m, _artifact_for(m))
        self.assertIn("Snippet source: runner-bucket template", snippet)

    def test_snippet_source_labels(self):
        self.assertEqual(snippet_source(MODELS["unlimited-ocr"]), "io_contract")
        self.assertEqual(snippet_source(MODELS["qwen3-5-2b"]), "runner_bucket")

    def test_every_contract_snippet_mentions_each_input_modality(self):
        # Spec §3.3: a snippet must reference each declared input modality.
        for m in CATALOG["models"]:
            ioc = m.get("io_contract")
            if not ioc:
                continue
            snippet = _generate_swift_snippet(m, _artifact_for(m))
            for inp in ioc.get("inputs", []):
                self.assertIn(
                    inp["name"], snippet,
                    f"{m['id']}: snippet does not mention input '{inp['name']}'",
                )


class TestBootstrapScript(unittest.TestCase):
    """Pure-logic tests for scripts/bootstrap_io_contracts.py (no network)."""

    PATHS = {
        "README.md": 3512,
        "assets/embed_tokens.f16": 330956800,
        "assets/recipe.json": 677,
        "decoder": None,
        "decoder/model.aimodel": None,
        "decoder/model.aimodel/main.mlirb": 3391059192,
        "decoder/model.aimodel/metadata.json": 28,
        "macos/metadata.json": 600,
        "tokenizer/tokenizer.json": 9979544,
        "tokenizer/tokenizer_config.json": 165938,
    }

    def test_classify_tree_finds_bundle_metadata(self):
        tree = bootstrap_io_contracts.classify_tree(self.PATHS)
        self.assertEqual(tree["aimodel_dirs"], ["decoder/model.aimodel"])
        # The 28-byte metadata.json INSIDE the .aimodel is not bundle-level.
        self.assertEqual(tree["bundle_metadata_files"], ["macos/metadata.json"])
        self.assertEqual(tree["tokenizer_dirs"], ["tokenizer"])

    def test_pick_downloads_never_selects_weights_or_big_files(self):
        picks = bootstrap_io_contracts.pick_downloads(self.PATHS)
        self.assertIn("assets/recipe.json", picks)
        self.assertIn("macos/metadata.json", picks)
        self.assertIn("tokenizer/tokenizer_config.json", picks)
        self.assertNotIn("assets/embed_tokens.f16", picks)
        self.assertNotIn("decoder/model.aimodel/main.mlirb", picks)
        self.assertNotIn("tokenizer/tokenizer.json", picks)  # ~10MB blob
        for p in picks:
            self.assertLessEqual(
                self.PATHS[p], bootstrap_io_contracts.MAX_FILE_BYTES
            )


if __name__ == "__main__":
    unittest.main()
