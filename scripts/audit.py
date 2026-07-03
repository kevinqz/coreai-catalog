#!/usr/bin/env python3
"""
Catalog data-quality auditor.

Runs the full 11-category cross-check against the catalog sources
(YAML entities + benchmarks.jsonl) and exits non-zero if any issue is
found. Designed for CI: fast, deterministic, no network calls, clear
output.

Categories:
  1. Duplicate IDs (models, artifacts, benchmarks.jsonl, terms)
  2. Cross-reference integrity (artifact_ref, model_id, source IDs)
  3. Upstream applies_to validity
  4. Hugging Face URL consistency
  5. Zero unknown fields (precision, quantization, runtime flags, etc)
  6. Officiality logic (source_group ↔ apple_export_recipe)
  7. Term relation integrity
  8. Metadata count accuracy
  9. Date format validation + capability ↔ modality sanity
 10. License ↔ upstream consistency (permissive claims over restricted
     upstreams; unverified upstreams must not claim permissive terms)
 11. Retired-store guard (benchmarks.yaml must not reappear — JSONL is the
     single benchmark source of truth)
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

#: Upstream license_terms values that are incompatible with a model claiming
#: a permissive license + likely commercial use.
NON_PERMISSIVE_LICENSE_TERMS = {"restricted", "review_required"}

#: model.source_group → artifact.group pairings allowed beyond identity.
#: The artifact group enum (schema/artifact.schema.json) has no 'fabric';
#: coreai-fabric conversions are independent/external artifacts, so a
#: fabric model pairs with an external artifact (the same mapping applied
#: by coreai_catalog/contribute.py build_artifact_entry and by
#: coreai-fabric's register command).
ALLOWED_GROUP_PAIRINGS = {"fabric": {"external"}}


def group_pairing_ok(source_group: str, artifact_group: str) -> bool:
    """True when a model's source_group may pair with an artifact's group."""
    if artifact_group == source_group:
        return True
    return artifact_group in ALLOWED_GROUP_PAIRINGS.get(source_group, set())


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def read_benchmarks_jsonl(path: Path) -> list[dict]:
    """Read benchmarks.jsonl (single benchmark source of truth)."""
    benchmarks: list[dict] = []
    if not path.exists():
        return benchmarks
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        benchmarks.append(json.loads(line))
    return benchmarks


def main() -> int:
    catalog = read_yaml(ROOT / "catalog.yaml")
    artifacts_data = read_yaml(ROOT / "artifacts.yaml")
    terms_data = read_yaml(ROOT / "terms.yaml")
    upstreams_data = read_yaml(ROOT / "upstreams.yaml")
    sources_data = read_yaml(ROOT / "sources.yaml")

    models = catalog.get("models", [])
    artifacts = artifacts_data.get("artifacts", [])
    benchmarks = read_benchmarks_jsonl(ROOT / "benchmarks.jsonl")
    terms = terms_data.get("terms", [])
    sources = sources_data.get("sources", [])

    issues: list[str] = []

    # ── 1. Duplicate IDs ──
    for items, label in [
        (models, "model"),
        (artifacts, "artifact"),
        (benchmarks, "benchmark"),
        (terms, "term"),
    ]:
        ids = [i["id"] for i in items]
        dups = [x for x, c in Counter(ids).items() if c > 1]
        if dups:
            issues.append(f"Duplicate {label} IDs: {dups}")

    # ── 2. Cross-reference integrity ──
    model_ids = {m["id"] for m in models}
    art_by_id = {a["id"]: a for a in artifacts}
    src_ids = {s["id"] for s in sources}

    UPSTREAM_GROUPS = [
        "framework_sources",
        "conversion_sources",
        "artifact_hosts",
        "benchmark_sources",
        "sample_sources",
        "original_model_sources",
        "license_sources",
    ]
    all_upstreams: list[dict] = []
    for g in UPSTREAM_GROUPS:
        all_upstreams.extend(upstreams_data.get(g, []) or [])
    up_ids = {u["id"] for u in all_upstreams}

    for m in models:
        ref = m.get("artifact_ref")
        if ref not in art_by_id:
            issues.append(f"model {m['id']} → missing artifact_ref '{ref}'")
        elif not group_pairing_ok(m["source_group"], art_by_id[ref].get("group")):
            issues.append(
                f"model {m['id']} source_group={m['source_group']} "
                f"vs artifact group={art_by_id[ref].get('group')}"
            )
        for s in m.get("sources", []):
            if s not in src_ids and s not in up_ids:
                issues.append(f"model {m['id']} → missing source '{s}'")

    for b in benchmarks:
        if b["model_id"] not in model_ids:
            issues.append(f"benchmark {b['id']} → missing model_id '{b['model_id']}'")
        if b["source"] not in src_ids and b["source"] not in up_ids:
            issues.append(f"benchmark {b['id']} → missing source '{b['source']}'")

    # ── 3. Upstream applies_to ──
    for u in upstreams_data.get("original_model_sources", []) or []:
        for t in u.get("applies_to", []) or []:
            if t not in model_ids:
                issues.append(
                    f"upstream {u['id']} applies_to '{t}' → not a known model ID"
                )

    # ── 4. HF URL consistency ──
    for a in artifacts:
        hf = a.get("huggingface", {}) or {}
        url = hf.get("url", "")
        owner = hf.get("owner", "")
        repo = hf.get("repo", "")
        path = hf.get("path")
        expected = f"https://huggingface.co/{owner}/{repo}"
        if path:
            expected = f"{expected}/{path}"
        if url and url != expected:
            issues.append(
                f"artifact {a['id']} URL mismatch: '{url}' != '{expected}'"
            )

    # ── 5. Zero unknown fields ──
    critical_fields = [
        ("size", "precision"),
        ("size", "quantization"),
        ("size", "artifact_size"),
        ("runtime", "stock_runtime"),
        ("runtime", "custom_kernel"),
        ("runtime", "patch_required"),
        ("runtime", "aot_required"),
    ]
    for m in models:
        for section, field in critical_fields:
            val = m.get(section, {}).get(field)
            if val == "unknown":
                issues.append(
                    f"model {m['id']} has unknown: {section}.{field} "
                    "(extract from upstream card or mark 'not_published')"
                )

    # ── 6. Officiality logic ──
    for m in models:
        a = art_by_id.get(m.get("artifact_ref"))
        if a:
            off = a.get("officiality", {}) or {}
            if m["source_group"] == "official" and not off.get("apple_export_recipe"):
                issues.append(
                    f"model {m['id']} is official but apple_export_recipe=False"
                )
            if m["source_group"] == "zoo" and off.get("apple_export_recipe"):
                issues.append(
                    f"model {m['id']} is zoo but apple_export_recipe=True"
                )
            if m["source_group"] == "fabric" and off.get("apple_export_recipe"):
                issues.append(
                    f"model {m['id']} is fabric but apple_export_recipe=True"
                )
            if off.get("apple_hosted_artifact"):
                issues.append(
                    f"artifact {a['id']} claims apple_hosted_artifact=True "
                    "(all current entries should be False)"
                )

    # ── 7. Term relation integrity ──
    term_ids = {t["id"] for t in terms}
    for t in terms:
        for rel in t.get("relations", []) or []:
            parts = rel.split(":")
            if len(parts) != 2:
                issues.append(f"term {t['id']} malformed relation '{rel}'")
                continue
            target = parts[1]
            if target not in term_ids:
                issues.append(
                    f"term {t['id']} relation → '{target}' is not a known term"
                )

    # ── 8. Metadata count accuracy ──
    # (benchmarks.jsonl carries no metadata block — nothing to cross-check)
    for fname, data_key in [("artifacts", "artifacts")]:
        data = read_yaml(ROOT / f"{fname}.yaml")
        meta_count = data.get("metadata", {}).get("count")
        actual = len(data.get(data_key, []))
        if meta_count is not None and meta_count != actual:
            issues.append(
                f"{fname}.yaml metadata.count={meta_count} but actual={actual}"
            )

    # ── 9. Date format + capability ↔ modality sanity ──
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for m in models:
        lv = m.get("last_verified", "")
        if lv and not date_re.match(lv):
            issues.append(f"model {m['id']} bad date '{lv}'")
        caps = set(m.get("capabilities", []))
        inp = set(m.get("modalities", {}).get("input", []))
        out = set(m.get("modalities", {}).get("output", []))
        vision_caps = {
            "vision-language", "object-detection", "instance-segmentation",
            "promptable-segmentation", "monocular-depth", "super-resolution",
            "document-ocr", "visual-document-retrieval", "image-to-3d",
            "image-text-similarity", "gui-grounding",
        }
        if caps & vision_caps and "image" not in inp:
            issues.append(f"model {m['id']} has vision capability but no image input")
        if "text-to-speech" in caps and "audio" not in out:
            issues.append(f"model {m['id']} is TTS but no audio output")
        if "text-to-video" in caps and "video" not in out:
            issues.append(f"model {m['id']} is text-to-video but no video output")

    for b in benchmarks:
        obs = b.get("observed_date", "")
        if not obs:
            issues.append(f"benchmark {b['id']} missing observed_date")
        elif not date_re.match(obs):
            issues.append(f"benchmark {b['id']} bad date '{obs}'")

    # ── 10. License ↔ upstream consistency ──
    # Join each model to its original_model_sources upstream(s) via
    # applies_to and compare the model's declared license posture with
    # the upstream's license_terms. A model must not claim likely
    # commercial use while its upstream license family is restricted or
    # review_required (license laundering guard).
    model_to_upstreams: dict[str, list[dict]] = {}
    for u in upstreams_data.get("original_model_sources", []) or []:
        for t in u.get("applies_to", []) or []:
            model_to_upstreams.setdefault(t, []).append(u)
        # An upstream whose identity is itself unverified cannot ground a
        # 'permissive' license claim (schema rule: license_terms must be
        # grounded in verified license strings; conservative default is
        # review_required).
        if (
            u.get("license_terms") == "permissive"
            and (u.get("trust") == "needs_review" or u.get("owner") == "unknown")
        ):
            issues.append(
                f"upstream {u['id']} has trust={u.get('trust')} / "
                f"owner={u.get('owner')} but license_terms=permissive — "
                "unverified upstreams must stay review_required until the "
                "upstream identity and license are verified"
            )

    for m in models:
        commercial_use = m.get("license", {}).get("commercial_use")
        for u in model_to_upstreams.get(m["id"], []):
            terms_val = u.get("license_terms")
            if commercial_use == "likely" and terms_val in NON_PERMISSIVE_LICENSE_TERMS:
                issues.append(
                    f"model {m['id']} claims commercial_use=likely "
                    f"(license '{m.get('license', {}).get('name')}') but upstream "
                    f"{u['id']} has license_terms={terms_val} — "
                    "set commercial_use: check_license or fix the upstream record"
                )

    # ── 11. Retired-store guard ──
    # benchmarks.jsonl is the single benchmark source of truth. The legacy
    # YAML store was retired; if it reappears, exports/docs/audits would
    # silently drift apart again.
    for retired in (ROOT / "benchmarks.yaml",
                    ROOT / "coreai_catalog" / "data" / "benchmarks.yaml"):
        if retired.exists():
            issues.append(
                f"{retired.relative_to(ROOT)} exists but is retired — "
                "benchmarks.jsonl is the single benchmark store; delete the YAML file"
            )
    if not (ROOT / "benchmarks.jsonl").exists():
        issues.append("benchmarks.jsonl is missing (single benchmark source of truth)")

    # ── Output ──
    if issues:
        print(f"\n❌ {len(issues)} issue(s) found:\n")
        for issue in sorted(issues):
            print(f"  {issue}")
        print(f"\nTotal: {len(issues)} issue(s)")
        return 1

    print(
        f"OK: 0 issues across {len(models)} models, {len(artifacts)} artifacts, "
        f"{len(benchmarks)} benchmarks, {len(terms)} terms, {len(all_upstreams)} upstreams."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
