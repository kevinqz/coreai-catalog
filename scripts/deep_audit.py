#!/usr/bin/env python3
"""
Deep data-quality auditor — goes beyond audit.py.

Checks for REAL data quality issues the schema/CI audit cannot catch:
  1. Benchmark values (nulls, unrealistic, duplicates, orphan refs, unit consistency)
  2. Artifact URL format + GitHub field completeness + officiality completeness
  3. License data (empty name, bad commercial_use, check_license reason tracing)
  4. Device support logic (mac=False, contradictory mac_only+iphone, all-unknown)
  5. Size data (parameters format inconsistency, artifact_size, precision validity)
  6. Runtime data (runner values, boolean-type correctness)
  7. Upstream references (sources[], artifact_ref resolution)
  8. Terms cross-references (relations format, target resolution, URL format)
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def main() -> int:
    catalog = read_yaml(ROOT / "catalog.yaml")
    artifacts_data = read_yaml(ROOT / "artifacts.yaml")
    benchmarks_data = read_yaml(ROOT / "benchmarks.yaml")
    terms_data = read_yaml(ROOT / "terms.yaml")
    upstreams_data = read_yaml(ROOT / "upstreams.yaml")
    sources_data = read_yaml(ROOT / "sources.yaml")

    models = catalog.get("models", [])
    artifacts = artifacts_data.get("artifacts", [])
    benchmarks = benchmarks_data.get("benchmarks", [])
    terms = terms_data.get("terms", [])
    sources = sources_data.get("sources", [])

    issues: list[str] = []

    model_ids = {m["id"] for m in models}
    art_by_id = {a["id"]: a for a in artifacts}
    src_ids = {s["id"] for s in sources}
    UPSTREAM_GROUPS = [
        "framework_sources", "conversion_sources", "artifact_hosts",
        "benchmark_sources", "sample_sources", "original_model_sources",
        "license_sources",
    ]
    all_upstreams: list[dict] = []
    for g in UPSTREAM_GROUPS:
        all_upstreams.extend(upstreams_data.get(g, []) or [])
    up_ids = {u["id"] for u in all_upstreams}
    model_by_id = {m["id"]: m for m in models}

    # ════════════════════════════════════════════════════════════════════
    # 1. BENCHMARK VALUES
    # ════════════════════════════════════════════════════════════════════
    BENCH_CRITICAL = ["value", "unit", "metric", "device"]
    for b in benchmarks:
        for f in BENCH_CRITICAL:
            v = b.get(f)
            if v is None or v == "null":
                issues.append(f"[BENCH] {b['id']} field '{f}' is null/None")

        # unrealistic values
        val = b.get("value")
        metric = b.get("metric", "")
        unit = b.get("unit", "")
        if isinstance(val, (int, float)):
            if val < 0:
                issues.append(f"[BENCH] {b['id']} value={val} is negative")
            if "throughput" in metric and "tokens_per_second" in unit and val > 10000:
                issues.append(f"[BENCH] {b['id']} throughput={val} tok/s unrealistically high (>10000)")
            if "latency" in metric and unit in ("seconds", "milliseconds") and val > 600:
                issues.append(f"[BENCH] {b['id']} latency={val}{unit} unrealistically high (>600)")
            if "realtime_factor" in metric and val > 100:
                issues.append(f"[BENCH] {b['id']} realtime_factor={val} unrealistically high (>100)")

    # duplicate benchmark records (same model_id + metric + device + compute_unit + precision)
    # Exclude legitimate supersede chains (one has superseded_by pointing to the other)
    seen_keys: dict[str, list[str]] = defaultdict(list)
    for b in benchmarks:
        key = f"{b.get('model_id')}|{b.get('metric')}|{b.get('device')}|{b.get('compute_unit')}|{b.get('precision')}"
        seen_keys[key].append(b["id"])
    for key, ids in seen_keys.items():
        if len(ids) > 1:
            # Check if this is a legit supersede chain
            bm_by_id = {b["id"]: b for b in benchmarks}
            is_supersede = False
            for bid in ids:
                if bm_by_id[bid].get("superseded_by") in ids:
                    is_supersede = True
            if not is_supersede:
                issues.append(
                    f"[BENCH] duplicate key (model|metric|device|unit|precision): "
                    f"{key} → ids={ids}"
                )

    # benchmark records referencing models that don't exist
    for b in benchmarks:
        if b.get("model_id") not in model_ids:
            issues.append(f"[BENCH] {b['id']} references unknown model_id='{b.get('model_id')}'")

    # inconsistent units for same metric across models
    metric_units: dict[str, set[str]] = defaultdict(set)
    for b in benchmarks:
        metric_units[b.get("metric", "")].add(b.get("unit", ""))
    for metric, units in metric_units.items():
        if len(units) > 1:
            issues.append(f"[BENCH] metric '{metric}' has inconsistent units: {sorted(units)}")

    # benchmark precision = unknown
    for b in benchmarks:
        if b.get("precision") == "unknown":
            issues.append(f"[BENCH] {b['id']} precision='unknown' (should be extracted or not_published)")

    # ════════════════════════════════════════════════════════════════════
    # 2. ARTIFACT URLs
    # ════════════════════════════════════════════════════════════════════
    hf_url_re = re.compile(r"^https://huggingface\.co/[A-Za-z0-9._\-]+/[A-Za-z0-9._\-]+(/.*)?$")
    for a in artifacts:
        hf = a.get("huggingface", {}) or {}
        url = hf.get("url", "")
        owner = hf.get("owner", "")
        repo = hf.get("repo", "")

        # Check format validity
        if url and url != "unknown":
            if not hf_url_re.match(url):
                issues.append(f"[ARTIFACT] {a['id']} HF URL malformed: '{url}'")
            # Check URL matches owner/repo
            expected_prefix = f"https://huggingface.co/{owner}/{repo}"
            if url and not url.startswith(expected_prefix):
                issues.append(
                    f"[ARTIFACT] {a['id']} HF URL '{url}' doesn't match owner={owner}/repo={repo}"
                )

        # Check for typos / suspicious patterns in repo names
        if repo:
            if "  " in repo:  # double space
                issues.append(f"[ARTIFACT] {a['id']} repo='{repo}' has double-space (likely typo)")
            if repo != repo.strip():
                issues.append(f"[ARTIFACT] {a['id']} repo='{repo}' has leading/trailing whitespace")

        # GitHub owner/repo presence
        gh = a.get("github", {}) or {}
        if not gh.get("owner"):
            issues.append(f"[ARTIFACT] {a['id']} github.owner missing/empty")
        if not gh.get("repo"):
            issues.append(f"[ARTIFACT] {a['id']} github.repo missing/empty")

        # GitHub path should be a GitHub URL (not HF), if present
        gpath = gh.get("path", "")
        if gpath and gpath.startswith("https://huggingface.co/"):
            issues.append(
                f"[ARTIFACT] {a['id']} github.path='{gpath}' is a HuggingFace URL "
                f"(should be a GitHub URL or omitted)"
            )

        # Officiality block completeness (all 3 fields)
        off = a.get("officiality", {}) or {}
        for f in ["apple_export_recipe", "apple_hosted_artifact", "community_packaged"]:
            if f not in off or off.get(f) is None:
                issues.append(f"[ARTIFACT] {a['id']} officiality.{f} missing/null")

    # ════════════════════════════════════════════════════════════════════
    # 3. LICENSE DATA
    # ════════════════════════════════════════════════════════════════════
    for m in models:
        lic = m.get("license", {}) or {}
        name = lic.get("name", "")
        if not name or name == "unknown":
            issues.append(f"[LICENSE] model {m['id']} license.name empty/unknown")

        cu = lic.get("commercial_use", "")
        if cu not in ("likely", "check_license"):
            issues.append(f"[LICENSE] model {m['id']} commercial_use='{cu}' (expected likely/check_license)")

    # Cross-reference: do check_license models have a reason in upstream?
    # Build map of model_id → upstream license_source review_required
    license_sources = upstreams_data.get("license_sources", []) or []
    lic_src_by_id = {ls["id"]: ls for ls in license_sources}

    # Build applies_to index from original_model_sources
    orig_sources = upstreams_data.get("original_model_sources", []) or []
    model_to_orig = defaultdict(list)
    for o in orig_sources:
        for t in o.get("applies_to", []) or []:
            model_to_orig[t].append(o)

    for m in models:
        if m.get("license", {}).get("commercial_use") == "check_license":
            # Check upstream has needs_review or review_required
            origs = model_to_orig.get(m["id"], [])
            if not origs:
                issues.append(
                    f"[LICENSE] model {m['id']} is check_license but has no original_model_source upstream"
                )

    # ════════════════════════════════════════════════════════════════════
    # 4. DEVICE SUPPORT LOGIC
    # ════════════════════════════════════════════════════════════════════
    for m in models:
        ds = m.get("device_support", {}) or {}
        mac = ds.get("mac")
        iphone = ds.get("iphone")
        mac_only = ds.get("mac_only")
        ipad = ds.get("ipad")

        if mac is False:
            issues.append(f"[DEVICE] model {m['id']} mac=False (all models should run on Mac)")

        if mac_only is True and iphone is True:
            issues.append(
                f"[DEVICE] model {m['id']} contradictory: mac_only=True but iphone=True"
            )

        if all(v == "unknown" for v in [mac, iphone, ipad, mac_only]):
            issues.append(f"[DEVICE] model {m['id']} ALL device fields are 'unknown'")

    # ════════════════════════════════════════════════════════════════════
    # 5. SIZE DATA
    # ════════════════════════════════════════════════════════════════════
    VALID_PRECISIONS = {
        "fp32", "fp16", "bf16", "fp8", "fp6", "fp4",
        "int8", "int4", "int2",
        "mxfp4", "mxfp6", "mxfp8", "MXFP4", "MXFP6", "MXFP8",
        "1.58-bit ternary",
        "not_published",
    }
    # Standard parameters format: should be like "2B", "0.8B", "350M", or numeric+B/M
    param_re = re.compile(r"^\d+(\.\d+)?[BM]$")

    for m in models:
        size = m.get("size", {}) or {}
        params = size.get("parameters", "")
        prec = size.get("precision", "")
        asize = size.get("artifact_size", "")

        # precision validity
        if prec and prec != "unknown" and prec not in VALID_PRECISIONS:
            issues.append(f"[SIZE] model {m['id']} precision='{prec}' not a recognized ML precision")

        # parameters format consistency
        if params and params != "not_published" and params != "unknown":
            # Check for lowercase 'b' or 'm' instead of uppercase
            if re.search(r"\d[bm](\s|$|/)", params) and not re.search(r"\d[BM](\s|$|/)", params):
                issues.append(f"[SIZE] model {m['id']} parameters='{params}' uses lowercase b/m (inconsistent)")

            # Check for raw numbers without B/M suffix
            if re.match(r"^\d+$", str(params)):
                issues.append(f"[SIZE] model {m['id']} parameters='{params}' raw number without B/M suffix")

            # Check for non-standard formats (not a recognized param pattern)
            if not param_re.match(str(params)):
                # Some are intentionally descriptive (MoE active params, etc.) — flag for review
                if not any(x in str(params).lower() for x in ["active", "ternary", "dit", "bitnet"]):
                    if str(params) not in ("not_published", "unknown"):
                        issues.append(
                            f"[SIZE] model {m['id']} parameters='{params}' non-standard format "
                            f"(expected e.g. '2B', '350M')"
                        )

        # artifact_size format
        if asize and asize not in ("not_published", "unknown"):
            if not re.match(r"^[\d.]+[KMGT]?B$", str(asize)):
                issues.append(f"[SIZE] model {m['id']} artifact_size='{asize}' non-standard format")

    # ════════════════════════════════════════════════════════════════════
    # 6. RUNTIME DATA
    # ════════════════════════════════════════════════════════════════════
    KNOWN_RUNNERS = {
        "CoreAIRunner", "CoreAIDiffusionPipeline", "CoreAIImageSegmenter",
        "CoreAITranscribe", "CoreAIVideoPipeline", "CoreAIKit-GraphModel",
        "stock-runner", "not_applicable",
    }
    BOOL_FIELDS = ["stock_runtime", "custom_kernel", "patch_required", "aot_required"]

    all_runners = set()
    for m in models:
        rt = m.get("runtime", {}) or {}
        runner = rt.get("runner")
        all_runners.add(runner)
        if runner and runner not in KNOWN_RUNNERS:
            issues.append(f"[RUNTIME] model {m['id']} runner='{runner}' unexpected value")

        for bf in BOOL_FIELDS:
            v = rt.get(bf)
            if v is None:
                issues.append(f"[RUNTIME] model {m['id']} runtime.{bf} is null/None")
            elif not isinstance(v, bool):
                issues.append(f"[RUNTIME] model {m['id']} runtime.{bf}={v!r} is not boolean (type={type(v).__name__})")

    # ════════════════════════════════════════════════════════════════════
    # 7. UPSTREAM REFERENCES
    # ════════════════════════════════════════════════════════════════════
    for m in models:
        ref = m.get("artifact_ref")
        if ref not in art_by_id:
            issues.append(f"[UPSTREAM] model {m['id']} artifact_ref='{ref}' not found in artifacts.yaml")

        for s in m.get("sources", []) or []:
            if s not in src_ids and s not in up_ids:
                issues.append(f"[UPSTREAM] model {m['id']} source='{s}' not found in sources.yaml or upstreams.yaml")

    # ════════════════════════════════════════════════════════════════════
    # 8. TERMS CROSS-REFERENCES
    # ════════════════════════════════════════════════════════════════════
    term_ids = {t["id"] for t in terms}
    url_re = re.compile(r"^https?://[^\s]+$")

    for t in terms:
        for rel in t.get("relations", []) or []:
            parts = rel.split(":", 1)
            if len(parts) != 2:
                issues.append(f"[TERMS] term {t['id']} malformed relation '{rel}' (expected 'type:target')")
                continue
            rel_type, target = parts
            if not rel_type:
                issues.append(f"[TERMS] term {t['id']} relation '{rel}' has empty relation_type")
            if target not in term_ids:
                issues.append(f"[TERMS] term {t['id']} relation target '{target}' is not a known term")

        osrc = t.get("official_source", "")
        if osrc and osrc != "unknown":
            if not url_re.match(osrc):
                issues.append(f"[TERMS] term {t['id']} official_source='{osrc}' invalid URL format")
        elif not osrc:
            issues.append(f"[TERMS] term {t['id']} official_source missing/empty")

    # ════════════════════════════════════════════════════════════════════
    # OUTPUT
    # ════════════════════════════════════════════════════════════════════
    # Group issues by category for readability
    by_cat: dict[str, list[str]] = defaultdict(list)
    for iss in issues:
        cat = iss.split("]")[0].strip("[").strip()
        by_cat[cat].append(iss)

    if issues:
        print(f"\n{'='*70}")
        print(f"DEEP AUDIT: {len(issues)} issue(s) found across {len(by_cat)} categories")
        print(f"{'='*70}\n")
        for cat in sorted(by_cat.keys()):
            cat_issues = by_cat[cat]
            print(f"── {cat} ({len(cat_issues)} issue(s)) ──")
            for iss in sorted(cat_issues):
                # Print just the detail part after [CAT]
                detail = iss.split("]", 1)[1].strip() if "]" in iss else iss
                print(f"  • {detail}")
            print()
        print(f"TOTAL: {len(issues)} issue(s)")
        return 1

    print(f"OK: 0 deep-audit issues across {len(models)} models, {len(artifacts)} artifacts, "
          f"{len(benchmarks)} benchmarks, {len(terms)} terms.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
