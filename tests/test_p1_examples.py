"""P1 example-package tests (redteam findings C3, C4, C8, C10).

Verifies:
1. Each example under examples/ is a real SwiftPM package (Package.swift +
   Sources/<target>/main.swift + README.md) — no README-only conceptual
   examples remain (C4/C8), and the old conceptual dirs are gone.
2. `swift package dump-package` parses every example manifest (skipped
   when no Swift toolchain is present), and the dumped manifest declares
   platforms macOS 27.0 / iOS 27.0 plus a dependency on the real
   https://github.com/apple/coreai-models package with its REAL product
   names (CoreAILM / CoreAIObjectDetection / CoreAISpeech).
3. `xcrun swiftc -parse` accepts every example source file (macOS only).
4. Capability tables in examples/*/README.md are generated from
   catalog.yaml and in sync (scripts/generate_example_tables.py --check),
   and their values match the catalog — in particular the unlimited-ocr
   license row says MIT / check_license, killing the C4 contradiction
   (the old README claimed Apache-2.0 / Encoder).
5. No unsourced capability claims (C10): the fabricated claims from the
   old examples are gone, and every README states the macOS 27 minimum.
6. The swift-examples workflow exists, is valid YAML, always runs
   dump-package, and makes the no-macOS-27-SDK skip visible.
"""
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples'
WORKFLOW = ROOT / '.github' / 'workflows' / 'swift-examples.yml'

EXPECTED_EXAMPLES = {
    'llm-chat': 'CoreAILM',
    'ocr-vlm': 'CoreAILM',
    'object-detection': 'CoreAIObjectDetection',
    'speech-transcription': 'CoreAISpeech',
}
REMOVED_CONCEPTUAL = ['ocr-swiftui', 'vlm-chat', 'embeddings-rag']
COREAI_MODELS_URL = 'https://github.com/apple/coreai-models'

SWIFT = shutil.which('swift')


def example_dirs() -> list[Path]:
    return sorted(d for d in EXAMPLES.iterdir()
                  if d.is_dir() and (d / 'Package.swift').exists())


def dump_package(package_dir: Path) -> dict:
    result = subprocess.run(
        ['swift', 'package', 'dump-package'],
        capture_output=True, text=True, cwd=package_dir,
    )
    if result.returncode != 0:
        raise AssertionError(
            f'dump-package failed for {package_dir.name}:\n{result.stderr}')
    return json.loads(result.stdout)


class TestPackageStructure(unittest.TestCase):
    def test_expected_examples_exist_as_real_packages(self):
        for name in EXPECTED_EXAMPLES:
            with self.subTest(example=name):
                pkg = EXAMPLES / name
                self.assertTrue((pkg / 'Package.swift').is_file(),
                                f'{name}: missing Package.swift')
                self.assertTrue((pkg / 'README.md').is_file(),
                                f'{name}: missing README.md')
                main = pkg / 'Sources' / name / 'main.swift'
                self.assertTrue(main.is_file(), f'{name}: missing {main}')

    def test_old_conceptual_examples_removed(self):
        for name in REMOVED_CONCEPTUAL:
            self.assertFalse((EXAMPLES / name).exists(),
                             f'conceptual example {name} should be gone')

    def test_no_readme_only_example_dirs(self):
        for d in EXAMPLES.iterdir():
            if d.is_dir():
                self.assertTrue((d / 'Package.swift').exists(),
                                f'{d.name}: README-only examples are banned')


@unittest.skipIf(SWIFT is None, 'swift toolchain not available')
class TestDumpPackage(unittest.TestCase):
    def test_dump_package_parses_and_declares_real_contract(self):
        for name, product in EXPECTED_EXAMPLES.items():
            with self.subTest(example=name):
                manifest = dump_package(EXAMPLES / name)

                platforms = {p['platformName']: p['version']
                             for p in manifest['platforms']}
                self.assertEqual(platforms.get('macos'), '27.0')
                self.assertEqual(platforms.get('ios'), '27.0')

                dep_urls = [
                    str(d['sourceControl'][0]['location']['remote'][0].get(
                        'urlString', ''))
                    for d in manifest['dependencies'] if 'sourceControl' in d
                ]
                self.assertTrue(
                    any(COREAI_MODELS_URL in u for u in dep_urls),
                    f'{name}: must depend on {COREAI_MODELS_URL}, got {dep_urls}')

                products = set()
                for target in manifest['targets']:
                    for dep in target.get('dependencies', []):
                        if 'product' in dep:
                            products.add(dep['product'][0])
                self.assertIn(product, products,
                              f'{name}: must use real product {product}')

    def test_swiftc_parse_accepts_every_source(self):
        if sys.platform != 'darwin':
            self.skipTest('xcrun swiftc only available on macOS')
        sources = [p for p in EXAMPLES.rglob('*.swift')
                   if p.name != 'Package.swift']
        self.assertTrue(sources, 'no example sources found')
        for src in sources:
            with self.subTest(source=str(src.relative_to(ROOT))):
                result = subprocess.run(
                    ['xcrun', 'swiftc', '-parse', str(src)],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0,
                                 f'swiftc -parse failed:\n{result.stderr}')


