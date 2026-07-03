#!/usr/bin/env python3
"""
Tests for P0 content-addressing (findings A2, B7, C9, D1, E1, F8).

Covers:
  - artifact.schema.json: github optional via anyOf(github, huggingface);
    new optional huggingface.revision / huggingface.files, provenance,
    mirrors — accepting valid data and rejecting garbage
  - model.schema.json: source_group gains "fabric"
  - installer digest verification (streamed sha256 against temp files)
  - backfill parser against a canned HF API response fixture

No network access. No downloads.

Run: python -m pytest tests/test_p0_addressing.py -v
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from coreai_catalog.installer import _sha256_file, verify_file_digests

ROOT = Path(__file__).resolve().parents[1]

_backfill_spec = importlib.util.spec_from_file_location(
    "backfill_digests", ROOT / "scripts" / "backfill_digests.py"
)
backfill_digests = importlib.util.module_from_spec(_backfill_spec)
_backfill_spec.loader.exec_module(backfill_digests)


def load_validator(schema_name: str) -> Draft202012Validator:
    schema = json.loads((ROOT / "schema" / schema_name).read_text())
    return Draft202012Validator(schema)


def base_artifact() -> dict:
    """A minimal valid artifact with only a huggingface block (no github)."""
    return {
        "id": "test-model",
        "group": "external",
        "huggingface": {
            "owner": "someone",
            "repo": "some-model-CoreAI",
            "url": "https://huggingface.co/someone/some-model-CoreAI",
        },
        "officiality": {
            "apple_export_recipe": False,
            "apple_hosted_artifact": False,
            "community_packaged": True,
        },
    }


REVISION = "34ed8b08946395397c3b01d07d0a532237e71af3"
SHA256 = "62c3344ec4a2ee8f6275e7659efe6a9cbb299161dcd41b7898818559661f722d"


# ── artifact schema: anyOf(github, huggingface) ────────────────────────


class TestArtifactSchemaAnyOf(unittest.TestCase):
    def setUp(self):
        self.validator = load_validator("artifact.schema.json")

    def test_huggingface_only_is_valid(self):
        self.assertEqual(list(self.validator.iter_errors(base_artifact())), [])

    def test_github_only_is_valid(self):
        artifact = base_artifact()
        del artifact["huggingface"]
        artifact["github"] = {"owner": "john-rocky", "repo": "coreai-model-zoo"}
        self.assertEqual(list(self.validator.iter_errors(artifact)), [])

    def test_neither_github_nor_huggingface_is_invalid(self):
        artifact = base_artifact()
        del artifact["huggingface"]
        self.assertTrue(list(self.validator.iter_errors(artifact)))


# ── artifact schema: revision + files ──────────────────────────────────


class TestArtifactSchemaDigests(unittest.TestCase):
    def setUp(self):
        self.validator = load_validator("artifact.schema.json")

    def test_revision_and_files_valid(self):
        artifact = base_artifact()
        artifact["huggingface"]["revision"] = REVISION
        artifact["huggingface"]["files"] = [
            {"path": "model.aimodel/main.mlirb", "sha256": SHA256,
             "size_bytes": 1309019209},
        ]
        self.assertEqual(list(self.validator.iter_errors(artifact)), [])

    def test_bad_revision_rejected(self):
        artifact = base_artifact()
        artifact["huggingface"]["revision"] = "main"  # not a 40-hex sha
        self.assertTrue(list(self.validator.iter_errors(artifact)))

    def test_bad_sha256_rejected(self):
        artifact = base_artifact()
        artifact["huggingface"]["files"] = [
            {"path": "a.bin", "sha256": "nothex", "size_bytes": 1},
        ]
        self.assertTrue(list(self.validator.iter_errors(artifact)))

    def test_file_entry_missing_size_rejected(self):
        artifact = base_artifact()
        artifact["huggingface"]["files"] = [
            {"path": "a.bin", "sha256": SHA256},
        ]
        self.assertTrue(list(self.validator.iter_errors(artifact)))

    def test_file_entry_extra_property_rejected(self):
        artifact = base_artifact()
        artifact["huggingface"]["files"] = [
            {"path": "a.bin", "sha256": SHA256, "size_bytes": 1, "md5": "x"},
        ]
        self.assertTrue(list(self.validator.iter_errors(artifact)))


# ── artifact schema: provenance + mirrors ──────────────────────────────


class TestArtifactSchemaProvenance(unittest.TestCase):
    def setUp(self):
        self.validator = load_validator("artifact.schema.json")

    def test_full_provenance_valid(self):
        artifact = base_artifact()
        artifact["provenance"] = {
            "converted_by": {
                "tool": "coreai-fabric",
                "version": "0.3.1",
                "recipe_url": "https://github.com/kevinqz/coreai-fabric/blob/main/recipes/qwen.py",
            },
            "recipe_source": "fabric",
            "format_version": "aimodel-v1",
        }
        self.assertEqual(list(self.validator.iter_errors(artifact)), [])

    def test_all_recipe_source_values_accepted(self):
        for value in ("apple-official", "zoo-port", "fabric", "independent"):
            artifact = base_artifact()
            artifact["provenance"] = {"recipe_source": value}
            self.assertEqual(
                list(self.validator.iter_errors(artifact)), [],
                f"recipe_source {value} should be valid",
            )

    def test_garbage_recipe_source_rejected(self):
        artifact = base_artifact()
        artifact["provenance"] = {"recipe_source": "trust-me-bro"}
        self.assertTrue(list(self.validator.iter_errors(artifact)))

    def test_provenance_extra_property_rejected(self):
        artifact = base_artifact()
        artifact["provenance"] = {"vibes": "good"}
        self.assertTrue(list(self.validator.iter_errors(artifact)))

    def test_mirrors_valid(self):
        artifact = base_artifact()
        artifact["mirrors"] = [
            {"owner": "coreai-community", "repo": "some-model-CoreAI",
             "url": "https://huggingface.co/coreai-community/some-model-CoreAI",
             "revision": REVISION},
        ]
        self.assertEqual(list(self.validator.iter_errors(artifact)), [])

    def test_mirror_missing_url_rejected(self):
        artifact = base_artifact()
        artifact["mirrors"] = [{"owner": "coreai-community", "repo": "x"}]
        self.assertTrue(list(self.validator.iter_errors(artifact)))

    def test_mirror_extra_property_rejected(self):
        artifact = base_artifact()
        artifact["mirrors"] = [
            {"owner": "a", "repo": "b", "url": "https://huggingface.co/a/b",
             "priority": 1},
        ]
        self.assertTrue(list(self.validator.iter_errors(artifact)))


# ── model schema: source_group fabric ──────────────────────────────────


class TestModelSchemaFabric(unittest.TestCase):
    def setUp(self):
        schema = json.loads((ROOT / "schema" / "model.schema.json").read_text())
        self.enum = schema["properties"]["source_group"]["enum"]

    def test_fabric_in_enum(self):
        self.assertIn("fabric", self.enum)

    def test_existing_values_stay(self):
        for value in ("zoo", "official", "external", "unknown"):
            self.assertIn(value, self.enum)


# ── installer: streamed hashing + digest verification ─────────────────


class TestInstallerHashCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.payload = b"coreai-catalog test payload\n" * 1024
        (self.dir / "weights.bin").write_bytes(self.payload)
        self.digest = hashlib.sha256(self.payload).hexdigest()

    def tearDown(self):
        self.tmp.cleanup()

    def test_sha256_file_matches_hashlib(self):
        self.assertEqual(_sha256_file(self.dir / "weights.bin"), self.digest)

    def test_matching_digest_verifies(self):
        files = [{"path": "weights.bin", "sha256": self.digest,
                  "size_bytes": len(self.payload)}]
        result = verify_file_digests(self.dir, files, verbose=False)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["files_verified"], 1)
        self.assertEqual(result["mismatched"], [])
        self.assertEqual(result["missing"], [])

    def test_mismatched_digest_fails(self):
        files = [{"path": "weights.bin", "sha256": "0" * 64,
                  "size_bytes": len(self.payload)}]
        result = verify_file_digests(self.dir, files, verbose=False)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["mismatched"], ["weights.bin"])

    def test_missing_file_fails(self):
        files = [{"path": "not-there.bin", "sha256": self.digest,
                  "size_bytes": 1}]
        result = verify_file_digests(self.dir, files, verbose=False)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["missing"], ["not-there.bin"])

    def test_nested_path_verifies(self):
        nested = self.dir / "model.aimodel"
        nested.mkdir()
        (nested / "main.mlirb").write_bytes(self.payload)
        files = [{"path": "model.aimodel/main.mlirb", "sha256": self.digest,
                  "size_bytes": len(self.payload)}]
        result = verify_file_digests(self.dir, files, verbose=False)
        self.assertEqual(result["status"], "verified")


# ── backfill: parser against a canned API response ─────────────────────


CANNED_RESPONSE = {
    "id": "someone/some-model-CoreAI",
    "sha": REVISION,
    "siblings": [
        # non-LFS file: only a git-sha1 blobId → must NOT be attested
        {"rfilename": "README.md",
         "blobId": "69779a23bc5a37eeaa6b1e6157f3beedc9fc437d", "size": 10621},
        # LFS file: sha256 OID → attested
        {"rfilename": "model.aimodel/main.mlirb",
         "blobId": "cc127c7037041fa6e5de72bc4dd64377a5e0d913",
         "size": 1309019209,
         "lfs": {"sha256": SHA256, "size": 1309019209, "pointerSize": 135}},
        # malformed sibling → ignored, never fabricated
        {"rfilename": "broken.bin", "lfs": {"size": 5}},
    ],
}


class TestBackfillParser(unittest.TestCase):
    def test_parses_revision_and_lfs_files_only(self):
        revision, files = backfill_digests.parse_hf_model_info(CANNED_RESPONSE)
        self.assertEqual(revision, REVISION)
        self.assertEqual(files, [
            {"path": "model.aimodel/main.mlirb", "sha256": SHA256,
             "size_bytes": 1309019209},
        ])

    def test_missing_sha_yields_none(self):
        revision, files = backfill_digests.parse_hf_model_info({"siblings": []})
        self.assertIsNone(revision)
        self.assertEqual(files, [])

    def test_no_lfs_files_yields_empty_list(self):
        revision, files = backfill_digests.parse_hf_model_info({
            "sha": REVISION,
            "siblings": [{"rfilename": "config.json", "blobId": "abc", "size": 3}],
        })
        self.assertEqual(revision, REVISION)
        self.assertEqual(files, [])

    def test_parsed_files_pass_artifact_schema(self):
        """Backfill output must satisfy the schema contract exactly."""
        revision, files = backfill_digests.parse_hf_model_info(CANNED_RESPONSE)
        artifact = base_artifact()
        artifact["huggingface"]["revision"] = revision
        artifact["huggingface"]["files"] = files
        validator = load_validator("artifact.schema.json")
        self.assertEqual(list(validator.iter_errors(artifact)), [])


if __name__ == "__main__":
    unittest.main()
