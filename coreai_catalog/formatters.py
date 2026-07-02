"""
Core AI Catalog — shared formatting/utilities.

Eliminates code duplication across CLI, MCP server, public API, and exports
for the following recurring patterns:

1. Version reading (catalog.yaml → metadata.version / last_verified)
2. Device list extraction (iphone/ipad/mac → list, with unknown support)
3. Capabilities counting (Counter loop with benchmark counts)
4. Benchmark dict reshaping (pick metric/unit/value/device/...)
5. Task→capability reverse map (TASK_MAP → capability → [synonyms])
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

#: Canonical ordered list of device keys recognized in device_support dicts.
DEVICE_KEYS: tuple[str, ...] = ("iphone", "ipad", "mac")

#: Fields included when reshaping benchmark dicts (full set).
_BENCHMARK_FIELDS: tuple[str, ...] = (
    "metric",
    "unit",
    "value",
    "device",
    "compute_unit",
    "precision",
    "environment",
    "observed",
    "confidence",
    "notes",
)

#: Subset of benchmark fields used by CLI/MCP get_model (excludes precision/notes).
_BENCHMARK_FIELDS_COMPACT: tuple[str, ...] = (
    "metric",
    "unit",
    "value",
    "device",
    "compute_unit",
    "environment",
    "observed",
    "confidence",
)


# ── 1. Version reading ──────────────────────────────────────────────────


def read_catalog_metadata(catalog_root: Path) -> dict[str, Any]:
    """Read the ``metadata`` block from ``catalog.yaml``.

    Returns an empty dict if the file is missing or has no metadata.
    Consumers should treat the result as optional — callers default
    ``version`` to ``"unknown"`` and ``last_verified`` to ``None``.
    """
    cat_path = Path(catalog_root) / "catalog.yaml"
    if cat_path.exists():
        data = yaml.safe_load(cat_path.read_text()) or {}
        return data.get("metadata", {}) or {}
    return {}


def get_catalog_version(catalog_root: Path) -> str:
    """Extract the catalog version string from ``catalog.yaml`` metadata.

    Returns ``"unknown"`` when the file or field is absent.
    """
    return read_catalog_metadata(catalog_root).get("version", "unknown")


def get_catalog_last_verified(catalog_root: Path) -> str | None:
    """Extract the ``last_verified`` timestamp from catalog metadata.

    Returns ``None`` when the field is absent.
    """
    return read_catalog_metadata(catalog_root).get("last_verified")


# ── 2. Device list extraction ───────────────────────────────────────────


def extract_device_list(device_support: dict) -> list[str]:
    """Return the list of supported device keys from a device_support dict.

    Only keys whose value is exactly ``True`` are included.
    Keys are returned in canonical order: iphone, ipad, mac.
    """
    ds = device_support or {}
    return [d for d in DEVICE_KEYS if ds.get(d) is True]


def extract_device_unknown(device_support: dict) -> list[str]:
    """Return device keys whose support is neither True nor False.

    Useful for surfacing "unknown" device support explicitly in JSON output.
    """
    ds = device_support or {}
    return [d for d in DEVICE_KEYS if ds.get(d) not in (True, False)]


# ── 3. Capabilities counting ────────────────────────────────────────────


def count_capabilities(
    models: list[dict],
    has_benchmark_fn,
) -> list[dict[str, Any]]:
    """Count models per capability, with benchmark-aware sub-counts.

    Args:
        models: Iterable of model dicts (must have ``capabilities`` list).
        has_benchmark_fn: Callable(model_id) -> bool indicating whether the
            model has at least one benchmark record.

    Returns:
        List of ``{"capability", "model_count", "benchmark_count"}`` dicts
        sorted by descending model_count (Counter.most_common order).
    """
    cap_counts: Counter = Counter()
    bench_counts: Counter = Counter()
    for m in models:
        has_bench = bool(has_benchmark_fn(m["id"]))
        for c in m.get("capabilities", []):
            cap_counts[c] += 1
            if has_bench:
                bench_counts[c] += 1
    return [
        {
            "capability": cap,
            "model_count": count,
            "benchmark_count": bench_counts.get(cap, 0),
        }
        for cap, count in cap_counts.most_common()
    ]


# ── 4. Benchmark dict reshaping ─────────────────────────────────────────


def reshape_benchmark(bench: dict, *, include_extras: bool = True) -> dict[str, Any]:
    """Reshape a raw benchmark dict into the canonical output schema.

    Args:
        bench: Raw benchmark dict from catalog/benchmarks.yaml.
        include_extras: When True (default), include ``precision`` and
            ``notes`` fields. When False, emit only the compact field set
            used by CLI/MCP ``get_model`` (metric/unit/value/device/
            compute_unit/environment/observed/confidence).

    Returns:
        Dict with only the whitelisted fields, each via ``.get()`` so
        missing keys become ``None`` rather than raising.
    """
    fields = _BENCHMARK_FIELDS if include_extras else _BENCHMARK_FIELDS_COMPACT
    return {f: bench.get(f) for f in fields}


def reshape_benchmarks(
    benchmarks: list[dict], *, include_extras: bool = True,
) -> list[dict[str, Any]]:
    """Reshape a list of benchmark dicts (see :func:`reshape_benchmark`)."""
    return [reshape_benchmark(b, include_extras=include_extras) for b in benchmarks]


# ── 5. Task→capability reverse map ──────────────────────────────────────


def build_task_reverse_map() -> dict[str, list[str]]:
    """Build the reverse map: capability → sorted list of task synonyms.

    Imports ``TASK_MAP`` lazily to avoid import cycles. Returns a regular
    dict (sorted by capability name) of sorted synonym lists.
    """
    from .catalog import TASK_MAP

    cap_to_tasks: dict[str, list[str]] = defaultdict(list)
    for task_syn, caps in TASK_MAP.items():
        for cap in caps:
            cap_to_tasks[cap].append(task_syn)
    return {cap: sorted(syns) for cap, syns in sorted(cap_to_tasks.items())}


def build_task_capability_entries() -> list[dict[str, Any]]:
    """Build capability entries for the ``get_tasks`` / ``tasks`` views.

    Returns a list of ``{"capability", "task_synonyms", "synonym_count"}``
    dicts (one per capability, sorted by capability name).
    """
    cap_map = build_task_reverse_map()
    return [
        {
            "capability": cap,
            "task_synonyms": syns,
            "synonym_count": len(syns),
        }
        for cap, syns in sorted(cap_map.items())
    ]
