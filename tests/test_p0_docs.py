"""P0 docs-contract tests (redteam findings A1, A3, A4, A7, A10, B4, F2).

Verifies:
1. scripts/doc_test.py runs green (all tagged doc examples + templates
   validate against the JSON Schemas).
2. scripts/generate_templates.py output is in sync with schema/*.json
   and every generated template validates against its schema.
3. The CONTRIBUTING.md benchmark example is schema-valid and uses the
   corrected field spellings (observed_date, enum extraction_method,
   compute_unit present, os_major as a string).
4. CONTRIBUTING.md / AGENTS.md no longer route contributors to the
   retired benchmarks.yaml store, document the benchmark lanes, the
   metadata.count bump, and the coreai-fabric contribution path.
5. benchmark-validate.yml stays valid YAML and contains the curator lane.
6. validate.yml runs the doc-test.
"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CONTRIBUTING = (ROOT / 'CONTRIBUTING.md').read_text()
AGENTS = (ROOT / 'AGENTS.md').read_text()


def run_script(name: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / name), *args],
        capture_output=True, text=True, cwd=ROOT,
    )


class TestDocTest(unittest.TestCase):
    """scripts/doc_test.py validates docs + templates and passes."""

    def test_doc_test_runs_green(self):
        result = run_script('doc_test.py')
        self.assertEqual(
            result.returncode, 0,
            f'doc_test.py failed:\n{result.stdout}\n{result.stderr}',
        )
        self.assertIn('OK:', result.stdout)

    def test_doc_test_catches_invalid_example(self):
        """A schema-invalid entry is reported, not silently accepted."""
        from scripts.doc_test import validate_entries
        errors = validate_entries(
            [{'id': 'x', 'extraction_method': 'upstream-readme'}],
            'benchmark', 'unit-test',
        )
        self.assertTrue(errors, 'invalid benchmark entry should produce errors')

    def test_contributing_has_tagged_examples(self):
        """CONTRIBUTING carries doc-test-tagged model, artifact, benchmark examples."""
        for entity in ('model', 'artifact', 'benchmark'):
            self.assertIn(
                f'<!-- doc-test: {entity} -->', CONTRIBUTING,
                f'CONTRIBUTING.md must include a tagged {entity} example',
            )


class TestTemplates(unittest.TestCase):
    """templates/ are schema-generated and schema-valid (finding A3)."""

    def test_templates_in_sync_with_schemas(self):
        result = run_script('generate_templates.py', '--check')
        self.assertEqual(
            result.returncode, 0,
            f'templates are stale — run scripts/generate_templates.py:\n'
            f'{result.stdout}\n{result.stderr}',
        )

    def test_yaml_templates_validate(self):
        for entity in ('model', 'artifact'):
            schema = json.loads(
                (ROOT / 'schema' / f'{entity}.schema.json').read_text()
            )
            validator = Draft202012Validator(schema)
            data = yaml.safe_load(
                (ROOT / 'templates' / f'{entity}-entry.yaml').read_text()
            )
            entries = data if isinstance(data, list) else [data]
            for entry in entries:
                errors = list(validator.iter_errors(entry))
                self.assertFalse(
                    errors,
                    f'{entity} template invalid: '
                    + '; '.join(e.message for e in errors),
                )

    def test_benchmark_template_validates(self):
        schema = json.loads((ROOT / 'schema' / 'benchmark.schema.json').read_text())
        validator = Draft202012Validator(schema)
        text = (ROOT / 'templates' / 'benchmark-entry.jsonl').read_text()
        entries = [
            json.loads(line) for line in text.splitlines()
            if line.strip() and not line.startswith('#')
        ]
        self.assertTrue(entries, 'benchmark template must contain a JSONL example line')
        for entry in entries:
            entry.pop('_signature', None)
            errors = list(validator.iter_errors(entry))
            self.assertFalse(
                errors,
                'benchmark template invalid: ' + '; '.join(e.message for e in errors),
            )

    def test_model_template_enums_match_schema(self):
        """Template comments list enum values exactly (no rejected values)."""
        schema = json.loads((ROOT / 'schema' / 'model.schema.json').read_text())
        text = (ROOT / 'templates' / 'model-entry.yaml').read_text()
        for field in ('status', 'maturity', 'confidence'):
            enum = schema['properties'][field]['enum']
            line = next(
                l for l in text.splitlines() if l.strip().startswith(f'{field}:')
            )
            for value in enum:
                self.assertIn(
                    str(value), line,
                    f'template comment for {field} must list enum value {value!r}',
                )


class TestContributingContract(unittest.TestCase):
    """CONTRIBUTING matches the enforced contract (findings A1, A4, A7, A10)."""

    def _benchmark_example(self) -> dict:
        m = re.search(
            r'<!--\s*doc-test:\s*benchmark\s*-->\s*```\w*\n(.*?)```',
            CONTRIBUTING, re.S,
        )
        self.assertIsNotNone(m, 'benchmark example not found in CONTRIBUTING.md')
        return json.loads(m.group(1).strip())

    def test_benchmark_example_is_schema_valid(self):
        schema = json.loads((ROOT / 'schema' / 'benchmark.schema.json').read_text())
        entry = self._benchmark_example()
        errors = list(Draft202012Validator(schema).iter_errors(entry))
        self.assertFalse(
            errors,
            'CONTRIBUTING benchmark example invalid: '
            + '; '.join(e.message for e in errors),
        )

    def test_benchmark_example_corrected_fields(self):
        entry = self._benchmark_example()
        schema = json.loads((ROOT / 'schema' / 'benchmark.schema.json').read_text())
        self.assertIn('observed_date', entry, 'must use observed_date, not observed')
        self.assertNotIn('observed', set(entry) - {'observed_date'})
        self.assertIn(
            entry['extraction_method'],
            schema['properties']['extraction_method']['enum'],
        )
        self.assertIn('compute_unit', entry)
        self.assertIsInstance(entry['os_major'], str, 'os_major must be a string')

    def test_no_benchmarks_yaml_references(self):
        """The retired benchmarks.yaml store is never referenced (A10)."""
        self.assertNotIn('benchmarks.yaml', CONTRIBUTING)
        self.assertNotIn('benchmarks.yaml', AGENTS)

    def test_lane_separation_documented(self):
        """Model PRs never touch benchmarks.jsonl; lanes are explicit (A1)."""
        self.assertIn('benchmarks.jsonl', CONTRIBUTING)
        self.assertRegex(
            CONTRIBUTING,
            r'model PR must \*\*never\*\* touch `benchmarks\.jsonl`',
        )
        self.assertIn('exactly one line', CONTRIBUTING.lower().replace('**', ''))
        self.assertIn('benchmark-curator-review', CONTRIBUTING)
        self.assertIn('not yet public', CONTRIBUTING.lower())
        self.assertIn('_signature', CONTRIBUTING)

    def test_metadata_count_bump_documented(self):
        """artifacts.yaml metadata.count bump is documented (A7)."""
        self.assertIn('metadata.count', CONTRIBUTING)

    def test_fabric_contribution_path_documented(self):
        for text, name in ((CONTRIBUTING, 'CONTRIBUTING.md'), (AGENTS, 'AGENTS.md')):
            self.assertIn(
                'github.com/kevinqz/coreai-fabric', text,
                f'{name} must point new conversions at coreai-fabric',
            )
            flat = ' '.join(text.replace('**', '').split())
            self.assertIn(
                'indexed reference upstream', flat,
                f'{name} must describe the zoo as an indexed reference upstream',
            )

    def test_fabric_surfaced_across_awareness_surfaces(self):
        """Boundary redteam: fabric was absent from every agent-bootstrap and
        moment-of-need surface. Guard the full set so it can't silently regress
        back to the pre-fabric story (only 2 surfaces were guarded before)."""
        surfaces = [
            'README.md',
            'llms.txt',
            'GOVERNANCE.md',
            'agent.json',
            'docs/data-model.md',
            'site/index.html',
            'mcp_server/server.py',
            'coreai_catalog/discover.py',
        ]
        for rel in surfaces:
            text = (ROOT / rel).read_text()
            self.assertIn(
                'coreai-fabric', text,
                f'{rel} must mention coreai-fabric (agent/human awareness surface)',
            )

    def test_site_no_longer_routes_conversion_to_zoo(self):
        """The site Contribute aside must route conversion to fabric, not to
        coremltools + the zoo (the pre-fabric misroute)."""
        site = (ROOT / 'site' / 'index.html').read_text()
        idx = site.find('contribute-aside')
        self.assertNotEqual(idx, -1, 'site must have the contribute-aside')
        aside = site[idx:idx + 700]
        self.assertIn('coreai-fabric', aside,
                      'the conversion aside must route to coreai-fabric')


class TestWorkflows(unittest.TestCase):
    """CI workflows stay valid YAML and carry the new lanes/steps."""

    def test_benchmark_validate_yaml_is_valid(self):
        text = (ROOT / '.github' / 'workflows' / 'benchmark-validate.yml').read_text()
        data = yaml.safe_load(text)
        self.assertIn('jobs', data)

    def test_benchmark_validate_has_curator_lane(self):
        text = (ROOT / '.github' / 'workflows' / 'benchmark-validate.yml').read_text()
        self.assertIn('benchmark-curator-review', text)
        self.assertIn("startswith('upstream_readme_')", text)
        # The signature gate must be skipped for the curator lane.
        self.assertIn("steps.lane.outputs.lane != 'curator'", text)
        # Auto-merge stays gated on the strict relay lane.
        self.assertIn("steps.lane.outputs.lane == 'relay'", text)

    def test_validate_workflow_runs_doc_test(self):
        text = (ROOT / '.github' / 'workflows' / 'validate.yml').read_text()
        yaml.safe_load(text)
        self.assertIn('doc_test.py', text)
        self.assertIn('generate_templates.py --check', text)


if __name__ == '__main__':
    unittest.main()
