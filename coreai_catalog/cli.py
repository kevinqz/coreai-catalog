#!/usr/bin/env python3
"""
Core AI Catalog CLI — the easiest way to discover, verify, and install
Apple Core AI models.

Usage:
  coreai-catalog search --capability vision-language --device iphone
  coreai-catalog show qwen3-vl-2b
  coreai-catalog list
  coreai-catalog scores
  coreai-catalog compare qwen3-vl-2b gemma-4-e2b-vision
  coreai-catalog recommend --task "robot vision" --device iphone
  coreai-catalog install qwen3-vl-2b
  coreai-catalog doctor
  coreai-catalog publish --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .catalog import Catalog, resolve_task, _parse_params
from .formatters import (
    build_task_capability_entries,
    count_capabilities,
    extract_device_list,
    extract_device_unknown,
    get_catalog_last_verified,
    get_catalog_version,
    reshape_benchmark,
)
from .installer import (
    get_model_dir,
    install_model,
    is_installed,
    list_installed,
    uninstall_model,
)
from .publish import (
    PreflightError,
    bump_all_version_surfaces,
    build_dist,
    git_commit_and_tag,
    git_push,
    run_preflight_checks,
    suggest_next_version,
    upload_to_pypi,
    validate_version,
)


# ── Formatting helpers ──

#: Detect if stdout is a TTY. When not a TTY (piped to file), disable colors.
_IS_TTY = sys.stdout.isatty()

BOLD = "\033[1m" if _IS_TTY else ""
DIM = "\033[2m" if _IS_TTY else ""
GREEN = "\033[32m" if _IS_TTY else ""
YELLOW = "\033[33m" if _IS_TTY else ""
BLUE = "\033[34m" if _IS_TTY else ""
RED = "\033[31m" if _IS_TTY else ""
RESET = "\033[0m" if _IS_TTY else ""


def _fmt_devices(ds: dict) -> str:
    parts = []
    if ds.get("iphone") is True:
        parts.append("iPhone")
    if ds.get("ipad") is True:
        parts.append("iPad")
    if ds.get("mac") is True:
        parts.append("Mac")
    if ds.get("mac_only") is True:
        parts.append("Mac-only")
    return "/".join(parts) if parts else "unknown"


def _fmt_license(lic: dict) -> str:
    name = lic.get("name", "unknown")
    cu = lic.get("commercial_use", "")
    icon = f"{GREEN}✅{RESET}" if cu == "likely" else f"{YELLOW}⚠️ {RESET}"
    return f"{icon} {name}"


def _fmt_score(score: int) -> str:
    if score >= 85:
        return f"{GREEN}{score} (A){RESET}"
    elif score >= 70:
        return f"{GREEN}{score} (B){RESET}"
    elif score >= 55:
        return f"{YELLOW}{score} (C){RESET}"
    elif score >= 40:
        return f"{YELLOW}{score} (D){RESET}"
    return f"{RED}{score} (F){RESET}"


def _fmt_source(model: dict) -> str:
    sg = model.get("source_group", "")
    if sg == "official":
        return f"{BLUE}🍎 Apple recipe{RESET}"
    elif sg == "external":
        return f"{BLUE}🔗 Independent{RESET}"
    elif sg == "zoo":
        return f"{BLUE}🐼 Zoo{RESET}"
    return sg


def _format_model_compact(cat: Catalog, model: dict) -> str:
    """One-line model summary for lists."""
    ds = model.get("device_support", {})
    has_bench = "📊" if cat.get_benchmarks(model["id"]) else "  "
    score = cat.readiness_score(model)
    devices = []
    if ds.get("iphone") is True:
        devices.append("📱")
    if ds.get("mac") is True:
        devices.append("💻")
    return (
        f"  {model['id']:40s}  {''.join(devices)} {has_bench} "
        f"{_fmt_score(score)}  {model['name']}"
    )


# ── Commands ──


def cmd_search(args: argparse.Namespace) -> int:
    cat = Catalog()
    results = cat.search(
        capability=args.capability,
        device=args.device,
        license_type=args.license,
        family=args.family,
        source_group=args.source_group,
        modality=args.modality,
    )

    if not results:
        if args.json:
            print(json.dumps({"count": 0, "total_matches": 0,
                              "truncated": False, "models": []}, indent=2))
            return 0
        print(f"\n  {DIM}No models match the given filters.{RESET}")
        # Provide valid-value hints for filters that may have been set
        if args.device:
            valid = sorted({d for m in cat.models
                            for d, v in m.get("device_support", {}).items()
                            if v is True})
            print(f"  {DIM}Valid devices: {', '.join(valid)}{RESET}")
        if args.source_group:
            valid = sorted({sg for m in cat.models
                            if (sg := m.get("source_group"))})
            print(f"  {DIM}Valid source groups: {', '.join(valid)}{RESET}")
        if args.license:
            valid = sorted({cu for m in cat.models
                            if (cu := m.get("license", {}).get("commercial_use"))})
            print(f"  {DIM}Valid license values: {', '.join(valid)}{RESET}")
        if args.capability:
            valid = sorted({c for m in cat.models
                            for c in m.get("capabilities", [])})
            print(f"  {DIM}Valid capabilities: {', '.join(valid)}{RESET}")
        if args.family:
            valid = sorted({f for m in cat.models if (f := m.get("family"))})
            print(f"  {DIM}Valid families: {', '.join(valid)}{RESET}")
        return 0

    if args.json:
        enriched = []
        for m in results:
            ds = m.get("device_support", {})
            devices = extract_device_list(ds)
            devices_unknown = extract_device_unknown(ds) or None
            # Artifact URL for direct download
            art = cat.get_artifact(m["id"])
            hf_url = ""
            if art:
                hf_url = art.get("huggingface", {}).get("url", "")
            enriched.append({
                "id": m["id"],
                "name": m["name"],
                "family": m["family"],
                "capabilities": m.get("capabilities", []),
                "devices": devices,
                "devices_unknown": devices_unknown,
                "parameters": m.get("size", {}).get("parameters"),
                "license": m.get("license", {}).get("name"),
                "commercial_use": m.get("license", {}).get("commercial_use"),
                "readiness_score": cat.readiness_score(m),
                "has_benchmark": bool(cat.get_benchmarks(m["id"])),
                "artifact_url": hf_url,
                "source_group": m.get("source_group"),
            })
        print(json.dumps({"count": len(enriched), "total_matches": len(enriched),
                          "truncated": False, "models": enriched}, indent=2))
        return 0

    print(f"\n  {BOLD}Found {len(results)} model(s){RESET}\n")
    for m in results:
        print(_format_model_compact(cat, m))

    filters = []
    if args.capability:
        filters.append(f"capability={args.capability}")
    if args.device:
        filters.append(f"device={args.device}")
    if args.license:
        filters.append(f"license={args.license}")
    if args.family:
        filters.append(f"family={args.family}")
    if args.source_group:
        filters.append(f"source={args.source_group}")
    if args.modality:
        filters.append(f"modality={args.modality}")
    print(f"\n  {DIM}Filters: {', '.join(filters) if filters else '(none)'}{RESET}")
    print(f"  {DIM}Next: coreai-catalog show <model-id>{RESET}\n")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    cat = Catalog()
    model = cat.get_model(args.model_id)

    if not model:
        if args.json:
            print(json.dumps({"error": f"Model '{args.model_id}' not found"}, indent=2))
            return 1
        print(f"\n  {RED}Model '{args.model_id}' not found.{RESET}")
        print(f"  {DIM}Try: coreai-catalog search --capability chat{RESET}")
        return 1

    art = cat.get_artifact(model["id"])
    benchmarks = cat.get_benchmarks(model["id"])
    score = cat.readiness_score(model)
    installed = is_installed(model["id"])

    # JSON output — aligned with MCP get_model schema
    if args.json:
        result = {
            "id": model["id"],
            "name": model["name"],
            "family": model.get("family"),
            "source_group": model.get("source_group"),
            "capabilities": model.get("capabilities", []),
            "modalities": model.get("modalities", {}),
            "size": model.get("size", {}),
            "runtime": model.get("runtime", {}),
            "device_support": model.get("device_support", {}),
            "license": model.get("license", {}),
            "status": model.get("status"),
            "maturity": model.get("maturity"),
            "confidence": model.get("confidence"),
            "readiness_score": score,
            "artifact": model.get("artifact", {}),
            "provenance": {},
            "benchmarks": [],
            "notes": model.get("notes"),
            "last_verified": model.get("last_verified"),
        }
        if art:
            result["provenance"] = {
                "github": art.get("github", {}),
                "huggingface": art.get("huggingface", {}),
                "officiality": art.get("officiality", {}),
            }
        for b in benchmarks:
            result["benchmarks"].append(reshape_benchmark(b, include_extras=False))
        print(json.dumps(result, indent=2))
        return 0

    mid = model["id"]
    print(f"\n  {BOLD}{model['name']}{RESET}")
    print(f"  {'─' * 60}")
    print(f"  ID:       {mid}")
    print(f"  Family:   {model.get('family', '?')}")
    print(f"  Source:   {_fmt_source(model)}")
    print(f"  Score:    {_fmt_score(score)}")
    if installed:
        print(f"  Status:   {GREEN}📦 Installed{RESET}")
    print()

    # Capabilities
    caps = model.get("capabilities", [])
    if caps:
        print(f"  {BOLD}Capabilities:{RESET} {', '.join(caps)}")

    # Modalities
    mod = model.get("modalities", {})
    inp = ", ".join(mod.get("input", []))
    out = ", ".join(mod.get("output", []))
    print(f"  {BOLD}Input:{RESET}      {inp}")
    print(f"  {BOLD}Output:{RESET}     {out}")

    # Device support
    print(f"  {BOLD}Devices:{RESET}    {_fmt_devices(model.get('device_support', {}))}")

    # Size
    size = model.get("size", {})
    print(f"  {BOLD}Size:{RESET}       {size.get('parameters', '?')} · {size.get('precision', '?')} · {size.get('quantization', '?')}")
    print(f"  {BOLD}Artifact:{RESET}   {size.get('artifact_size', '?')}")

    # Runtime
    rt = model.get("runtime", {})
    print(f"  {BOLD}Runtime:{RESET}    {rt.get('runner', '?')}")
    flags = []
    if rt.get("stock_runtime") is True:
        flags.append("stock runtime")
    if rt.get("custom_kernel") is True:
        flags.append(f"{YELLOW}custom kernel{RESET}")
    if rt.get("patch_required") is True:
        flags.append(f"{YELLOW}patch required{RESET}")
    if rt.get("aot_required") is True:
        flags.append(f"{YELLOW}AOT required{RESET}")
    if rt.get("tokenizer_required") is True:
        flags.append("tokenizer")
    if rt.get("processor_required") is True:
        flags.append("processor")
    if flags:
        print(f"  {BOLD}Flags:{RESET}      {' · '.join(flags)}")

    # License
    print(f"  {BOLD}License:{RESET}    {_fmt_license(model.get('license', {}))}")

    # Artifact provenance
    if art:
        hf = art.get("huggingface", {}) or {}
        off = art.get("officiality", {}) or {}
        print(f"\n  {BOLD}Provenance:{RESET}")
        print(f"    HF:        {hf.get('url', '?')}")
        gh = art.get("github", {}) or {}
        if gh.get("owner"):
            print(f"    GitHub:    {gh.get('owner', '')}/{gh.get('repo', '')}")
        print(f"    Recipe:    {'Apple official' if off.get('apple_export_recipe') else 'Community'}")
        print(f"    Hosted by Apple: {'Yes' if off.get('apple_hosted_artifact') else 'No'}")

    # Benchmarks
    if benchmarks:
        print(f"\n  {BOLD}Benchmarks:{RESET}")
        for b in benchmarks[:5]:
            val = b.get("value")
            unit = b.get("unit", "")
            dev = b.get("device", "?")
            cu = b.get("compute_unit", "")
            print(f"    {val} {unit:20s}  {dev} · {cu}")

    # Notes
    notes = model.get("notes")
    if notes:
        if args.verbose:
            print(f"\n  {DIM}Note: {notes}{RESET}")
        else:
            note = notes[:150].replace("\n", " ")
            if len(notes) > 150:
                note += "…"
            print(f"\n  {DIM}Note: {note}{RESET}")

    # Actions
    print(f"\n  {BOLD}Actions:{RESET}")
    if not installed:
        print(f"    {GREEN}coreai-catalog install {mid}{RESET}")
    else:
        print(f"    {YELLOW}coreai-catalog uninstall {mid}{RESET}")
    print(f"    coreai-catalog compare {mid} <other-model>")

    if art:
        hf = art.get("huggingface", {})
        if hf.get("url"):
            print(f"    {DIM}Download: {hf['url']}{RESET}")
    print()
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    cat = Catalog()
    models = cat.models

    if args.capability:
        models = [m for m in models if args.capability.lower()
                  in [c.lower() for c in m.get("capabilities", [])]]

    models.sort(key=lambda m: cat.readiness_score(m), reverse=True)

    if args.json:
        results = []
        for m in models:
            ds = m.get("device_support", {})
            devices = extract_device_list(ds)
            devices_unknown = extract_device_unknown(ds) or None
            art = cat.get_artifact(m["id"])
            hf_url = ""
            if art:
                hf_url = art.get("huggingface", {}).get("url", "")
            results.append({
                "id": m["id"],
                "name": m["name"],
                "family": m.get("family"),
                "capabilities": m.get("capabilities", []),
                "devices": devices,
                "devices_unknown": devices_unknown,
                "parameters": m.get("size", {}).get("parameters"),
                "license": m.get("license", {}).get("name"),
                "commercial_use": m.get("license", {}).get("commercial_use"),
                "readiness_score": cat.readiness_score(m),
                "has_benchmark": bool(cat.get_benchmarks(m["id"])),
                "artifact_url": hf_url,
                "source_group": m.get("source_group"),
            })
        print(json.dumps({"count": len(results), "total_matches": len(results),
                          "truncated": False, "models": results}, indent=2))
        return 0

    print(f"\n  {BOLD}{len(models)} models in catalog{RESET}\n")
    for m in models:
        print(_format_model_compact(cat, m))
    print()
    return 0


def cmd_scores(args: argparse.Namespace) -> int:
    cat = Catalog()
    models = cat.models
    scored = [(m, cat.readiness_score(m)) for m in models]
    scored.sort(key=lambda x: (-x[1], x[0]["id"]))

    if args.json:
        results = [{
            "id": m["id"],
            "name": m["name"],
            "score": s,
        } for m, s in scored]
        print(json.dumps({"scores": results}, indent=2))
        return 0

    print(f"\n  {BOLD}Core AI Readiness Scores{RESET}\n")
    print(f"  {'Score':>20s}  {'ID':40s}  Name")
    print(f"  {'─' * 20}  {'─' * 40}  {'─' * 30}")
    for m, s in scored:
        print(f"  {_fmt_score(s):>20s}  {m['id']:40s}  {m['name']}")

    # Grade distribution
    from collections import Counter
    grades = Counter()
    for _, s in scored:
        if s >= 85:
            grades["A"] += 1
        elif s >= 70:
            grades["B"] += 1
        elif s >= 55:
            grades["C"] += 1
        elif s >= 40:
            grades["D"] += 1
        else:
            grades["F"] += 1
    dist = ", ".join(f"{g}: {c}" for g, c in sorted(grades.items()))
    print(f"\n  {DIM}Grade distribution: {dist}{RESET}\n")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    cat = Catalog()
    models_to_compare = args.models

    if len(models_to_compare) < 2:
        if args.json:
            print(json.dumps({"error": "Compare requires at least 2 models"}, indent=2))
            return 1
        print(f"\n  {RED}Compare requires at least 2 models.{RESET}")
        print(f"  {DIM}Usage: coreai-catalog compare <model-a> <model-b> [model-c...]{RESET}")
        return 1

    all_models = []
    for mid in models_to_compare:
        m = cat.get_model(mid)
        if not m:
            if args.json:
                print(json.dumps({"error": f"Model '{mid}' not found"}, indent=2))
                return 1
            print(f"\n  {RED}Model '{mid}' not found.{RESET}")
            return 1
        all_models.append(m)

    if args.json:
        results = []
        for m in all_models:
            results.append({
                "id": m["id"],
                "name": m["name"],
                "score": cat.readiness_score(m),
                "capabilities": m.get("capabilities", []),
                "parameters": m.get("size", {}).get("parameters"),
                "precision": m.get("size", {}).get("precision"),
                "devices": m.get("device_support", {}),
                "license": m.get("license", {}).get("name"),
                "commercial_use": m.get("license", {}).get("commercial_use"),
                "runner": m.get("runtime", {}).get("runner"),
                "stock_runtime": m.get("runtime", {}).get("stock_runtime"),
                "benchmark_count": len(cat.get_benchmarks(m["id"])),
                "source_group": m.get("source_group"),
            })
        print(json.dumps({"comparison": results}, indent=2))
        return 0

    print(f"\n  {BOLD}Comparison: {' vs '.join(m['name'] for m in all_models)}{RESET}\n")

    # Headers
    fields = [
        ("Score", lambda m: str(cat.readiness_score(m))),
        ("Family", lambda m: m.get("family", "?")),
        ("Parameters", lambda m: m.get("size", {}).get("parameters", "?")),
        ("Precision", lambda m: m.get("size", {}).get("precision", "?")),
        ("Devices", lambda m: _fmt_devices(m.get("device_support", {}))),
        ("License", lambda m: m.get("license", {}).get("name", "?")),
        ("Runner", lambda m: m.get("runtime", {}).get("runner", "?")),
        ("Benchmarks", lambda m: str(len(cat.get_benchmarks(m["id"])))),
        ("Source", lambda m: m.get("source_group", "?")),
        ("Capabilities", lambda m: ", ".join(m.get("capabilities", []))),
    ]

    # Calculate column width — consider longest field value, not just name
    max_name = max(len(m["name"]) for m in all_models)
    max_val = max_name
    for label, getter in fields:
        for m in all_models:
            val_len = len(str(getter(m)))
            if val_len > max_val:
                max_val = val_len
    col_w = min(max(max_val, 12), 40)  # cap at 40 to prevent extreme overflow

    # Header row
    print(f"  {'Field':15s}", end="")
    for m in all_models:
        print(f"  {m['name'][:col_w]:{col_w}s}", end="")
    print()
    print(f"  {'─' * 15}", end="")
    for _ in all_models:
        print(f"  {'─' * col_w}", end="")
    print()

    for label, getter in fields:
        print(f"  {label:15s}", end="")
        for m in all_models:
            val = str(getter(m))
            # Truncate long values to col_w
            if len(val) > col_w:
                val = val[: col_w - 1] + "…"
            print(f"  {val:{col_w}s}", end="")
        print()
    print()
    return 0


def cmd_recommend(args: argparse.Namespace) -> int:
    cat = Catalog()
    capabilities = resolve_task(args.task)
    recommendations = cat.recommend_models(
        capabilities=capabilities,
        device=args.device,
        limit=args.limit,
        task=args.task,
        license_type=getattr(args, "license", None),
    )

    if args.json:
        results = []
        for rec in recommendations:
            devices = extract_device_list(rec.get("devices", {}))
            results.append({
                "id": rec["id"],
                "name": rec["name"],
                "score": rec["score"],
                "matched_capabilities": rec["matched_capabilities"],
                "parameters": rec.get("parameters"),
                "devices": devices,
                "license": rec.get("license"),
                "commercial_use": rec.get("commercial_use"),
                "has_benchmark": rec.get("has_benchmark"),
                "notes": rec.get("notes", ""),
            })
        print(json.dumps({
            "task": args.task,
            "resolved_capabilities": capabilities,
            "device": args.device,
            "recommendations": results,
        }, indent=2))
        return 0

    if not recommendations:
        print(f"\n  {DIM}No models found for task '{args.task}'.{RESET}")
        print(f"  {DIM}Resolved capabilities: {', '.join(capabilities)}{RESET}")
        # Show valid task keywords to help the user
        from .catalog import TASK_MAP
        valid = ", ".join(sorted(TASK_MAP.keys()))
        print(f"  {DIM}Try one of: {valid}{RESET}")
        return 0

    print(f"\n  {BOLD}Task:{RESET} {args.task}")
    print(f"  {BOLD}Capabilities:{RESET} {', '.join(capabilities)}")
    if args.device:
        print(f"  {BOLD}Device:{RESET} {args.device}")
    if args.explain:
        print(f"\n  {BOLD}── Decision tree ──{RESET}")
        print(f"  {DIM}1.{RESET} Task \"{args.task}\" → resolved to capabilities: {', '.join(capabilities)}")
        if args.device:
            print(f"  {DIM}2.{RESET} Filter: device_support.{args.device} == true")
        if args.license:
            print(f"  {DIM}3.{RESET} Filter: commercial_use == {args.license}")
        step = (4 if args.device else 3) if args.license else (3 if args.device else 2)
        print(f"  {DIM}{step}.{RESET} Rank by: readiness_score (desc) → first-capability priority → params (asc)")
        print(f"  {DIM}{step+1}.{RESET} Top {args.limit} returned\n")
    print(f"\n  {BOLD}Recommended models:{RESET}\n")

    for i, rec in enumerate(recommendations, 1):
        ds = rec.get("devices", {})
        devices = []
        if ds.get("iphone") is True:
            devices.append("iPhone")
        if ds.get("mac") is True:
            devices.append("Mac")
        bench = "📊 benchmarked" if rec.get("has_benchmark") else "not benchmarked"
        lic = rec.get("license", "?")
        params = rec.get("parameters", "?")
        cu = rec.get("commercial_use", "")
        lic_icon = f"{GREEN}✅{RESET}" if cu == "likely" else f"{YELLOW}⚠️ {RESET}"
        dev_str = "/".join(devices) if devices else "unknown"
        score_str = _fmt_score(rec["score"])

        # Header line with score, device, license
        print(f"  {BOLD}{i}. {rec['name']}{RESET}")
        print(f"     {score_str} · {dev_str} · {lic_icon} {lic}")
        print(f"     {bench} · {params} params")
        notes = rec.get("notes", "")
        if notes:
            note = notes[:120].replace("\n", " ")
            if len(notes) > 120:
                note += "…"
            print(f"     {DIM}{note}{RESET}")
        # Install command + artifact URL
        print(f"\n     {DIM}Install:{RESET}  coreai-catalog install {rec['id']}")
        art = cat.get_artifact(rec["id"])
        if art:
            hf = art.get("huggingface", {}) or {}
            url = hf.get("url", "")
            if url:
                print(f"     {DIM}Artifact:{RESET} {url}")
        print()

    if recommendations:
        first = recommendations[0]
        print(f"  {DIM}── Quick start ──{RESET}")
        print(f"    {BOLD}coreai-catalog install {first['id']}{RESET}")
    print()
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    cat = Catalog()
    model = cat.get_model(args.model_id)

    if not model:
        if args.json:
            print(json.dumps({"error": f"Model '{args.model_id}' not found"}))
        else:
            print(f"\n  {RED}Model '{args.model_id}' not found.{RESET}")
            print(f"  {DIM}Try: coreai-catalog search --capability chat{RESET}")
        return 1

    artifact = cat.get_artifact(model["id"])
    if not artifact:
        if args.json:
            print(json.dumps({"error": f"No artifact record for '{model['id']}'"}))
        else:
            print(f"\n  {RED}No artifact record for '{model['id']}'.{RESET}")
        return 1

    if is_installed(model["id"]) and not args.force:
        d = get_model_dir(model["id"])
        if args.json:
            print(json.dumps({
                "model_id": model["id"],
                "status": "already_installed",
                "path": str(d),
            }, indent=2))
        else:
            print(f"\n  {YELLOW}Model '{model['id']}' is already installed.{RESET}")
            print(f"  {DIM}Use --force to reinstall.{RESET}")
            print(f"  {DIM}Location: {d}{RESET}")
        return 0

    if not args.json:
        print(f"\n  {BOLD}Installing {model['name']}...{RESET}")
        size = model.get("size", {}).get("artifact_size", "")
        if size and size != "not_published":
            print(f"  {DIM}Artifact size: {size}{RESET}")

        if args.dry_run:
            print(f"  {DIM}(dry run — no files downloaded){RESET}")

    manifest = install_model(
        model=model,
        artifact=artifact,
        benchmarks=cat.get_benchmarks(model["id"]),
        dry_run=args.dry_run,
        verbose=not args.json,
    )

    # Report honestly based on the installation outcome
    file_layout = manifest.get("verified", {}).get("file_layout", "not_checked")

    if args.json:
        status = "dry_run" if args.dry_run else file_layout
        result = {
            "model_id": model["id"],
            "name": model.get("name", model["id"]),
            "status": status,
        }
        size = model.get("size", {}).get("artifact_size", "")
        if size and size != "not_published":
            result["artifact_size"] = size
        hf = artifact.get("huggingface", {}) or {}
        if hf.get("url"):
            result["artifact_url"] = hf["url"]
        if not args.dry_run:
            result["path"] = str(get_model_dir(model["id"]))
            # Machine-readable verification outcome (mismatched/missing
            # digests) so scripted agents can detect a failed sha256 check.
            if manifest.get("verification") is not None:
                result["verification"] = manifest["verification"]
        print(json.dumps(result, indent=2))
        # Mirror the human path: only a completed download or an explicit
        # manual-download handoff is success; download_failed,
        # verification_failed (sha256 mismatch), etc. must exit non-zero.
        if args.dry_run or file_layout in ("downloaded", "manual_required"):
            return 0
        return 1

    if args.dry_run:
        print(f"\n  {DIM}(dry run complete){RESET}\n")
        return 0

    if file_layout == "downloaded":
        print(f"\n  {GREEN}✅ Done.{RESET}")
        print(f"  {BOLD}Next steps:{RESET}")
        print(f"    View manifest:   cat {get_model_dir(model['id']) / 'manifest.json'}")
        print(f"    Swift snippet:   cat {get_model_dir(model['id']) / 'snippet.swift'}")
        print(f"    Uninstall:       coreai-catalog uninstall {model['id']}")
        print()
        return 0
    elif file_layout == "manual_required":
        print(f"\n  {YELLOW}⚠️  Manifest written, but manual download required.{RESET}")
        print(f"  {DIM}See manifest for the Hugging Face URL.{RESET}")
        print()
        return 0
    else:
        print(f"\n  {RED}❌ Installation failed (file_layout: {file_layout}).{RESET}")
        print(f"  {DIM}Manifest written to: {get_model_dir(model['id']) / 'manifest.json'}{RESET}")
        print()
        return 1


def cmd_uninstall(args: argparse.Namespace) -> int:
    if args.json:
        # Check if installed first for accurate JSON response
        d = get_model_dir(args.model_id)
        if not d.exists():
            print(json.dumps({
                "model_id": args.model_id,
                "status": "not_installed",
            }))
            return 1
        success = uninstall_model(args.model_id, verbose=False)
        print(json.dumps({
            "model_id": args.model_id,
            "status": "removed" if success else "failed",
        }))
        return 0 if success else 1

    if uninstall_model(args.model_id):
        return 0
    print(f"\n  {YELLOW}Model '{args.model_id}' was not installed.{RESET}")
    return 1


def cmd_capabilities(args: argparse.Namespace) -> int:
    """List all capabilities with model and benchmark counts."""
    cat = Catalog()
    cap_list = count_capabilities(cat.models, cat.get_benchmarks)

    if args.json:
        output = cap_list
        print(json.dumps({"count": len(output), "capabilities": output}, indent=2))
        return 0

    # Build Counter for display from the structured result
    from collections import Counter
    cap_counts = Counter()
    bench_counts_map = {}
    for entry in cap_list:
        cap_counts[entry["capability"]] = entry["model_count"]
        bench_counts_map[entry["capability"]] = entry["benchmark_count"]

    print(f"\n  {BOLD}Core AI Model Capabilities{RESET}\n")
    print(f"  {'Capability':35s}  Models  Benchmarked")
    print(f"  {'─' * 35}  {'─' * 6}  {'─' * 12}")
    for cap, count in cap_counts.most_common():
        bcount = bench_counts_map.get(cap, 0)
        print(f"  {cap:35s}  {count:>6}  {bcount:>12}")
    print(f"\n  {DIM}{len(cap_counts)} capabilities across {len(cat.models)} models{RESET}\n")
    return 0


def cmd_tasks(args: argparse.Namespace) -> int:
    """Browse all supported task keywords, grouped by capability."""
    from .catalog import TASK_MAP

    # Structured entries: one per capability, sorted, with synonym counts
    entries = build_task_capability_entries()

    if args.json:
        print(json.dumps({
            "count": len(TASK_MAP),
            "capabilities": entries,
        }, indent=2))
        return 0

    print(f"\n  {BOLD}Core AI Catalog — Task Keywords{RESET}")
    print(f"  {DIM}{len(TASK_MAP)} task synonyms across {len(entries)} capabilities{RESET}\n")

    for entry in entries:
        cap = entry["capability"]
        synonyms = entry["task_synonyms"]
        syn_str = ", ".join(synonyms)
        print(f"  {BOLD}{cap}{RESET} ({len(synonyms)})")
        print(f"    {DIM}{syn_str}{RESET}\n")

    print(f"  {DIM}Usage: coreai-catalog recommend --task \"<keyword>\"{RESET}")
    print()
    return 0


def cmd_transforms(args: argparse.Namespace) -> int:
    """Browse and query modality transformation pipelines."""
    from .transform_graph import TransformGraph

    cat = Catalog()
    graph = TransformGraph(cat.models, cat)

    if args.json:
        if args.from_modality and args.to_modality:
            pipeline = graph.shortest_path(args.from_modality, args.to_modality)
            if pipeline:
                print(json.dumps({
                    "from": args.from_modality,
                    "to": args.to_modality,
                    "pipeline": pipeline.to_dict(),
                }, indent=2))
            else:
                print(json.dumps({
                    "from": args.from_modality,
                    "to": args.to_modality,
                    "pipeline": None,
                    "error": "No transform path found",
                }, indent=2))
                return 1
        elif args.from_modality:
            reachable = sorted(graph.reachable_outputs(args.from_modality))
            print(json.dumps({
                "from": args.from_modality,
                "reachable_outputs": reachable,
                "count": len(reachable),
            }, indent=2))
            return 0
        else:
            matrix = graph.reachability_matrix()
            serializable = {k: sorted(v) for k, v in sorted(matrix.items())}
            print(json.dumps({
                "input_modalities": sorted(graph.input_modalities),
                "output_modalities": sorted(graph.output_modalities),
                "reachability": serializable,
            }, indent=2))
            return 0

    # Human-readable
    if args.from_modality and args.to_modality:
        pipeline = graph.shortest_path(args.from_modality, args.to_modality)
        if not pipeline:
            print(f"\n  {RED}No transform path: {args.from_modality} -> {args.to_modality}{RESET}")
            print(f"  {DIM}Try: coreai-catalog transforms --from {args.from_modality}{RESET}\n")
            return 1

        chain = " -> ".join(pipeline.modality_chain)
        print(f"\n  {BOLD}Transform: {args.from_modality} -> {args.to_modality}{RESET}")
        print(f"  {BOLD}Route:{RESET} {pipeline.hop_count} hop(s)")
        print(f"  {BOLD}Chain:{RESET} {chain}")
        print(f"  {BOLD}Download:{RESET} {pipeline.total_artifact_size}\n")

        for i, stage in enumerate(pipeline.stages, 1):
            tps = f"{stage.estimated_tokens_per_sec:.0f} tok/s" if stage.estimated_tokens_per_sec > 0 else "no benchmark"
            print(f"  {BOLD}{i}.{RESET} {stage.model_name}")
            print(f"     {DIM}{stage.input_modality} -> {stage.output_modality}{RESET}")
            print(f"     {DIM}{stage.parameters} | {tps} | {stage.runner}{RESET}")
            print(f"     {GREEN}coreai-catalog install {stage.model_id}{RESET}\n")
        return 0

    elif args.from_modality:
        reachable = sorted(graph.reachable_outputs(args.from_modality))
        print(f"\n  {BOLD}From: {args.from_modality}{RESET}")
        print(f"  {BOLD}Reachable outputs ({len(reachable)}):{RESET}\n")
        for mod in reachable:
            print(f"    {mod}")
        print()
        return 0

    else:
        all_inputs = sorted(graph.input_modalities)
        print(f"\n  {BOLD}Core AI Transform Graph{RESET}")
        print(f"  {DIM}{len(all_inputs)} input modalities -> {len(graph.output_modalities)} output modalities{RESET}\n")
        for inp in all_inputs:
            reachable = sorted(graph.reachable_outputs(inp))
            direct = {e.output_modality for e in graph.get_all_edges_from(inp)}
            print(f"  {BOLD}{inp}{RESET}")
            for out in reachable:
                marker = "  " if out in direct else "-> "
                print(f"    {marker}{out}")
            print()
        pairs = graph.get_all_modality_pairs()
        matrix = graph.reachability_matrix()
        total = sum(len(v) for v in matrix.values())
        print(f"  {DIM}Direct transforms: {len(pairs)} | Total reachable: {total}{RESET}\n")
        return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Check the local environment for Core AI development readiness."""
    print(f"\n  {BOLD}Core AI Catalog — Environment Check{RESET}")
    print(f"  {'─' * 60}\n")

    checks_passed = 0
    checks_total = 0

    def check(name: str, passed: bool, detail: str = "") -> None:
        nonlocal checks_passed, checks_total
        checks_total += 1
        icon = f"{GREEN}✅{RESET}" if passed else f"{YELLOW}⚠️ {RESET}"
        print(f"  {icon} {name:30s} {detail}")
        if passed:
            checks_passed += 1

    # Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    check("Python", sys.version_info >= (3, 10), py_ver)

    # pip
    check("pip", bool(shutil.which("pip") or shutil.which("pip3")), "")

    # Xcode
    xcode = shutil.which("xcodebuild")
    xcode_ver = ""
    if xcode:
        try:
            result = subprocess.run(
                [xcode, "-version"],
                capture_output=True, text=True, timeout=10,
            )
            xcode_ver = result.stdout.split("\n")[0] if result.returncode == 0 else ""
        except Exception:
            pass
    check("Xcode", bool(xcode), xcode_ver)

    # coreai-torch
    coreai_torch = shutil.which("coreai-torch") or _check_pip("coreai-torch")
    check("coreai-torch", bool(coreai_torch), "PyTorch→.aimodel converter" if coreai_torch else "not installed")

    # coreai-opt
    coreai_opt = shutil.which("coreai-opt") or _check_pip("coreai-opt")
    check("coreai-opt", bool(coreai_opt), "quantization/palettization" if coreai_opt else "not installed")

    # huggingface-cli
    hfcli = shutil.which("huggingface-cli") or shutil.which("hf")
    check("huggingface-cli", bool(hfcli), "for model downloads" if hfcli else "pip install huggingface-hub")

    # Disk space
    try:
        stat = os.statvfs(str(Path.home()))
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        check("Disk space", free_gb > 5, f"{free_gb:.1f} GB free")
    except Exception:
        check("Disk space", True, "unable to check")

    # Catalog
    cat = Catalog()
    model_count = len(cat.models)
    check("Catalog", model_count > 0, f"{model_count} models loaded")

    # Cache dir
    from .installer import CACHE_DIR
    installed = list_installed()
    check("Cache dir", True, str(CACHE_DIR))

    # Summary
    print(f"\n  {'─' * 60}")
    print(f"  {checks_passed}/{checks_total} checks passed.")
    if checks_passed == checks_total:
        print(f"  {GREEN}✅ Environment ready for Core AI development.{RESET}")
    elif checks_passed >= checks_total - 2:
        print(f"  {YELLOW}⚠️  Mostly ready. Install missing tools for full functionality.{RESET}")
    else:
        print(f"  {YELLOW}⚠️  Several tools missing. See recommendations below.{RESET}")

    # Only show install instructions for tools that actually failed
    missing = []
    if not coreai_torch:
        missing.append(("coreai-torch", "uv pip install coreai-torch"))
    if not coreai_opt:
        missing.append(("coreai-opt", "uv pip install coreai-opt"))
    if not hfcli:
        missing.append(("huggingface-cli", "pip install huggingface-hub"))
    if not shutil.which("uv"):
        missing.append(("uv (package manager)", "brew install uv"))

    if missing:
        print(f"\n  {BOLD}Install missing tools:{RESET}")
        for name, cmd in missing:
            print(f"    {DIM}{cmd}{RESET}")

    # Show available interfaces
    print(f"\n  {BOLD}Available interfaces:{RESET}")
    print(f"    {DIM}CLI:     coreai-catalog <command>{RESET}")
    print(f"    {DIM}MCP:     coreai-catalog-mcp  (Claude Desktop, Cursor, MCP clients){RESET}")
    print(f"    {DIM}JSON:    dist/*.json         (programmatic consumption){RESET}")
    print(f"    {DIM}Context: llms.txt, llms-full.txt, agent.json, openapi.yaml{RESET}")
    print()
    return 0 if checks_passed == checks_total else 1