class TestGeneratedTables(unittest.TestCase):
    def test_tables_in_sync_with_catalog(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'generate_example_tables.py'),
             '--check'],
            capture_output=True, text=True, cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0,
                         f'stale/broken tables:\n{result.stdout}{result.stderr}')

    def test_table_values_match_catalog(self):
        models = {m['id']: m
                  for m in yaml.safe_load((ROOT / 'catalog.yaml').read_text())['models']}
        marker = re.compile(
            r'<!-- BEGIN GENERATED: capability-table model=([\w.-]+) -->(.*?)'
            r'<!-- END GENERATED: capability-table -->', re.DOTALL)
        seen = 0
        for readme in EXAMPLES.glob('*/README.md'):
            for model_id, body in marker.findall(readme.read_text()):
                seen += 1
                model = models.get(model_id)
                self.assertIsNotNone(model, f'{readme}: unknown model {model_id}')
                lic = model['license']
                self.assertIn(f"| License | {lic['name']} |", body)
                self.assertIn(f"| Commercial use | {lic['commercial_use']} |", body)
        self.assertGreaterEqual(seen, len(EXPECTED_EXAMPLES),
                                'every example needs >=1 generated table')

    def test_c4_contradiction_dead(self):
        """The OCR example must state the catalog license (MIT/check_license),
        not the old fabricated Apache-2.0 / 'commercial use: likely'."""
        ocr = (EXAMPLES / 'ocr-vlm' / 'README.md').read_text()
        self.assertIn('| License | MIT |', ocr)
        self.assertIn('| Commercial use | check_license |', ocr)
        self.assertNotIn('License | Apache-2.0 (commercial use: likely)', ocr)

    def test_c10_no_fabricated_capability_claims(self):
        """Claims the old examples invented but catalog.yaml never made."""
        banned = [
            'handles printed and handwritten text',  # old ocr-swiftui caveat
            'response.embedding',                    # invented embedding API
            'typically 768 or 1536 dimensions',      # invented embedding dims
        ]
        for readme in EXAMPLES.rglob('README.md'):
            text = readme.read_text()
            for phrase in banned:
                self.assertNotIn(phrase, text,
                                 f'{readme}: fabricated claim "{phrase}"')

    def test_min_os_stated_everywhere(self):
        for name in EXPECTED_EXAMPLES:
            text = (EXAMPLES / name / 'README.md').read_text()
            self.assertIn('macOS 27', text, f'{name}: must state min_os')
            self.assertIn('macOS 26', text,
                          f'{name}: must warn macOS 26 machines cannot run it')


class TestWorkflow(unittest.TestCase):
    def test_workflow_exists_and_is_valid_yaml(self):
        self.assertTrue(WORKFLOW.is_file())
        data = yaml.safe_load(WORKFLOW.read_text())
        self.assertIn('jobs', data)

    def test_workflow_always_dumps_and_makes_skip_visible(self):
        text = WORKFLOW.read_text()
        self.assertIn('swift package dump-package', text)
        self.assertIn('swiftc -parse', text)
        self.assertIn('generate_example_tables.py --check', text)
        self.assertIn('GITHUB_STEP_SUMMARY', text)
        self.assertIn('SKIPPED', text)
        # The build step must be gated on SDK detection, not continue-on-error.
        self.assertNotIn('continue-on-error', text)
        self.assertIn("if: steps.sdk.outputs.macos27 == 'true'", text)


if __name__ == '__main__':
    unittest.main()
