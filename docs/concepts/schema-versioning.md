# Schema Versioning

Core AI Catalog follows [Semantic Versioning](https://semver.org/) for the
catalog data schema, separate from the software package version.

## Two version numbers

Every JSON export includes two version fields:

```json
{
  "export_schema_version": "1.0",
  "export_catalog_version": "1.6.0"
}
```

| Field | What it tracks | When it changes |
|---|---|---|
| `export_schema_version` | The structure/format of the export | Only on breaking export format changes |
| `export_catalog_version` | The catalog content version | Every release with data changes |

## SemVer for schema changes

### Patch (1.0.x)

- New model records added
- Existing records updated (metadata corrections, new benchmarks)
- No structural changes to YAML or JSON schema

Consumers should not need to update code.

### Minor (1.x.0)

- New optional fields added to model/artifact/benchmark records
- New export files (e.g. `dist/tasks/`)
- New capabilities or task synonyms

Consumers should handle unknown fields gracefully (use `**kwargs` or
`.get()` patterns), but existing code should continue to work.

### Major (x.0.0)

- Breaking schema changes: renamed fields, removed fields, changed types
- Structural reorganization of YAML files

A migration guide will be provided with every major version bump.

## Current schema versions

| Schema | Version | File |
|---|---|---|
| Model | 1.0 | `schema/model.schema.json` |
| Artifact | 1.0 | `schema/artifact.schema.json` |
| Benchmark | 1.0 | `schema/benchmark.schema.json` |
| Upstream | 1.0 | `schema/upstream.schema.json` |
| Term | 1.0 | `schema/term.schema.json` |
| Export | 1.0 | All `dist/*.json` files |

## Consumer guidance

### For agents (MCP, llms.txt)

Agents should always check `export_catalog_version` to detect data updates.
The `export_schema_version` should be checked to detect format changes.

```python
import json, requests

data = requests.get("https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/catalog.json").json()
schema_ver = data["export_schema_version"]
catalog_ver = data["export_catalog_version"]

if schema_ver != "1.0":
    print(f"Warning: schema version {schema_ver} may require code updates")
```

### For programmatic consumers (Python API)

```python
from coreai_catalog import Catalog

catalog = Catalog.load()
print(f"Catalog version: {catalog.version}")
print(f"Models: {catalog.model_count}")
```

The Python API is versioned with the package (`pyproject.toml` version).
Breaking API changes follow SemVer and will be documented in the CHANGELOG.

### For raw JSON consumers

Always use `.get()` for optional fields. Never assume a field exists on every
record — use `unknown` or `not_published` as the default for missing data.

## Validation guarantee

Every record in the catalog validates against its JSON Schema (`schema/*.json`).
The CI pipeline runs `scripts/validate.py` on every push, ensuring schema
compliance.

If you need to validate records in your own code:

```python
import jsonschema

schema = json.loads(Path("schema/model.schema.json").read_text())
jsonschema.validate(model_record, schema)
```