def _check_pip(package: str) -> bool:
    """Check if a Python package is installed."""
    try:
        subprocess.run(
            [sys.executable, "-c", f"import {package.replace('-', '_')}"],
            capture_output=True, timeout=5,
        )
        # If import succeeds, returncode is 0
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", package],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def cmd_installed(args: argparse.Namespace) -> int:
    """List locally installed models."""
    installed = list_installed()
    if not installed:
        print(f"\n  {DIM}No models installed locally.{RESET}")
        print(f"  {DIM}Try: coreai-catalog install qwen3-vl-2b{RESET}")
        return 0

    print(f"\n  {BOLD}{len(installed)} model(s) installed:{RESET}\n")
    for m in installed:
        print(f"  {m.get('id', '?'):40s}  {m.get('name', '?')}")
        src = m.get("source", {})
        if src.get("huggingface"):
            print(f"  {'':40s}  {DIM}from {src['huggingface']}{RESET}")
    print()
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    """Automate the release workflow: validate, test, bump, tag, build, upload.

    Steps (in order):
      1. Pre-flight: ``scripts/validate.py`` + ``pytest``
      2. Confirm target version (or use ``--version``)
      3. Bump version in ``catalog.yaml`` + ``pyproject.toml``
      4. Regenerate ``dist/`` via ``scripts/generate.py``
      5. Git commit + tag ``v{version}``
      6. Build sdist + wheel (``python -m build``)
      7. Upload to PyPI via ``twine upload dist/*``
      8. Optionally ``git push --follow-tags``

    With ``--dry-run`` steps 7 and 8 are skipped (everything else runs
    so you can verify the version bump, git tag, and build succeed).
    """
    from .catalog import _find_catalog_root

    repo_root = _find_catalog_root()
    cat_yaml = repo_root / "catalog.yaml"
    pyproject = repo_root / "pyproject.toml"

    dry_run = getattr(args, "dry_run", False)
    push = getattr(args, "push", False)
    yes = getattr(args, "yes", False)

    tag_msg = f"{BOLD}Core AI Catalog — Publish{RESET}"
    print(f"\n  {tag_msg}")
    print(f"  {'─' * 60}\n")

    # ── 1. Pre-flight checks ──
    print(f"  {BOLD}Step 1/8: Pre-flight checks{RESET}")
    try:
        results = run_preflight_checks(repo_root)
        for r in results:
            print(f"    {r}")
    except PreflightError as exc:
        print(f"\n  {RED}{exc}{RESET}")
        print(f"  {DIM}Fix the issues above, then re-run.{RESET}\n")
        return 1
    print()

    # ── 2. Determine target version ──
    print(f"  {BOLD}Step 2/8: Version{RESET}")
    from .formatters import get_catalog_version
    current = get_catalog_version(repo_root)
    print(f"    Current version: {current}")

    if args.version:
        target = args.version
        validate_version(target)
    else:
        patch_v = suggest_next_version(current, "patch")
        minor_v = suggest_next_version(current, "minor")
        major_v = suggest_next_version(current, "major")
        print(f"    Suggested bumps:")
        print(f"      patch → {patch_v}")
        print(f"      minor → {minor_v}")
        print(f"      major → {major_v}")
        if yes:
            target = patch_v
            print(f"    {DIM}--yes: auto-selecting patch → {target}{RESET}")
        else:
            try:
                raw = input(
                    f"    Target version [{patch_v}]: "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n  {YELLOW}Aborted.{RESET}\n")
                return 1
            target = raw or patch_v
            try:
                validate_version(target)
            except ValueError as exc:
                print(f"\n  {RED}{exc}{RESET}\n")
                return 1

    if target == current:
        print(f"\n  {RED}Target version '{target}' equals current version. "
              f"Nothing to do.{RESET}\n")
        return 1

    print(f"    Target version: {GREEN}{target}{RESET}\n")

    # ── 3. Bump version (all surfaces: catalog.yaml, pyproject.toml,
    #      agent.json, openapi.yaml, README.md + CHANGELOG hint) ──
    print(f"  {BOLD}Step 3/8: Bump version{RESET}")
    for surface_result in bump_all_version_surfaces(repo_root, target):
        if "missing" in surface_result or "skipped" in surface_result:
            print(f"    {YELLOW}⚠️{RESET}  {surface_result}")
        else:
            print(f"    {GREEN}✅{RESET} {surface_result}")
    print()

    # ── 4. Regenerate dist/ ──
    print(f"  {BOLD}Step 4/8: Regenerate exports{RESET}")
    import subprocess as _sp
    gen_result = _sp.run(
        [sys.executable, "scripts/generate.py"],
        cwd=str(repo_root),
    )
    if gen_result.returncode != 0:
        print(f"\n  {RED}generate.py failed (exit "
              f"{gen_result.returncode}).{RESET}")
        print(f"  {DIM}Version files were bumped but exports were not "
              f"regenerated. Review and commit manually.{RESET}\n")
        return 1
    print(f"    {GREEN}✅{RESET} dist/ regenerated\n")

    # ── 5. Git commit + tag ──
    print(f"  {BOLD}Step 5/8: Git commit + tag{RESET}")
    tag = git_commit_and_tag(repo_root, target)
    print(f"    {GREEN}✅{RESET} committed + tagged {tag}\n")

    # ── 6. Build ──
    print(f"  {BOLD}Step 6/8: Build sdist + wheel{RESET}")
    build_dist(repo_root)
    print(f"    {GREEN}✅{RESET} built\n")

    # ── 7. Upload ──
    if dry_run:
        print(f"  {BOLD}Step 7/8: Upload to PyPI{RESET}")
        print(f"    {YELLOW}⏭  Skipped (--dry-run){RESET}\n")
    else:
        print(f"  {BOLD}Step 7/8: Upload to PyPI{RESET}")
        try:
            upload_to_pypi(repo_root)
            print(f"    {GREEN}✅{RESET} uploaded\n")
        except RuntimeError as exc:
            print(f"\n  {RED}{exc}{RESET}")
            print(f"  {DIM}Build artifacts are ready in dist/. "
                  f"Set PYPI_API_TOKEN and upload manually:{RESET}")
            print(f"  {DIM}  twine upload dist/*{RESET}\n")
            return 1
        except Exception as exc:
            print(f"\n  {RED}twine upload failed: {exc}{RESET}\n")
            return 1

    # ── 8. Push ──
    print(f"  {BOLD}Step 8/8: Push to remote{RESET}")
    if dry_run:
        print(f"    {YELLOW}⏭  Skipped (--dry-run){RESET}")
    elif push:
        try:
            git_push(repo_root)
            print(f"    {GREEN}✅{RESET} pushed\n")
        except Exception as exc:
            print(f"\n  {RED}git push failed: {exc}{RESET}")
            print(f"  {DIM}Push manually: git push --follow-tags{RESET}\n")
            return 1
    else:
        print(f"    {DIM}Skipped (use --push to push automatically){RESET}")
        print(f"    {DIM}Run: git push --follow-tags{RESET}")

    # ── Summary ──
    print(f"  {'─' * 60}")
    if dry_run:
        print(f"  {GREEN}✅ Dry run complete for v{target}.{RESET}")
        print(f"  {DIM}Re-run without --dry-run to publish.{RESET}")
    else:
        print(f"  {GREEN}✅ Released v{target} to PyPI.{RESET}")
        if push:
            print(f"  {DIM}Tags pushed to remote.{RESET}")
        else:
            print(f"  {DIM}Don't forget: git push --follow-tags{RESET}")
    print()
    return 0


# ── Contribute (draft → validate → write → PR) ──
#
# Field specs drive BOTH the argparse flags and the interactive prompts.
# Enum values are never hardcoded here: `schema_field` names the dotted
# path inside the JSON Schema and options are rendered from it at runtime.
# spec: (dest, flag, required, kind, schema_field, help)
#   kind: "str" | "csv" (comma-separated list) | "tri" (true/false/unknown)

_MODEL_FIELD_SPECS = [
    ("id", "--id", True, "str", None, "Model id (kebab-case, unique)"),
    ("name", "--name", True, "str", None, "Human-readable model name"),
    ("family", "--family", True, "str", None, "Model family (e.g. Qwen)"),
    ("source_group", "--source-group", True, "str", "source_group", None),
    ("source_path", "--source-path", True, "str", None,
     "Upstream URL documenting the conversion (https://...)"),
    ("artifact_ref", "--artifact-ref", False, "str", None,
     "Artifact id (defaults to the model id)"),
    ("capabilities", "--capabilities", True, "csv", None,
     "Comma-separated capabilities (e.g. chat,text-generation)"),
    ("input_modalities", "--input", True, "csv", None,
     "Comma-separated input modalities (e.g. text,image)"),
    ("output_modalities", "--output", True, "csv", None,
     "Comma-separated output modalities"),
    ("artifact_format", "--artifact-format", True, "str", "artifact.format", None),
    ("availability", "--availability", True, "str", "artifact.availability", None),
    ("parameters", "--parameters", True, "str", None, "Parameter count (e.g. 0.8B)"),
    ("precision", "--precision", True, "str", None, "Weights precision (e.g. int8)"),
    ("quantization", "--quantization", True, "str", None, "Quantization (e.g. int8lin)"),
    ("artifact_size", "--artifact-size", True, "str", None, "Download size (e.g. 969MB)"),
    ("runtime_name", "--runtime-name", True, "str", "runtime.runtime_name", None),
    ("runner", "--runner", True, "str", "runtime.runner", None),
    ("stock_runtime", "--stock-runtime", True, "tri", "runtime.stock_runtime", None),
    ("custom_kernel", "--custom-kernel", True, "tri", "runtime.custom_kernel", None),
    ("patch_required", "--patch-required", True, "tri", "runtime.patch_required", None),
    ("tokenizer_required", "--tokenizer-required", True, "tri",
     "runtime.tokenizer_required", None),
    ("processor_required", "--processor-required", True, "tri",
     "runtime.processor_required", None),
    ("aot_required", "--aot-required", True, "tri", "runtime.aot_required", None),
    ("iphone", "--iphone", True, "tri", "device_support.iphone", None),
    ("ipad", "--ipad", True, "tri", "device_support.ipad", None),
    ("mac", "--mac", True, "tri", "device_support.mac", None),
    ("mac_only", "--mac-only", True, "tri", "device_support.mac_only", None),
    ("license_name", "--license-name", True, "str", None, "License (e.g. Apache-2.0)"),
    ("commercial_use", "--commercial-use", True, "str", "license.commercial_use", None),
    ("status", "--status", True, "str", "status", None),
    ("maturity", "--maturity", True, "str", "maturity", None),
    ("confidence", "--confidence", True, "str", "confidence", None),
    ("sources", "--sources", True, "csv", None,
     "Comma-separated sources.yaml/upstreams.yaml record ids"),
    ("last_verified", "--last-verified", False, "str", None,
     "YYYY-MM-DD (defaults to today)"),
    ("notes", "--notes", False, "str", None, "Free-text notes (optional)"),
    ("architecture", "--architecture", False, "str", "architecture", None),
    # artifact provenance (anyOf: github and/or huggingface)
    ("hf_owner", "--hf-owner", False, "str", None, "Hugging Face repo owner"),
    ("hf_repo", "--hf-repo", False, "str", None, "Hugging Face repo name"),
    ("github_owner", "--github-owner", False, "str", None, "GitHub conversion repo owner"),
    ("github_repo", "--github-repo", False, "str", None, "GitHub conversion repo name"),
    ("github_path", "--github-path", False, "str", None, "GitHub doc/source URL"),
]

_BENCHMARK_FIELD_SPECS = [
    ("id", "--id", False, "str", None, "Benchmark id (derived if omitted)"),
    ("model_id", "--model-id", True, "str", None, "Existing catalog model id"),
    ("metric", "--metric", True, "str", "metric", None),
    ("value", "--value", True, "str", None, "Measured value (positive number)"),
    ("unit", "--unit", True, "str", "unit", None),
    ("device_class", "--device-class", True, "str", None,
     "Coarsened hardware class (e.g. 'M4 Max') — never a raw device model"),
    ("os_major", "--os-major", True, "str", None, "Major OS version (e.g. '26')"),
    ("compute_unit", "--compute-unit", True, "str", "compute_unit", None),
    ("precision", "--precision", False, "str", None, "Precision (e.g. int8)"),
    ("extraction_method", "--extraction-method", True, "str", "extraction_method", None),
    ("confidence", "--confidence", True, "str", "confidence", None),
    ("observed_date", "--observed-date", False, "str", None,
     "YYYY-MM-DD (defaults to today)"),
    ("source", "--source", True, "str", None,
     "sources.yaml/upstreams.yaml record id for provenance"),
    ("notes", "--notes", False, "str", None, "Free-text notes (optional)"),
]


def _parse_tri(value):
    """Parse a true/false/unknown flag value (schema tri-state)."""
    if isinstance(value, (bool,)) or value is None:
        return value
    lowered = str(value).strip().lower()
    if lowered in ("true", "yes", "1"):
        return True
    if lowered in ("false", "no", "0"):
        return False
    if lowered == "unknown":
        return "unknown"
    return value  # let the schema flag it with a hint


def _spec_value(spec_kind: str, raw):
    if raw is None:
        return None
    if spec_kind == "csv":
        return [part.strip() for part in str(raw).split(",") if part.strip()]
    if spec_kind == "tri":
        return _parse_tri(raw)
    return raw


def _collect_fields(specs, args, schema, interactive: bool) -> tuple[dict, list[str]]:
    """Collect field values from flags, prompting interactively for gaps.

    Returns (fields, missing_flags). Enum options shown in prompts are
    rendered from the schema at runtime.
    """
    from .contribute import schema_enum

    fields: dict = {}
    missing: list[str] = []
    for dest, flag, required, kind, schema_field, _help in specs:
        raw = getattr(args, dest, None)
        value = _spec_value(kind, raw)
        if value in (None, []) and required and interactive:
            options = schema_enum(schema, schema_field) if schema_field else []
            if kind == "tri":
                options = options or [True, False, "unknown"]
            prompt = f"    {flag.lstrip('-')}"
            if options:
                prompt += f" ({' | '.join(str(o) for o in options)})"
            prompt += ": "
            try:
                raw = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                raw = ""
            value = _spec_value(kind, raw) if raw else None
        if value in (None, []):
            if required:
                missing.append(flag)
            continue
        fields[dest] = value
    return fields, missing


def _print_errors(errors) -> None:
    from .contribute import format_error

    print(f"\n  {RED}{len(errors)} validation error(s) — all reported at once:{RESET}\n")
    for err in errors:
        print(f"    - {format_error(err)}")
    print()


def cmd_contribute_model(args: argparse.Namespace) -> int:
    """Draft a new model contribution: assemble → validate → write → PR."""
    from . import contribute as contrib

    root = contrib.find_root()
    schema = contrib.load_schema("model", root)
    interactive = getattr(args, "interactive", False) or (
        sys.stdin.isatty() and not getattr(args, "non_interactive", False)
        and not args.dry_run
    )

    fields, missing = _collect_fields(_MODEL_FIELD_SPECS, args, schema, interactive)
    if "last_verified" not in fields:
        from datetime import date
        fields["last_verified"] = date.today().isoformat()
    fields.setdefault("notes", None)

    problems = list(missing)
    has_hf = fields.get("hf_owner") and fields.get("hf_repo")
    has_gh = fields.get("github_owner") and fields.get("github_repo")
    if not has_hf and not has_gh:
        problems.append("--hf-owner/--hf-repo (or --github-owner/--github-repo)")
    if problems:
        print(f"\n  {RED}Missing required fields (all reported at once):{RESET}")
        for flag in problems:
            print(f"    {flag}")
        print(f"\n  {DIM}Enum values come from schema/model.schema.json + "
              f"schema/artifact.schema.json — run with no flags on a TTY for "
              f"interactive prompts.{RESET}\n")
        return 1

    model_entry = contrib.build_model_entry(fields)
    artifact_entry = contrib.build_artifact_entry(fields)

    new_source = None
    if getattr(args, "add_source", None):
        fields["new_source_id"] = args.add_source
        if not has_hf:
            print(f"\n  {RED}--add-source requires --hf-owner/--hf-repo.{RESET}")
            return 1
        new_source = contrib.build_hf_source_record(fields)

    # Validate everything against schemas + cross-references, aggregated.
    base_ctx = contrib.ids_context(root)
    xref_ctx = {k: set(v) for k, v in base_ctx.items()}
    xref_ctx["artifact_ids"].add(artifact_entry["id"])
    if new_source:
        xref_ctx["source_ids"].add(new_source["id"])

    errors = []
    for kind, entry in [("model", model_entry), ("artifact", artifact_entry)] + (
        [("source", new_source)] if new_source else []
    ):
        errors.extend(contrib.schema_errors(kind, entry, root))
        errors.extend(contrib.cross_reference_errors(kind, entry, xref_ctx))
        dup = contrib.duplicate_id_error(kind, entry, base_ctx)
        if dup:
            errors.append(dup)
    if errors:
        _print_errors(errors)
        return 1

    catalog_block = contrib.dump_entry_yaml(model_entry)
    artifact_block = contrib.dump_entry_yaml(artifact_entry)
    source_block = contrib.dump_entry_yaml(new_source) if new_source else None

    if args.dry_run:
        print(f"\n  {BOLD}Dry run — validated entries (nothing written):{RESET}\n")
        print(f"# ── append to catalog.yaml under models: ──")
        print(catalog_block)
        print(f"# ── append to artifacts.yaml under artifacts: "
              f"(and bump metadata.count) ──")
        print(artifact_block)
        if source_block:
            print(f"# ── append to sources.yaml under sources: ──")
            print(source_block)
        return 0

    # Write with rollback-on-gate-failure.
    touched = {
        "catalog.yaml": (root / "catalog.yaml").read_text(),
        "artifacts.yaml": (root / "artifacts.yaml").read_text(),
        "sources.yaml": (root / "sources.yaml").read_text(),
    }
    files_changed = ["catalog.yaml", "artifacts.yaml"]
    contrib.append_yaml_entry(root / "catalog.yaml", model_entry)
    contrib.append_yaml_entry(root / "artifacts.yaml", artifact_entry)
    old_count, new_count = contrib.bump_artifact_count(root)
    if new_source:
        contrib.append_yaml_entry(root / "sources.yaml", new_source)
        files_changed.append("sources.yaml")

    print(f"\n  {BOLD}Running the local gate (validate + audit)...{RESET}")
    ok, evidence = contrib.run_local_gate(root)
    if not ok:
        for name, original in touched.items():
            (root / name).write_text(original)
        print(f"\n  {RED}Local gate failed — changes rolled back:{RESET}")
        for line in evidence:
            print(f"    {line}")
        print()
        return 1

    # Aggregated diff summary.
    print(f"\n  {GREEN}✅ Local gate passed.{RESET}")
    print(f"\n  {BOLD}Diff summary:{RESET}")
    print(f"    catalog.yaml    +{len(catalog_block.splitlines())} lines "
          f"(model {model_entry['id']})")
    print(f"    artifacts.yaml  +{len(artifact_block.splitlines())} lines "
          f"(artifact {artifact_entry['id']}; metadata.count "
          f"{old_count} → {new_count})")
    if source_block:
        print(f"    sources.yaml    +{len(source_block.splitlines())} lines "
              f"(source {new_source['id']})")

    if getattr(args, "pr", False):
        print(f"\n  {BOLD}Regenerating exports for the PR...{RESET}")
        gen = subprocess.run([sys.executable, "scripts/generate.py"],
                             cwd=str(root), capture_output=True, text=True)
        if gen.returncode != 0:
            print(f"  {RED}generate.py failed — fix and open the PR "
                  f"manually.{RESET}")
            print((gen.stdout + gen.stderr).strip())
            return 1
        pr_files = files_changed + ["docs", "dist", "coreai_catalog/data"]
        ok, message = contrib.open_contribution_pr(
            root, model_entry["id"], pr_files, evidence,
        )
        if not ok:
            print(f"\n  {RED}PR step failed:{RESET} {message}")
            return 1
        print(f"\n  {GREEN}✅ {message}{RESET}\n")
        return 0

    print(f"\n  {BOLD}Next steps:{RESET}")
    print(f"    python scripts/generate.py   # regenerate docs/ + dist/")
    print(f"    git checkout -b contribute/add-{model_entry['id']} && "
          f"git add -A && git commit")
    print(f"    (or re-run with --pr to do this automatically via gh)")
    print(f"\n  {DIM}Model lane only — never add benchmarks.jsonl lines to a "
          f"model PR.{RESET}\n")
    return 0


def cmd_contribute_benchmark(args: argparse.Namespace) -> int:
    """Draft + validate a benchmarks.jsonl line and explain the curator lane."""
    from . import contribute as contrib

    root = contrib.find_root()
    schema = contrib.load_schema("benchmark", root)
    interactive = getattr(args, "interactive", False) or (
        sys.stdin.isatty() and not getattr(args, "non_interactive", False)
    )

    fields, missing = _collect_fields(_BENCHMARK_FIELD_SPECS, args, schema, interactive)
    if missing:
        print(f"\n  {RED}Missing required fields (all reported at once):{RESET}")
        for flag in missing:
            print(f"    {flag}")
        print(f"\n  {DIM}Enum values come from schema/benchmark.schema.json.{RESET}\n")
        return 1

    if "observed_date" not in fields:
        from datetime import date
        fields["observed_date"] = date.today().isoformat()
    try:
        fields["value"] = float(fields["value"])
        if fields["value"] == int(fields["value"]):
            fields["value"] = int(fields["value"])
    except (TypeError, ValueError):
        pass  # let the schema flag it with a hint
    if getattr(args, "higher_is_better", None) is not None:
        fields["higher_is_better"] = args.higher_is_better
    if "id" not in fields:
        fields["id"] = contrib.derive_benchmark_id(fields)

    entry = contrib.build_benchmark_entry(fields)
    errors = contrib.validate_entry("benchmark", entry, root)
    if errors:
        _print_errors(errors)
        return 1

    line = json.dumps(entry, ensure_ascii=False)
    print(f"\n  {GREEN}✅ Schema-valid benchmark line "
          f"(schema/benchmark.schema.json + cross-references):{RESET}\n")
    print(line)
    print()
    for text_line in contrib.CURATOR_LANE_EXPLANATION.splitlines():
        print(f"  {DIM}{text_line}{RESET}")
    print()

    if getattr(args, "write", False):
        path = root / "benchmarks.jsonl"
        text = path.read_text()
        if not text.endswith("\n"):
            text += "\n"
        path.write_text(text + line + "\n")
        print(f"  {GREEN}Appended to benchmarks.jsonl.{RESET} "
              f"{DIM}Open a dedicated single-line PR — do not mix with model "
              f"changes.{RESET}\n")
    return 0


def cmd_contribute(args: argparse.Namespace) -> int:
    """Dispatch for `coreai-catalog contribute <entity>`."""
    print(f"\n  {RED}Specify what to contribute: model | benchmark{RESET}")
    print(f"  {DIM}Try: coreai-catalog contribute model --help{RESET}\n")
    return 1


def cmd_version(args: argparse.Namespace) -> int:
    """Show catalog version and content statistics."""
    cat = Catalog()
    version = get_catalog_version(cat.root)
    last_verified = get_catalog_last_verified(cat.root)

    bench_count = len(cat.benchmarks)
    term_count = len(cat.terms)

    if args.json:
        print(json.dumps({
            "version": version,
            "model_count": len(cat.models),
            "benchmark_count": bench_count,
            "term_count": term_count,
            "last_verified": last_verified,
        }, indent=2))
        return 0

    print(f"\n  {BOLD}Core AI Catalog{RESET}")
    print(f"  {'─' * 40}")
    print(f"  Version:        {version}")
    print(f"  Models:         {len(cat.models)}")
    print(f"  Benchmarks:     {bench_count}")
    print(f"  Terms:          {term_count}")
    print(f"  Last verified:  {last_verified}")
    print()
    return 0


# ── CLI entry point ──


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coreai-catalog",
        description="Discover, compare, and install Core AI models for Apple Silicon.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Common tasks:\n"
            "  coreai-catalog capabilities          # see all capabilities\n"
            "  coreai-catalog search -c chat -d iphone  # find chat models for iPhone\n"
            "  coreai-catalog recommend -t 'robot vision' -d iphone\n"
            "  coreai-catalog transforms --from audio --to image  # plan transform pipeline\n"
            "  coreai-catalog show qwen3-vl-2b       # full model details\n"
            "  coreai-catalog install qwen3-vl-2b    # download + Swift snippet\n"
            "  coreai-catalog doctor                 # check your environment\n"
        ),
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    parser.add_argument("-V", "--version", action="store_true", help="Show version and exit")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # search
    p = sub.add_parser("search", aliases=["s"], help="Search models by criteria")
    p.add_argument("-c", "--capability",
                   help="Filter by capability (e.g. chat, text-generation, "
                        "vision-language, speech-to-text, text-to-speech, "
                        "embedding, object-detection, image-generation)")
    p.add_argument("-d", "--device",
                   help="Filter by device (iphone, ipad, mac)")
    p.add_argument("-l", "--license",
                   help="Filter by commercial use (likely, check_license)")
    p.add_argument("-f", "--family", help="Filter by model family (e.g. Qwen, Gemma, Whisper)")
    p.add_argument("-g", "--source-group",
                   help="Filter by source (official, zoo, external)")
    p.add_argument("-m", "--modality",
                   help="Filter by modality (text, image, audio)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_search)

    # show
    p = sub.add_parser("show", aliases=["info"], help="Show details for a specific model")
    p.add_argument("model_id", help="Model ID (e.g. qwen3-vl-2b)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument("-v", "--verbose", action="store_true", help="Show full notes (not truncated)")
    p.set_defaults(func=cmd_show)

    # list
    p = sub.add_parser("list", aliases=["ls"], help="List all models (sorted by readiness score)")
    p.add_argument("-c", "--capability", help="Filter by capability")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_list)

    # scores
    p = sub.add_parser("scores", help="Show readiness scores for all models")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_scores)

    # compare
    p = sub.add_parser("compare", help="Compare two or more models side-by-side")
    p.add_argument("models", nargs="+", help="Model IDs to compare")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_compare)

    # recommend
    p = sub.add_parser("recommend", aliases=["rec"], help="Get model recommendations for a task")
    p.add_argument("-t", "--task", required=True, help="Task description (e.g. 'robot vision')")
    p.add_argument("-d", "--device", help="Target device (iphone, mac)")
    p.add_argument("-l", "--license",
                   help="Filter by commercial use (likely, check_license)")
    p.add_argument("-n", "--limit", type=int, default=5, help="Max results (default 5)")
    p.add_argument("--explain", action="store_true", help="Show decision tree (task → capability → filter → rank)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_recommend)

    # install
    p = sub.add_parser("install", help="Download and install a model from Hugging Face")
    p.add_argument("model_id", help="Model ID to install")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without downloading")
    p.add_argument("--force", action="store_true", help="Reinstall if already installed")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_install)

    # uninstall
    p = sub.add_parser("uninstall", help="Remove a locally installed model")
    p.add_argument("model_id", help="Model ID to remove")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_uninstall)

    # installed
    p = sub.add_parser("installed", help="List locally installed models")
    p.set_defaults(func=cmd_installed)

    # doctor
    p = sub.add_parser("doctor", help="Check your environment for Core AI development")
    p.set_defaults(func=cmd_doctor)

    # capabilities
    p = sub.add_parser("capabilities", aliases=["caps"], help="List all capabilities with model counts")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_capabilities)

    # version
    p = sub.add_parser("version", help="Show catalog version and statistics")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_version)

    # tasks (browse-tasks)
    p = sub.add_parser("tasks", help="Browse all supported task keywords")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_tasks)

    # transforms
    p = sub.add_parser("transforms", aliases=["tx"],
                       help="Browse and query modality transformation pipelines")
    p.add_argument("--from", dest="from_modality",
                   help="Input modality (text, image, audio, document_image)")
    p.add_argument("--to", dest="to_modality",
                   help="Target output modality")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_transforms)

    # contribute
    p = sub.add_parser(
        "contribute",
        help="Draft a new catalog entry: assemble, validate, write, open a PR",
        description=(
            "Draft → validate → write → PR for new catalog entries. "
            "Enum values are validated against the JSON Schemas at runtime "
            "(schema/*.schema.json) — run interactively (no flags, TTY) to "
            "be prompted with the valid options."
        ),
    )
    p.set_defaults(func=cmd_contribute)
    contrib_sub = p.add_subparsers(dest="entity", help="What to contribute")

    pm = contrib_sub.add_parser(
        "model",
        help="Add a model (catalog.yaml + artifacts.yaml [+ sources.yaml])",
    )
    for dest, flag, _required, kind, schema_field, help_text in _MODEL_FIELD_SPECS:
        if help_text is None and schema_field:
            help_text = f"See enum in schema ({schema_field})"
        pm.add_argument(flag, dest=dest, help=help_text)
    pm.add_argument("--add-source", dest="add_source", metavar="SOURCE_ID",
                    help="Also draft a sources.yaml record (id) for the new "
                         "HF artifact host — include it in --sources")
    pm.add_argument("--dry-run", action="store_true",
                    help="Print the validated YAML without writing anything")
    pm.add_argument("--pr", action="store_true",
                    help="After the local gate passes, branch + commit + "
                         "open a PR via gh")
    pm.add_argument("--interactive", action="store_true",
                    help="Prompt for missing fields (default on a TTY)")
    pm.add_argument("--non-interactive", action="store_true",
                    help="Never prompt; fail with the aggregated missing list")
    pm.set_defaults(func=cmd_contribute_model)

    pb = contrib_sub.add_parser(
        "benchmark",
        help="Draft + validate a benchmarks.jsonl line (curator lane; no push)",
    )
    for dest, flag, _required, kind, schema_field, help_text in _BENCHMARK_FIELD_SPECS:
        if help_text is None and schema_field:
            help_text = f"See enum in schema ({schema_field})"
        pb.add_argument(flag, dest=dest, help=help_text)
    hib = pb.add_mutually_exclusive_group()
    hib.add_argument("--higher-is-better", dest="higher_is_better",
                     action="store_true", default=None)
    hib.add_argument("--lower-is-better", dest="higher_is_better",
                     action="store_false", default=None)
    pb.add_argument("--write", action="store_true",
                    help="Append the validated line to benchmarks.jsonl "
                         "(local only — you still open the single-line PR)")
    pb.add_argument("--interactive", action="store_true",
                    help="Prompt for missing fields (default on a TTY)")
    pb.add_argument("--non-interactive", action="store_true",
                    help="Never prompt; fail with the aggregated missing list")
    pb.set_defaults(func=cmd_contribute_benchmark)

    # publish
    p = sub.add_parser("publish",
                       help="Release workflow: validate, bump, tag, build, upload to PyPI")
    p.add_argument("-v", "--version",
                   help="Target version (e.g. 2.2.0). If omitted, interactively prompt.")
    p.add_argument("--dry-run", action="store_true",
                   help="Run everything except the PyPI upload and git push")
    p.add_argument("--push", action="store_true",
                   help="Push commits and tags to the remote after upload")
    p.add_argument("-y", "--yes", action="store_true",
                   help="Skip interactive prompts (defaults to patch bump)")
    p.set_defaults(func=cmd_publish)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Apply --no-color by re-evaluating color constants
    global BOLD, DIM, GREEN, YELLOW, BLUE, RED, RESET
    if getattr(args, "no_color", False) or not _IS_TTY:
        BOLD = DIM = GREEN = YELLOW = BLUE = RED = RESET = ""

    # Handle --version / -V flag
    if getattr(args, "version", False):
        cat = Catalog()
        version = get_catalog_version(cat.root)
        print(f"coreai-catalog {version}")
        sys.exit(0)

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
