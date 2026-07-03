#!/usr/bin/env python3
"""Physics plausibility gate for benchmark submissions.

Three checks per entry, evaluated against public hardware limits
(chips.yaml) and the model's own catalog metadata:

1. Bandwidth ceiling (decode_throughput only): autoregressive decode is
   memory-bandwidth bound — every generated token must stream the model's
   (active) weights through the memory controller at least once, so

       tokens/s  <=  peak_bandwidth_bytes_per_s / bytes_per_token

   where bytes_per_token = active_param_count * bytes_per_weight(precision).
   A submitted value above 95% of that theoretical ceiling is rejected as
   physically implausible. Chips without a publicly grounded bandwidth
   figure (see chips.yaml) skip this check — we never invent numbers.

2. Tokens/elapsed internal consistency: if the entry's environment block
   carries raw counters (generation_tokens + elapsed_seconds), the claimed
   throughput must match tokens/elapsed within 10%.

3. Thermal telemetry gate (tier-aware — the B9 inversion fix):
   - tier "trusted"  (signed relay / sigstore submissions aiming for
     auto-merge): thermal_state MUST be present and 'nominal' or 'fair'.
     Missing or 'unknown' telemetry FAILS — omitting telemetry can no
     longer buy a pass in the trusted lane.
   - tier "curator" (unsigned upstream_readme_* entries reviewed by a
     human): absence is tolerated; only 'serious'/'critical' fail.

Usage:
    python scripts/physics_check.py --input <file_with_jsonl_lines> \
        [--tier trusted|curator] [--chips chips.yaml] [--catalog catalog.yaml]

Exit codes:
    0 — all entries physically plausible for the given tier
    1 — at least one check failed
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHIPS_PATH = ROOT / "chips.yaml"
CATALOG_PATH = ROOT / "catalog.yaml"

# Fraction of the theoretical bandwidth ceiling a real submission may
# reach. Real decoders lose throughput to KV-cache reads, activations and
# scheduling, so >95% of theoretical peak is implausible.
CEILING_MARGIN = 0.95

# Max relative error between claimed throughput and tokens/elapsed.
CONSISTENCY_TOLERANCE = 0.10

# bytes per weight by precision pattern (checked in order).
# MXFP4: 4-bit elements + one shared 8-bit scale per 32-element block
# (OCP Microscaling spec) = 4.25 bits/weight.
_PRECISION_PATTERNS: list[tuple[str, float]] = [
    (r"fp32|float32", 4.0),
    (r"fp16|float16|bf16|bfloat16|half", 2.0),
    (r"mxfp4", 0.53125),
    (r"1\.58|ternary", 0.2),
    (r"int4|4[-_ ]?bit|w4|fp4", 0.5),
    (r"int8|8[-_ ]?bit|w8|sym8", 1.0),
]

# Only this metric is bandwidth-ceiling checkable today.
_CEILING_METRICS = {"decode_throughput"}

# Gates whose conjunction earns the signed_plausible auto-merge outcome
# (used by benchmark-validate.yml; kept here so it is unit-testable).
TIER_GATES = (
    "schema_valid",
    "model_id_exists",
    "signature_valid",
    "identity_matches_author",
    "physics_pass",
    "outlier_pass",
    "not_duplicate",
)

# How far back the duplicate gate looks for a same-cohort submission.
DUPLICATE_WINDOW_DAYS = 7


def evaluate_tier(gates: dict) -> str:
    """Map the CI gate results onto a merge outcome.

    signed_plausible — signed submission whose signer identity matches
    the PR author, physically plausible, schema-valid: auto-merge.
    unverified — anything else in the signed lanes: curator review.

    NOTE: signed_plausible is a CI *gate outcome*, not a value of the
    stored ``verification_tier`` field. The trust ladder's
    ``community_verified`` rung requires independent reproduction by a
    SECOND identity (docs/benchmark-protocol.md, benchmark.schema.json)
    — a single n=1 submission can never earn it here, no matter how
    well signed. The merged row keeps ``verification_tier: unverified``
    (accurate for n=1); promotion to community_verified is a separate,
    curator-driven step. CI also cannot rewrite the field post hoc:
    every field except ``_signature`` is covered by the signature
    (verify_benchmark_signature.canonical_payload), so stamping a tier
    into the row would invalidate the submitter's signature.
    """
    if all(bool(gates.get(g)) for g in TIER_GATES):
        return "signed_plausible"
    return "unverified"


def find_recent_duplicate(
    entry: dict,
    store_lines,
    submitted_raw: str | None = None,
    today: datetime.date | None = None,
    window_days: int = DUPLICATE_WINDOW_DAYS,
) -> dict | None:
    """Return the first stored row that makes `entry` a duplicate, or None.

    A duplicate is another row with the same model_id + device_class +
    metric whose observed_date falls within the last `window_days`.

    Self-exclusion (the F1/B3 unreachable-auto-merge fix): CI evaluates
    this gate on the pull_request MERGE checkout, whose benchmarks.jsonl
    already CONTAINS the just-added line. Without exclusion every fresh
    submission (observed within the window — i.e. every legitimate
    `bench run` result) matches ITSELF and can never auto-merge, while
    stale >window results sail through — an inverted freshness
    incentive. The submitted row is excluded exactly ONCE:

    - `submitted_raw` given (the raw JSONL line as added, including
      `_signature`): the first byte-identical stored line is skipped.
      Exactly-once matters — if an identical line was ALREADY in the
      store, the second copy still counts as a duplicate.
    - otherwise the first stored row with the same `id` is skipped.
      (Raw-line matching is preferred: an `id` is submitter-chosen, so
      skipping every equal-id row would let a submitter dodge the gate
      by reusing the id of the recent row they are duplicating.)
    """
    if today is None:
        today = datetime.date.today()
    cutoff = (today - datetime.timedelta(days=window_days)).isoformat()
    sub_norm = submitted_raw.strip().lstrip("+") if submitted_raw else None

    skipped_self = False
    for raw in store_lines:
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        if not skipped_self and sub_norm is not None and raw == sub_norm:
            skipped_self = True
            continue
        try:
            existing = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if (not skipped_self and sub_norm is None
                and existing.get("id") == entry.get("id")):
            skipped_self = True
            continue
        if (existing.get("model_id") == entry.get("model_id")
                and existing.get("device_class") == entry.get("device_class")
                and existing.get("metric") == entry.get("metric")
                and existing.get("observed_date", "") >= cutoff):
            return existing
    return None


def load_chip_bandwidth(chips_path: Path = CHIPS_PATH) -> dict[str, float]:
    """Load {normalized chip name: peak bandwidth GB/s} from chips.yaml."""
    import yaml

    if not chips_path.exists():
        return {}
    data = yaml.safe_load(chips_path.read_text()) or {}
    out: dict[str, float] = {}
    for row in data.get("chips", []):
        chip = row.get("chip")
        bw = row.get("peak_memory_bandwidth_gbps")
        if chip and isinstance(bw, (int, float)) and bw > 0:
            out[normalize_chip(chip)] = float(bw)
    return out


def normalize_chip(device_class: str) -> str:
    """Normalize a device_class/chip string to a chips.yaml key.

    Accepts both the bare chip strings used in benchmarks.jsonl
    ('M4 Max', 'A18 Pro') and the coarsened slugs from
    benchmarks/protocol-config.json ('mac-m4-max', 'iphone-a18-pro').
    """
    s = (device_class or "").strip().lower()
    s = re.sub(r"^(mac|ipad|iphone)-", "", s)
    s = s.replace("-", " ").replace("_", " ")
    return re.sub(r"\s+", " ", s).strip()


def parse_param_count(text: str | None) -> float | None:
    """Parse a catalog size.parameters string into an absolute weight count.

    '0.8B' -> 8e8; '350M' -> 3.5e8.
    MoE strings like '35B / ~3B active' return the ACTIVE count (3e9):
    decode streams only the active experts' weights per token.
    """
    if not text:
        return None
    text = str(text)
    m = re.search(r"~?(\d+(?:\.\d+)?)\s*([BM])\b[^/]*active", text, re.IGNORECASE)
    if not m:
        m = re.search(r"(\d+(?:\.\d+)?)\s*([BM])\b", text)
    if not m:
        return None
    value = float(m.group(1))
    scale = 1e9 if m.group(2).upper() == "B" else 1e6
    return value * scale


def bytes_per_weight(precision: str | None) -> float | None:
    """Map a precision string to bytes/weight, or None if unrecognized."""
    if not precision:
        return None
    p = str(precision).lower()
    p = p.removeprefix("inferred:")
    for pattern, bpw in _PRECISION_PATTERNS:
        if re.search(pattern, p):
            return bpw
    return None


def load_model_index(catalog_path: Path = CATALOG_PATH) -> dict[str, dict]:
    """Load {model_id: model} from catalog.yaml."""
    import yaml

    if not catalog_path.exists():
        return {}
    cat = yaml.safe_load(catalog_path.read_text()) or {}
    return {m["id"]: m for m in cat.get("models", []) if "id" in m}


def check_entry(
    entry: dict,
    chips: dict[str, float],
    models: dict[str, dict],
    tier: str = "curator",
) -> tuple[bool, list[dict]]:
    """Run all physics checks on one benchmark entry.

    Returns (passed, checks) where each check is
    {"check": name, "status": "pass"|"fail"|"skip", "detail": str}.
    """
    checks: list[dict] = []

    # --- 1. bandwidth ceiling -------------------------------------------
    metric = entry.get("metric", "")
    if metric not in _CEILING_METRICS:
        checks.append({
            "check": "bandwidth_ceiling", "status": "skip",
            "detail": f"metric '{metric}' has no bandwidth-ceiling model",
        })
    else:
        chip_key = normalize_chip(entry.get("device_class", ""))
        bw = chips.get(chip_key)
        model = models.get(entry.get("model_id", ""), {})
        size = model.get("size", {}) if isinstance(model, dict) else {}
        params = parse_param_count(size.get("parameters"))
        precision = entry.get("precision") or size.get("precision")
        bpw = bytes_per_weight(precision)

        if bw is None:
            checks.append({
                "check": "bandwidth_ceiling", "status": "skip",
                "detail": (
                    f"no publicly grounded bandwidth for chip "
                    f"'{entry.get('device_class')}' in chips.yaml"
                ),
            })
        elif params is None or bpw is None:
            checks.append({
                "check": "bandwidth_ceiling", "status": "skip",
                "detail": (
                    f"cannot size bytes/token (parameters="
                    f"{size.get('parameters')!r}, precision={precision!r})"
                ),
            })
        else:
            ceiling = bw * 1e9 / (params * bpw)
            allowed = CEILING_MARGIN * ceiling
            try:
                value = float(entry.get("value", 0))
            except (TypeError, ValueError):
                value = 0.0
            if value > allowed:
                checks.append({
                    "check": "bandwidth_ceiling", "status": "fail",
                    "detail": (
                        f"{value:g} tok/s exceeds {CEILING_MARGIN:.0%} of the "
                        f"theoretical ceiling {ceiling:.1f} tok/s "
                        f"({bw:g} GB/s / ({params:g} weights x {bpw:g} B))"
                    ),
                })
            else:
                checks.append({
                    "check": "bandwidth_ceiling", "status": "pass",
                    "detail": (
                        f"{value:g} tok/s <= {allowed:.1f} tok/s "
                        f"(ceiling {ceiling:.1f}, chip {bw:g} GB/s)"
                    ),
                })

    # --- 2. tokens/elapsed internal consistency ------------------------
    env = entry.get("environment") or {}
    tokens = env.get("generation_tokens", env.get("tokens_generated"))
    elapsed = env.get("elapsed_seconds", env.get("elapsed_s"))
    if metric in _CEILING_METRICS and tokens and elapsed:
        try:
            implied = float(tokens) / float(elapsed)
            value = float(entry.get("value", 0))
            rel_err = abs(value - implied) / implied if implied else float("inf")
            if rel_err > CONSISTENCY_TOLERANCE:
                checks.append({
                    "check": "tokens_elapsed_consistency", "status": "fail",
                    "detail": (
                        f"claimed {value:g} tok/s vs {implied:.1f} implied by "
                        f"{tokens} tokens / {elapsed}s ({rel_err:.0%} off, "
                        f"tolerance {CONSISTENCY_TOLERANCE:.0%})"
                    ),
                })
            else:
                checks.append({
                    "check": "tokens_elapsed_consistency", "status": "pass",
                    "detail": f"{value:g} tok/s matches {implied:.1f} implied ({rel_err:.1%} off)",
                })
        except (TypeError, ValueError, ZeroDivisionError):
            checks.append({
                "check": "tokens_elapsed_consistency", "status": "fail",
                "detail": f"unparseable counters (tokens={tokens!r}, elapsed={elapsed!r})",
            })
    else:
        checks.append({
            "check": "tokens_elapsed_consistency", "status": "skip",
            "detail": "no raw generation_tokens/elapsed_seconds counters in environment",
        })

    # --- 3. thermal telemetry gate (tier-aware) -------------------------
    thermal = env.get("thermal_state")
    if tier == "trusted":
        if thermal in ("nominal", "fair"):
            checks.append({
                "check": "thermal_telemetry", "status": "pass",
                "detail": f"thermal_state={thermal}",
            })
        else:
            checks.append({
                "check": "thermal_telemetry", "status": "fail",
                "detail": (
                    f"trusted tier requires measured thermal_state of "
                    f"'nominal' or 'fair'; got {thermal!r} — missing or "
                    f"unknown telemetry no longer passes"
                ),
            })
    else:  # curator lane tolerates absence
        if thermal in ("serious", "critical"):
            checks.append({
                "check": "thermal_telemetry", "status": "fail",
                "detail": f"device was throttling (thermal_state={thermal})",
            })
        else:
            checks.append({
                "check": "thermal_telemetry", "status": "pass",
                "detail": f"thermal_state={thermal!r} (absence tolerated in curator lane)",
            })

    passed = not any(c["status"] == "fail" for c in checks)
    return passed, checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Physics plausibility gate for benchmark submissions")
    parser.add_argument("--input", required=True, help="File containing the new JSONL line(s)")
    parser.add_argument("--tier", choices=("trusted", "curator"), default="curator",
                        help="trusted = signed lane (missing telemetry fails); curator = human-review lane")
    parser.add_argument("--chips", default=str(CHIPS_PATH), help="Path to chips.yaml")
    parser.add_argument("--catalog", default=str(CATALOG_PATH), help="Path to catalog.yaml")
    args = parser.parse_args()

    raw = Path(args.input).read_text().strip()
    lines = [l for l in raw.splitlines() if l.strip() and not l.strip().startswith("#")]
    if not lines:
        print("No valid lines to check", file=sys.stderr)
        return 1

    chips = load_chip_bandwidth(Path(args.chips))
    models = load_model_index(Path(args.catalog))

    all_pass = True
    results: list[str] = []
    for i, line in enumerate(lines):
        line = line.strip().lstrip("+")
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            results.append(f"Line {i+1} | INVALID JSON | {e}")
            all_pass = False
            continue
        entry.pop("_signature", None)

        passed, checks = check_entry(entry, chips, models, tier=args.tier)
        if not passed:
            all_pass = False
        for c in checks:
            icon = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[c["status"]]
            results.append(f"Line {i+1} | {c['check']} | {icon} — {c['detail']}")

    # Write comment file for GitHub Action
    comment = f"## Physics Check Results (tier: {args.tier})\n\n| Line | Check | Result |\n|---|---|---|\n"
    for r in results:
        parts = r.split(" | ", 2)
        while len(parts) < 3:
            parts.append("")
        comment += f"| {parts[0]} | {parts[1]} | {parts[2]} |\n"
    try:
        Path("/tmp/physics-comment.md").write_text(comment)
    except OSError:
        pass  # /tmp might not be writable

    for r in results:
        print(r)

    if not all_pass:
        print("\n::error::Physics check failed — submission is not plausible for this tier", file=sys.stderr)
        return 1
    print("\nAll physics checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
