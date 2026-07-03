"""
Core AI Catalog contribution toolkit.

Single implementation of candidate-entry validation shared by three
surfaces (redteam findings A6/A9/F3):

  1. ``scripts/validate.py``   — repo-wide aggregated validation
  2. ``coreai-catalog contribute`` — CLI draft → validate → write → PR
  3. MCP ``validate_entry``    — pre-flight validation for agents

Every error is a structured dict — ``{file, entity_id, field, message,
hint}`` — and validation is NEVER fail-fast: all errors for an entry (and
across entries) are aggregated so a contributor fixes everything in one
round-trip. Enum values, required fields, and fix hints are rendered from
the JSON Schemas at runtime — nothing is hardcoded, so schema changes
propagate automatically.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from .catalog import _find_catalog_root

#: Entity kinds this toolkit understands: data file, schema file, and the
#: top-level list key inside the YAML file (None for JSONL / grouped files).
ENTITY_KINDS: dict[str, dict] = {
    "model": {"file": "catalog.yaml", "schema": "model.schema.json", "list_key": "models"},
    "artifact": {"file": "artifacts.yaml", "schema": "artifact.schema.json", "list_key": "artifacts"},
    "benchmark": {"file": "benchmarks.jsonl", "schema": "benchmark.schema.json", "list_key": None},
    "source": {"file": "sources.yaml", "schema": "source.schema.json", "list_key": "sources"},
    "upstream": {"file": "upstreams.yaml", "schema": "upstream.schema.json", "list_key": None},
    "term": {"file": "terms.yaml", "schema": "term.schema.json", "list_key": "terms"},
}

#: upstreams.yaml groups all records under these keys (no single list key).
UPSTREAM_GROUPS = [
    "framework_sources",
    "conversion_sources",
    "artifact_hosts",
    "benchmark_sources",
    "sample_sources",
    "original_model_sources",
    "license_sources",
]


# ── Loading helpers ──


def find_root() -> Path:
    """Locate the catalog repo root (where catalog.yaml lives)."""
    return _find_catalog_root()


def read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def read_benchmarks_jsonl(path: Path) -> list[dict]:
    """Read benchmarks.jsonl entries (comment lines and blanks skipped)."""
    entries: list[dict] = []
    if not path.exists():
        return entries
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def load_schema(kind: str, root: Path | None = None) -> dict:
    """Load the JSON Schema for an entity kind."""
    if kind not in ENTITY_KINDS:
        raise ValueError(
            f"Unknown entity kind '{kind}'. Valid kinds: {sorted(ENTITY_KINDS)}"
        )
    root = root or find_root()
    schema_path = root / "schema" / ENTITY_KINDS[kind]["schema"]
    return json.loads(schema_path.read_text())


def schema_enum(schema: dict, dotted_field: str) -> list:
    """Render the enum for a (possibly nested) field from a schema at runtime.

    ``schema_enum(model_schema, 'license.commercial_use')`` →
    ``['likely', 'check_license']``. Returns [] when the field has no enum.
    Never hardcode enum values — always render them from the schema.
    """
    node = schema
    for part in dotted_field.split("."):
        node = (node.get("properties") or {}).get(part)
        if node is None:
            return []
    return list(node.get("enum", []))


def required_fields(schema: dict) -> list[str]:
    """Top-level required field names, straight from the schema."""
    return list(schema.get("required", []))


# ── Fix-hint machinery ──


def suggest(value: str, options, limit: int = 3) -> list[str]:
    """Near-miss suggestions for a bad value (shared by CLI/MCP/validators)."""
    if not isinstance(value, str) or not value:
        return []
    pool = [o for o in options if isinstance(o, str)]
    matches = difflib.get_close_matches(value, pool, n=limit, cutoff=0.5)
    if not matches:
        lowered = value.lower()
        matches = [o for o in pool if lowered in o.lower() or o.lower() in lowered]
    return matches[:limit]


def _fmt_options(options) -> str:
    return ", ".join(str(o) for o in options)


def _hint_for(error) -> str | None:
    """Build an actionable fix hint from a jsonschema ValidationError."""
    if error.validator == "enum":
        options = error.validator_value
        hint = f"valid values: {_fmt_options(options)}"
        near = suggest(error.instance, options)
        if near:
            hint = f"did you mean '{near[0]}'? " + hint
        return hint
    if error.validator == "additionalProperties":
        unexpected = re.findall(r"'([^']+)'", error.message)
        known = sorted((error.schema.get("properties") or {}).keys())
        parts = []
        for prop in unexpected:
            near = suggest(prop, known)
            if near:
                parts.append(f"'{prop}' → did you mean '{near[0]}'?")
        base = f"allowed fields: {_fmt_options(known)}"
        return ("; ".join(parts) + "; " + base) if parts else base
    if error.validator == "required":
        missing = re.findall(r"'([^']+)' is a required property", error.message)
        if missing:
            descs = []
            for field in missing:
                node = (error.schema.get("properties") or {}).get(field) or {}
                enum = node.get("enum")
                if enum:
                    descs.append(f"add '{field}' (one of: {_fmt_options(enum)})")
                else:
                    descs.append(f"add '{field}'")
            return "; ".join(descs)
        return None
    if error.validator == "pattern":
        return f"value must match pattern {error.validator_value}"
    if error.validator == "type":
        return f"expected type: {error.validator_value}"
    if error.validator == "anyOf":
        # artifact schema: anyOf(github, huggingface)
        alternatives = []
        for sub in error.validator_value:
            req = sub.get("required")
            if req:
                alternatives.append("/".join(req))
        if alternatives:
            return f"provide at least one of: {_fmt_options(alternatives)}"
    return None


def _field_path(error) -> str:
    path = ".".join(str(p) for p in error.path)
    if error.validator == "required":
        missing = re.findall(r"'([^']+)' is a required property", error.message)
        if missing:
            return f"{path}.{missing[0]}" if path else missing[0]
    return path or "<root>"


def make_error(
    file: str,
    entity_id: str,
    field: str,
    message: str,
    hint: str | None = None,
) -> dict:
    """Structured validation error shared by all three surfaces."""
    return {
        "file": file,
        "entity_id": entity_id,
        "field": field,
        "message": message,
        "hint": hint,
    }


def format_error(err: dict) -> str:
    """One-line human rendering of a structured error."""
    line = f"{err['file']} :: {err['entity_id']} :: {err['field']}: {err['message']}"
    if err.get("hint"):
        line += f"  [hint: {err['hint']}]"
    return line


# ── Schema validation (aggregated, never fail-fast) ──


def schema_errors(
    kind: str,
    payload: dict,
    root: Path | None = None,
    schema: dict | None = None,
) -> list[dict]:
    """Validate one entry against its schema; return ALL errors with hints."""
    if schema is None:
        schema = load_schema(kind, root)
    if not isinstance(payload, dict):
        return [
            make_error(
                ENTITY_KINDS[kind]["file"],
                "<not-an-object>",
                "<root>",
                f"entry must be an object/mapping, got {type(payload).__name__}",
                None,
            )
        ]
    candidate = dict(payload)
    if kind == "benchmark":
        candidate.pop("_signature", None)  # relay signature is not part of the schema
    validator = Draft202012Validator(schema)
    entity_id = str(candidate.get("id", "<missing id>"))
    errors: list[dict] = []
    for error in sorted(validator.iter_errors(candidate), key=lambda e: list(e.path)):
        errors.append(
            make_error(
                ENTITY_KINDS[kind]["file"],
                entity_id,
                _field_path(error),
                error.message,
                _hint_for(error),
            )
        )
    return errors


# ── Cross-reference validation ──


def ids_context(root: Path | None = None) -> dict:
    """Load the ID universe used by cross-reference checks."""
    root = root or find_root()
    catalog = read_yaml(root / "catalog.yaml")
    artifacts = read_yaml(root / "artifacts.yaml")
    sources = read_yaml(root / "sources.yaml")
    upstreams = read_yaml(root / "upstreams.yaml")
    benchmarks = read_benchmarks_jsonl(root / "benchmarks.jsonl")

    upstream_ids: set[str] = set()
    for group in UPSTREAM_GROUPS:
        for item in upstreams.get(group, []) or []:
            if "id" in item:
                upstream_ids.add(item["id"])

    return {
        "model_ids": {m["id"] for m in catalog.get("models", []) if "id" in m},
        "artifact_ids": {a["id"] for a in artifacts.get("artifacts", []) if "id" in a},
        "source_ids": {s["id"] for s in sources.get("sources", []) if "id" in s},
        "upstream_ids": upstream_ids,
        "benchmark_ids": {b["id"] for b in benchmarks if "id" in b},
    }


def cross_reference_errors(kind: str, payload: dict, context: dict) -> list[dict]:
    """Per-entry cross-reference checks against the ID universe.

    Mirrors the rules enforced repo-wide by scripts/validate.py so a
    candidate entry gets the same verdict CI would give it.
    """
    if not isinstance(payload, dict):
        return []
    file = ENTITY_KINDS[kind]["file"]
    entity_id = str(payload.get("id", "<missing id>"))
    errors: list[dict] = []
    source_universe = context["source_ids"] | context["upstream_ids"]

    if kind == "model":
        ref = payload.get("artifact_ref")
        if ref is not None and ref not in context["artifact_ids"]:
            near = suggest(ref, context["artifact_ids"])
            hint = "add the matching artifacts.yaml entry (same id) in this change"
            if near:
                hint = f"did you mean '{near[0]}'? Otherwise " + hint
            errors.append(
                make_error(
                    file, entity_id, "artifact_ref",
                    f"points to missing artifact '{ref}'", hint,
                )
            )
        for source_id in payload.get("sources", []) or []:
            if source_id not in source_universe:
                near = suggest(source_id, source_universe)
                hint = "add a sources.yaml record for it (schema/source.schema.json)"
                if near:
                    hint = f"did you mean '{near[0]}'? Otherwise " + hint
                errors.append(
                    make_error(
                        file, entity_id, "sources",
                        f"points to missing source '{source_id}'", hint,
                    )
                )

    elif kind == "artifact":
        github = payload.get("github", {}) or {}
        path = github.get("path")
        owner, repo = github.get("owner"), github.get("repo")
        if isinstance(path, str) and path.startswith("https://github.com/"):
            if f"{owner}/{repo}" not in path:
                errors.append(
                    make_error(
                        file, entity_id, "github.path",
                        f"github.path '{path}' is inconsistent with owner/repo "
                        f"'{owner}/{repo}'",
                        "path URL must contain the same owner/repo",
                    )
                )

    elif kind == "benchmark":
        model_id = payload.get("model_id")
        if model_id is not None and model_id not in context["model_ids"]:
            near = suggest(model_id, context["model_ids"])
            hint = "model_id must be an existing catalog.yaml model id"
            if near:
                hint = f"did you mean '{near[0]}'? " + hint
            errors.append(
                make_error(
                    file, entity_id, "model_id",
                    f"points to missing model_id '{model_id}'", hint,
                )
            )
        source_id = payload.get("source")
        if source_id and source_id not in source_universe:
            near = suggest(source_id, source_universe)
            hint = "source must be a sources.yaml or upstreams.yaml record id"
            if near:
                hint = f"did you mean '{near[0]}'? " + hint
            errors.append(
                make_error(
                    file, entity_id, "source",
                    f"points to missing source '{source_id}'", hint,
                )
            )

    elif kind == "upstream" and payload.get("category") == "original_model":
        # Only original_model_sources use applies_to as model/artifact refs;
        # other upstream groups use it for free-form topic tags.
        for target in payload.get("applies_to", []) or []:
            if target not in context["model_ids"] and target not in context["artifact_ids"]:
                near = suggest(target, context["model_ids"] | context["artifact_ids"])
                hint = "applies_to targets must be existing model or artifact ids"
                if near:
                    hint = f"did you mean '{near[0]}'? " + hint
                errors.append(
                    make_error(
                        file, entity_id, "applies_to",
                        f"applies_to missing target '{target}'", hint,
                    )
                )

    return errors


def duplicate_id_error(kind: str, payload: dict, context: dict) -> dict | None:
    """Candidate-entry check: the id must not collide with an existing one."""
    if not isinstance(payload, dict):
        return None
    entity_id = payload.get("id")
    if not entity_id:
        return None
    existing = {
        "model": context["model_ids"],
        "artifact": context["artifact_ids"],
        "benchmark": context["benchmark_ids"],
        "source": context["source_ids"],
        "upstream": context["upstream_ids"],
    }.get(kind, set())
    if entity_id in existing:
        article = "an" if kind[0] in "aeiou" else "a"
        return make_error(
            ENTITY_KINDS[kind]["file"],
            str(entity_id),
            "id",
            f"{article} {kind} with id '{entity_id}' already exists",
            "pick a unique id (or edit the existing record instead of adding one)",
        )
    return None


def validate_entry(
    kind: str,
    payload: dict,
    root: Path | None = None,
    context: dict | None = None,
    check_duplicate_id: bool = True,
) -> list[dict]:
    """Validate a CANDIDATE entry: schema + cross-references + duplicate id.

    Returns an aggregated list of structured errors (empty = valid).
    This is the single validation core shared by the CLI ``contribute``
    command, the MCP ``validate_entry`` tool, and scripts/validate.py.
    """
    if kind not in ENTITY_KINDS:
        raise ValueError(
            f"Unknown entity kind '{kind}'. Valid kinds: {sorted(ENTITY_KINDS)}"
        )
    root = root or find_root()
    errors = schema_errors(kind, payload, root)
    if context is None:
        context = ids_context(root)
    errors.extend(cross_reference_errors(kind, payload, context))
    if check_duplicate_id:
        dup = duplicate_id_error(kind, payload, context)
        if dup:
            errors.append(dup)
    return errors


# ── Entry assembly (contribute model) ──


def build_model_entry(fields: dict) -> dict:
    """Assemble a catalog.yaml model entry in canonical key order.

    Only includes optional keys the caller actually provided — never
    invents values (leave unknowable optional fields absent).
    """
    entry = {
        "id": fields["id"],
        "name": fields["name"],
        "family": fields["family"],
        "source_group": fields["source_group"],
        "artifact_ref": fields.get("artifact_ref") or fields["id"],
        "source_path": fields["source_path"],
        "capabilities": list(fields["capabilities"]),
        "modalities": {
            "input": list(fields["input_modalities"]),
            "output": list(fields["output_modalities"]),
        },
        "artifact": {
            "format": fields["artifact_format"],
            "availability": fields["availability"],
        },
        "size": {
            "parameters": fields["parameters"],
            "precision": fields["precision"],
            "quantization": fields["quantization"],
            "artifact_size": fields["artifact_size"],
        },
        "runtime": {
            "runtime_name": fields["runtime_name"],
            "runner": fields["runner"],
            "stock_runtime": fields["stock_runtime"],
            "custom_kernel": fields["custom_kernel"],
            "patch_required": fields["patch_required"],
            "tokenizer_required": fields["tokenizer_required"],
            "processor_required": fields["processor_required"],
            "aot_required": fields["aot_required"],
        },
        "device_support": {
            "iphone": fields["iphone"],
            "ipad": fields["ipad"],
            "mac": fields["mac"],
            "mac_only": fields["mac_only"],
        },
        "license": {
            "name": fields["license_name"],
            "commercial_use": fields["commercial_use"],
        },
        "status": fields["status"],
        "maturity": fields["maturity"],
        "confidence": fields["confidence"],
        "sources": list(fields["sources"]),
        "last_verified": fields["last_verified"],
        "notes": fields.get("notes"),
    }
    for optional in ("architecture", "context_window", "streaming"):
        if fields.get(optional) is not None:
            entry[optional] = fields[optional]
    return entry


def build_artifact_entry(fields: dict) -> dict:
    """Assemble an artifacts.yaml entry (github and/or huggingface block).

    Model ``source_group: fabric`` maps to artifact ``group: external`` per
    the shared field contract (the artifact group enum has no 'fabric').
    """
    group = fields["source_group"]
    if group == "fabric":
        group = "external"
    entry: dict = {
        "id": fields.get("artifact_ref") or fields["id"],
        "group": group,
    }
    if fields.get("github_owner") and fields.get("github_repo"):
        gh: dict = {
            "owner": fields["github_owner"],
            "repo": fields["github_repo"],
        }
        if fields.get("github_path"):
            gh["path"] = fields["github_path"]
        entry["github"] = gh
    if fields.get("hf_owner") and fields.get("hf_repo"):
        entry["huggingface"] = {
            "owner": fields["hf_owner"],
            "repo": fields["hf_repo"],
            "url": f"https://huggingface.co/{fields['hf_owner']}/{fields['hf_repo']}",
        }
    entry["officiality"] = {
        "apple_export_recipe": fields["source_group"] == "official",
        "apple_hosted_artifact": False,
        "community_packaged": True,
    }
    return entry


def build_hf_source_record(fields: dict, today: str | None = None) -> dict:
    """sources.yaml record for a new Hugging Face artifact host repo."""
    owner, repo = fields["hf_owner"], fields["hf_repo"]
    return {
        "id": fields["new_source_id"],
        "title": f"{owner}/{repo}",
        "type": "huggingface_repository",
        "url": f"https://huggingface.co/{owner}/{repo}",
        "owner": owner,
        "repo": repo,
        "trust": "artifact_host",
        "volatility": "medium",
        "last_checked": today or date.today().isoformat(),
        "notes": f"Hugging Face artifact host for {fields['id']} "
                 "(registered via coreai-catalog contribute).",
    }


def build_benchmark_entry(fields: dict) -> dict:
    """Assemble a benchmarks.jsonl entry from contribute-benchmark fields."""
    entry = {
        "id": fields["id"],
        "model_id": fields["model_id"],
        "metric": fields["metric"],
        "value": fields["value"],
        "unit": fields["unit"],
        "device_class": fields["device_class"],
        "os_major": fields["os_major"],
        "compute_unit": fields["compute_unit"],
        "extraction_method": fields["extraction_method"],
        "confidence": fields["confidence"],
        "observed_date": fields["observed_date"],
        "source": fields["source"],
    }
    for optional in ("precision", "higher_is_better", "notes"):
        if fields.get(optional) is not None:
            entry[optional] = fields[optional]
    return entry


def derive_benchmark_id(fields: dict) -> str:
    """Derive a benchmark id from its coordinates (existing naming style)."""
    device = re.sub(r"[^a-z0-9]+", "", str(fields["device_class"]).lower())
    metric = str(fields["metric"]).replace("_", "-")
    return f"{fields['model_id']}-{device}-{str(fields['compute_unit']).lower()}-{metric}"


# ── File writing ──


def dump_entry_yaml(entry: dict) -> str:
    """Render one entry as a YAML list item matching the repo style."""
    return yaml.dump(
        [entry], default_flow_style=False, sort_keys=False, allow_unicode=True,
        width=1000,
    )


def append_yaml_entry(path: Path, entry: dict) -> str:
    """Append a list-item entry at EOF (all repo YAML lists end the file)."""
    text = path.read_text()
    block = dump_entry_yaml(entry)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + block)
    return block


def bump_artifact_count(root: Path, delta: int = 1) -> tuple[int, int]:
    """Bump artifacts.yaml metadata.count (audit category 8 requires it)."""
    path = root / "artifacts.yaml"
    text = path.read_text()
    head, sep, tail = text.partition("\nartifacts:")
    match = re.search(r"(count:\s*)(\d+)", head)
    if not match:
        raise ValueError("artifacts.yaml metadata.count not found")
    old = int(match.group(2))
    new = old + delta
    head = head[: match.start(2)] + str(new) + head[match.end(2):]
    path.write_text(head + sep + tail)
    return old, new


# ── Local gate + PR ──


def run_local_gate(root: Path) -> tuple[bool, list[str]]:
    """Run the local validation gate (validate.py + audit.py).

    Returns (ok, report_lines) — the same evidence a PR body cites.
    """
    lines: list[str] = []
    ok = True
    for script in ("scripts/validate.py", "scripts/audit.py"):
        result = subprocess.run(
            [sys.executable, script],
            cwd=str(root), capture_output=True, text=True,
        )
        status = "PASS" if result.returncode == 0 else "FAIL"
        lines.append(f"{status}: python {script}")
        output = (result.stdout + result.stderr).strip()
        if output:
            lines.extend("  " + ln for ln in output.splitlines()[-20:])
        if result.returncode != 0:
            ok = False
    return ok, lines


def open_contribution_pr(
    root: Path,
    model_id: str,
    files: list[str],
    evidence: list[str],
) -> tuple[bool, str]:
    """Create a branch, commit, push, and open a PR via gh.

    Returns (ok, message). Never force-pushes; aborts on the first failing
    step, reports it (with an auth hint for push failures), and returns the
    user to the branch they started on — committed work is preserved on the
    contribution branch.
    """
    branch = f"contribute/add-{model_id}"
    title = f"feat: add model {model_id} (via coreai-catalog contribute)"
    body = (
        f"## New model: `{model_id}`\n\n"
        "Drafted with `coreai-catalog contribute model` — entries were "
        "validated against the JSON Schemas and cross-reference rules "
        "before this PR was opened.\n\n"
        "### Files changed\n"
        + "".join(f"- `{f}`\n" for f in files)
        + "\n### Local validation evidence\n\n```\n"
        + "\n".join(evidence)
        + "\n```\n\n"
        "Model lane only — this PR does not touch `benchmarks.jsonl`.\n"
    )
    original_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(root), capture_output=True, text=True,
    ).stdout.strip()
    steps = [
        ["git", "checkout", "-b", branch],
        ["git", "add", *files],
        ["git", "commit", "-m", title],
        # gh pr create runs non-interactively here (stdout is a pipe), so the
        # branch must already exist on the remote — push before creating.
        ["git", "push", "-u", "origin", branch],
        ["gh", "pr", "create", "--title", title, "--body", body],
    ]
    for cmd in steps:
        result = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).strip()
            hint = ""
            if cmd[:2] == ["git", "push"]:
                hint = (
                    "\nhint: the push failed — check `git remote -v` and "
                    "`gh auth status` (push access / authentication). "
                    f"Your work is committed on branch '{branch}'."
                )
            # Don't strand the user on the half-done contribution branch:
            # return to the original branch (committed work stays on the
            # contribution branch; uncommitted edits survive the checkout).
            if original_branch and original_branch != branch:
                subprocess.run(
                    ["git", "checkout", original_branch],
                    cwd=str(root), capture_output=True, text=True,
                )
            return False, (
                f"step failed: {' '.join(cmd[:3])}…\n{detail}{hint}"
            )
    return True, f"PR opened from branch {branch}"


CURATOR_LANE_EXPLANATION = """\
How benchmark submission works (curator lane):
  - benchmarks.jsonl is append-only: exactly ONE added line per PR, and a
    benchmark PR must touch NOTHING else (never mix it with a model PR).
  - Signed relay submissions (Ed25519) auto-merge, but the relay is not
    yet public — you cannot complete that path today.
  - Unsigned entries with extraction_method upstream_readme_manual or
    upstream_readme_scripted go to the CURATOR REVIEW lane: CI validates
    the line, applies the benchmark-curator-review label, and a curator
    reviews provenance and merges manually. This is the normal path for
    external contributors today.
  - This command drafts and validates the line locally. It does NOT push:
    open a dedicated single-line PR against benchmarks.jsonl yourself.\
"""
