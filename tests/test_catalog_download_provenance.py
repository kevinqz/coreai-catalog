"""dist/catalog.json must carry each model's download provenance.

The catalog is the single source of truth: a consumer reading only the model
catalog (e.g. the Swift coreai-runner) must be able to resolve WHERE to fetch a
model's `.aimodel` bundle. The download provenance is authored in artifacts.yaml
(keyed by artifact id); export_json joins it onto each model as
`provenance.huggingface` so dist/catalog.json is self-sufficient. This test
guarantees that join never silently regresses.
"""

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from coreai_catalog.exports import export_json

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestCatalogDownloadProvenance(unittest.TestCase):
    def _artifacts_with_hf(self):
        arts = yaml.safe_load((REPO_ROOT / "artifacts.yaml").read_text())["artifacts"]
        return {a["id"]: a for a in arts if a.get("huggingface")}

    def test_catalog_json_models_carry_hf_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            export_json(REPO_ROOT, dist)
            catalog = json.loads((dist / "catalog.json").read_text())

        hf_by_id = self._artifacts_with_hf()
        models = catalog["models"]
        checked = 0
        for m in models:
            ref = m.get("artifact_ref")
            if ref not in hf_by_id:
                continue  # artifact has no HF block → model legitimately has no provenance
            checked += 1
            prov = m.get("provenance")
            self.assertIsNotNone(
                prov, f"{m['id']}: expected provenance joined from artifact {ref!r}")
            hf = prov.get("huggingface")
            self.assertIsNotNone(hf, f"{m['id']}: provenance.huggingface missing")
            # Shape the runner (and any consumer) relies on to resolve a download.
            for key in ("owner", "repo", "url"):
                self.assertIn(key, hf, f"{m['id']}: provenance.huggingface.{key} missing")
            # It must be the SAME provenance authored in artifacts.yaml (no drift).
            self.assertEqual(hf, hf_by_id[ref]["huggingface"],
                             f"{m['id']}: joined provenance differs from artifacts.yaml")

        self.assertGreater(checked, 0, "expected at least one model with HF provenance")

    def test_rf_detr_nano_resolves_a_download(self):
        """Concrete guard: the model that exposed the gap is now self-sufficient."""
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            export_json(REPO_ROOT, dist)
            catalog = json.loads((dist / "catalog.json").read_text())

        rf = next((m for m in catalog["models"] if m["id"] == "rf-detr-nano"), None)
        if rf is None:
            self.skipTest("rf-detr-nano not in catalog")
        hf = (rf.get("provenance") or {}).get("huggingface") or {}
        self.assertTrue(hf.get("owner") and hf.get("repo"),
                        "rf-detr-nano must resolve a huggingface owner/repo from the catalog")
        self.assertTrue(hf.get("files"), "rf-detr-nano must list downloadable files")


if __name__ == "__main__":
    unittest.main()
