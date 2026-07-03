"""
Core AI Catalog discovery & governance toolkit (redteam findings F4/F5/F6).

Single implementation shared by three surfaces:

  1. ``scripts/discover.py``        — standalone discovery CLI (thin wrapper)
  2. ``.github/workflows/discover.yml`` — weekly scan that upserts ONE pinned
     "Porting candidates" issue (label ``porting-candidates``)
  3. ``.github/workflows/model-request-to-pr.yml`` — parses the
     ``model-request.yml`` issue FORM and turns it into a validated draft PR

The old ``scripts/discover.py`` dedup was structurally broken (finding F4):
it compared a candidate's ``org/name`` key against the set of *converted*
Hugging Face artifact repo names stored WITHOUT an owner prefix (e.g.
``qwen3.5-0.8B-CoreAI``) — the membership test could never match, so
already-ported models kept rescoring as top candidates. The fixed dedup
matches a candidate upstream repo against the catalog three ways, in order
of trust:

  (a) the authored ``upstream_repo`` field on catalog models (``org/name``
      of the ORIGINAL upstream repo — the strongest signal),
  (b) Hugging Face ``base_model`` metadata on the catalog's artifact host
      repos (the converted repo declares which upstream it was built from),
  (c) a normalized-name fuzzy fallback against catalog model ids/names.

Everything network-facing takes an injectable ``fetch`` callable so tests
run entirely on fixtures. CLI wiring into ``coreai-catalog discover``
happens in a later wave — ``run_discovery`` is the clean entry point.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Optional

import yaml


# ── Root / IO helpers ──


def find_root() -> Path:
    """Locate the catalog repo root (where catalog.yaml lives)."""
    from .catalog import _find_catalog_root
    return _find_catalog_root()


def read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def fetch_json(url: str, timeout: int = 15) -> list | dict | None:
    """Default network fetcher (tests inject a fixture-backed replacement)."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


# ── Hugging Face upstream orgs that commonly release models ──

UPSTREAM_ORGS = [
    "Qwen", "google", "openai", "mistralai",
    "ibm-granite", "LiquidAI", "openbmb",
    "black-forest-labs", "microsoft", "meta-llama",
    "deepseek-ai", "tiiuae", "stabilityai",
    "HuggingFaceTB", "allenai", "Nyandro",
]

# ── Apple's stock capabilities (models shipped with the OS) ──

APPLE_STOCK_CAPABILITIES = {
    "chat": "Apple Intelligence 3B Foundation Model (built-in, iOS 18+)",
    "text-generation": "Apple Intelligence 3B Foundation Model (built-in, iOS 18+)",
    "summarization": "Apple Intelligence Writing Tools",
    "image-generation": "Image Playground (built-in, iOS 18.2+)",
    "image-editing": "Clean Up (built-in, iOS 18.2+)",
    "transcription": "Apple Speech framework (built-in)",
    "translation": "Apple Translation framework (built-in)",
    "embedding": "Apple Neural Engine embeddings (built-in)",
}

# ── Model architecture patterns ──

ARCH_PATTERNS = {
    # LLMs
    "qwen": {"arch": "Qwen", "track": "L", "typical_size": "1.5-72B"},
    "gemma": {"arch": "Gemma", "track": "L", "typical_size": "2-31B"},
    "llama": {"arch": "Llama", "track": "L", "typical_size": "1-70B"},
    "mistral": {"arch": "Mistral", "track": "L", "typical_size": "7-8B"},
    "phi": {"arch": "Phi", "track": "L", "typical_size": "2-4B"},
    "granite": {"arch": "Granite", "track": "L", "typical_size": "1-8B"},
    "deepseek": {"arch": "DeepSeek", "track": "L", "typical_size": "1-67B"},
    "lfm": {"arch": "Liquid", "track": "L", "typical_size": "1-8B"},
    "minicpm": {"arch": "MiniCPM", "track": "L", "typical_size": "1-8B"},
    "nanbeige": {"arch": "Nanbeige", "track": "L", "typical_size": "3B"},
    # VLMs
    "vl": {"arch": "VLM", "track": "L", "typical_size": "2-8B"},
    "vlm": {"arch": "VLM", "track": "L", "typical_size": "2-8B"},
    "vision": {"arch": "Vision", "track": "V", "typical_size": "0.3-2B"},
    # Audio
    "whisper": {"arch": "Whisper", "track": "V", "typical_size": "0.1-1.5B"},
    "tts": {"arch": "TTS", "track": "V", "typical_size": "0.08-0.3B"},
    "parakeet": {"arch": "ASR", "track": "V", "typical_size": "0.6B"},
    # Vision
    "yolo": {"arch": "Detection", "track": "V", "typical_size": "0.01-0.1B"},
    "sam": {"arch": "Segmentation", "track": "V", "typical_size": "0.1-0.3B"},
    "depth": {"arch": "Depth", "track": "V", "typical_size": "0.03-0.3B"},
    "esrgan": {"arch": "SuperRes", "track": "V", "typical_size": "0.01-0.04B"},
    # Generation
    "flux": {"arch": "Diffusion", "track": "V", "typical_size": "4-12B"},
    "stable-diffusion": {"arch": "Diffusion", "track": "V", "typical_size": "1-8B"},
    "ltx": {"arch": "Video", "track": "V", "typical_size": "2B"},
}


# ── Dedup index (the F4 fix) ──


def normalize_name(name: str) -> str:
    """Normalize a model id/name for fuzzy comparison.

    Lowercase, strip separators and anything non-alphanumeric so
    ``Qwen3.5-0.8B`` and ``qwen3-5-0-8b`` normalize identically.
    """
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def base_models_from_tags(tags: list) -> set[str]:
    """Extract ``org/name`` upstream repos from HF ``base_model:`` tags.

    The HF API encodes lineage as tags: ``base_model:ORG/NAME`` and
    ``base_model:finetune:ORG/NAME`` / ``base_model:quantized:ORG/NAME``
    (verified live against huggingface.co/api/models?author=mlboydaisuke).
    """
    found: set[str] = set()
    for tag in tags or []:
        if not isinstance(tag, str) or not tag.startswith("base_model:"):
            continue
        ref = tag.split(":")[-1]
        if "/" in ref:
            found.add(ref.lower())
    return found


@dataclass
class CatalogIndex:
    """Everything needed to decide 'is this upstream already ported?'."""
    upstream_repos: set[str] = field(default_factory=set)   # authored org/name
    base_models: set[str] = field(default_factory=set)      # from HF metadata
    artifact_repos: set[str] = field(default_factory=set)   # owner/repo + bare
    normalized_names: set[str] = field(default_factory=set)  # ids + names
    model_count: int = 0


def build_catalog_index(
    root: Optional[Path] = None,
    catalog: Optional[dict] = None,
    artifacts: Optional[dict] = None,
    base_models: Optional[set[str]] = None,
) -> CatalogIndex:
    """Build the dedup index from catalog.yaml + artifacts.yaml.

    ``catalog``/``artifacts`` may be passed directly (tests use fixtures).
    ``base_models`` is the optional pre-fetched HF lineage set — see
    ``fetch_artifact_base_models`` (kept separate so offline runs still
    get the authored ``upstream_repo`` + fuzzy layers).
    """
    if catalog is None or artifacts is None:
        root = root or find_root()
        catalog = catalog if catalog is not None else read_yaml(root / "catalog.yaml")
        artifacts = artifacts if artifacts is not None else read_yaml(root / "artifacts.yaml")

    index = CatalogIndex(base_models={b.lower() for b in (base_models or set())})

    models = catalog.get("models", []) or []
    index.model_count = len(models)
    for m in models:
        # (a) authored upstream_repo — 'org/name' of the ORIGINAL upstream.
        # The field is being introduced in schema/model.schema.json; absent
        # values are simply skipped (never fabricated).
        upstream = m.get("upstream_repo")
        if isinstance(upstream, str) and "/" in upstream:
            index.upstream_repos.add(upstream.lower())
        # (c) normalized ids and names for the fuzzy fallback
        for key in ("id", "name"):
            norm = normalize_name(m.get(key, ""))
            if norm:
                index.normalized_names.add(norm)

    for a in artifacts.get("artifacts", []) or []:
        hf = a.get("huggingface", {}) or {}
        owner, repo = hf.get("owner", ""), hf.get("repo", "")
        if repo:
            index.artifact_repos.add(repo.lower())
            if owner:
                index.artifact_repos.add(f"{owner}/{repo}".lower())

    return index


def fetch_artifact_base_models(
    artifacts: dict,
    fetch: Callable = fetch_json,
) -> set[str]:
    """Fetch HF ``base_model`` lineage for the catalog's artifact host repos.

    One API call per unique Hugging Face owner (the author listing carries
    the tags for all of that owner's repos), filtered to repos actually
    referenced by artifacts.yaml. Returns lowercase ``org/name`` upstreams.
    """
    wanted: dict[str, set[str]] = {}
    for a in artifacts.get("artifacts", []) or []:
        hf = a.get("huggingface", {}) or {}
        owner, repo = hf.get("owner", ""), hf.get("repo", "")
        if owner and repo:
            wanted.setdefault(owner, set()).add(f"{owner}/{repo}".lower())

    lineage: set[str] = set()
    for owner, repo_ids in wanted.items():
        data = fetch(
            f"https://huggingface.co/api/models?author={owner}"
            "&sort=lastModified&direction=-1&limit=100"
        )
        if not data or not isinstance(data, list):
            continue
        for m in data:
            repo_id = (m.get("id") or m.get("modelId") or "").lower()
            if repo_id in repo_ids:
                lineage |= base_models_from_tags(m.get("tags", []))
    return lineage


#: Minimum normalized length for a containment match — prevents short
#: fragments like 'vl' or 'sam' from swallowing unrelated names.
_FUZZY_MIN_LEN = 6


def match_candidate(org: str, name: str, index: CatalogIndex) -> Optional[str]:
    """Decide whether upstream ``org/name`` is already in the catalog.

    Returns the match method ('upstream_repo' | 'hf_base_model' |
    'name_fuzzy') or None when the candidate is genuinely new.
    """
    repo_key = f"{org}/{name}".lower()

    if repo_key in index.upstream_repos:
        return "upstream_repo"

    if repo_key in index.base_models:
        return "hf_base_model"

    norm = normalize_name(name)
    if norm:
        if norm in index.normalized_names:
            return "name_fuzzy"
        for known in index.normalized_names:
            shorter = min(norm, known, key=len)
            if len(shorter) >= _FUZZY_MIN_LEN and (norm in known or known in norm):
                return "name_fuzzy"

    return None


# ── Candidate scoring (GAP/EDGE/FIRST/DEVICE/QUALITY/COMMUNITY) ──


@dataclass
class PortCandidate:
    """A model that could be ported to Core AI."""
    model_name: str
    org: str
    hf_url: str
    parameters: Optional[str] = None
    license: Optional[str] = None
    last_modified: Optional[str] = None
    downloads: int = 0
    likes: int = 0

    # Scoring
    gap_score: int = 0      # 0-25: does Apple lack this?
    edge_score: int = 0     # 0-20: will it beat MLX?
    first_score: int = 0    # 0-20: first Core AI port?
    device_score: int = 0   # 0-20: fits iPhone?
    quality_score: int = 0  # 0-15: shippable quantization?
    community_score: int = 0  # 0-20: HF popularity

    total_score: int = 0
    rationale: list[str] = field(default_factory=list)
    track: str = "L"  # V (stateless) or L (stateful LLM)
    arch: str = "unknown"
    already_ported: bool = False
    matched_via: Optional[str] = None  # upstream_repo | hf_base_model | name_fuzzy

    def compute_total(self):
        self.total_score = (
            self.gap_score + self.edge_score + self.first_score
            + self.device_score + self.quality_score + self.community_score
        )

    def as_dict(self) -> dict:
        return {
            "model": self.model_name,
            "org": self.org,
            "hf_url": self.hf_url,
            "score": self.total_score,
            "parameters": self.parameters,
            "license": self.license,
            "downloads": self.downloads,
            "arch": self.arch,
            "track": self.track,
            "rationale": self.rationale,
            "already_ported": self.already_ported,
            "matched_via": self.matched_via,
        }


def detect_arch(model_name: str) -> tuple[str, str]:
    """Detect architecture and track from model name."""
    name_lower = model_name.lower()
    for pattern, info in ARCH_PATTERNS.items():
        if pattern in name_lower:
            return info["arch"], info["track"]
    return "unknown", "L"


def estimate_parameters(model_name: str) -> Optional[str]:
    """Try to extract parameter count from model name."""
    match = re.search(r'(\d+\.?\d*)([BM])', model_name, re.IGNORECASE)
    if match:
        return f"{match.group(1)}{match.group(2).upper()}"
    match = re.search(r'E(\d)B', model_name, re.IGNORECASE)
    if match:
        return f"E{match.group(1)}B"
    return None


def fits_iphone(parameters: Optional[str]) -> bool:
    """Check if model likely fits in iPhone's ~6GB practical ceiling."""
    if not parameters:
        return False
    match = re.match(r'(\d+\.?\d*)([BM])', parameters, re.IGNORECASE)
    if not match:
        return False
    value = float(match.group(1))
    unit = match.group(2).upper()
    if unit == "B":
        # int4 quant: ~0.5 bytes per param; iPhone ceiling ~6GB → max ~12B
        return value <= 12
    elif unit == "M":
        return True
    return False


def score_candidate(
    model_name: str,
    org: str,
    model_data: dict,
    index: CatalogIndex,
) -> PortCandidate:
    """Score a model against porting criteria (dedup runs first)."""
    candidate = PortCandidate(
        model_name=model_name,
        org=org,
        hf_url=f"https://huggingface.co/{org}/{model_name}",
        parameters=estimate_parameters(model_name) or model_data.get("parameters"),
        license=model_data.get("license"),
        last_modified=(model_data.get("lastModified") or "")[:10],
        downloads=model_data.get("downloads", 0),
        likes=model_data.get("likes", 0),
    )

    matched_via = match_candidate(org, model_name, index)
    if matched_via:
        candidate.already_ported = True
        candidate.matched_via = matched_via
        return candidate

    candidate.arch, candidate.track = detect_arch(model_name)

    # ── GAP: Does Apple already ship this? ──
    caps = []
    name_l = model_name.lower()
    if any(x in name_l for x in ["chat", "instruct", "llm", "base"]):
        caps.append("chat")
    if any(x in name_l for x in ["whisper", "asr", "speech"]):
        caps.append("transcription")
    if any(x in name_l for x in ["flux", "stable-diffusion", "sd"]):
        caps.append("image-generation")

    has_gap = any(c not in APPLE_STOCK_CAPABILITIES for c in caps)
    if caps and has_gap:
        candidate.gap_score = 20
        candidate.rationale.append("Fills capability gap not in Apple's stock stack")
    elif caps:
        candidate.gap_score = 5
        candidate.rationale.append(
            f"Apple already ships {caps[0]} — only worth it if significantly better"
        )

    # ── FIRST: Is this a first Core AI port of the architecture? ──
    arch_norm = normalize_name(candidate.arch)
    arch_exists = arch_norm != "unknown" and any(
        arch_norm in known for known in index.normalized_names
    )
    if not arch_exists:
        candidate.first_score = 15
        candidate.rationale.append(f"First {candidate.arch} architecture in Core AI")
    else:
        candidate.first_score = 5

    # ── DEVICE: Fits iPhone? ──
    if fits_iphone(candidate.parameters):
        candidate.device_score = 20
        candidate.rationale.append(f"Fits iPhone (~{candidate.parameters} at int4)")
    elif candidate.parameters:
        candidate.device_score = 8
        candidate.rationale.append(f"Mac-only (~{candidate.parameters})")
    else:
        candidate.device_score = 10
        candidate.rationale.append("Size unknown — needs investigation")

    # ── QUALITY: Likely shippable quantization? ──
    if candidate.parameters:
        match = re.match(r'(\d+\.?\d*)([BM])', candidate.parameters, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            if value <= 8:
                candidate.quality_score = 15
                candidate.rationale.append("Small enough for clean int4 quantization")
            elif value <= 30:
                candidate.quality_score = 10
                candidate.rationale.append("Large — needs careful quantization study")
            else:
                candidate.quality_score = 5
                candidate.rationale.append("Very large — Mac-only, challenging quantization")

    # ── COMMUNITY: HF popularity ──
    if candidate.downloads > 100000:
        candidate.community_score = 20
        candidate.rationale.append(f"Very popular ({candidate.downloads:,} downloads)")
    elif candidate.downloads > 10000:
        candidate.community_score = 15
    elif candidate.downloads > 1000:
        candidate.community_score = 10
    elif candidate.downloads > 100:
        candidate.community_score = 5

    # ── EDGE: Will it beat MLX? (heuristic) ──
    if candidate.gap_score >= 20:
        candidate.edge_score = min(20, candidate.first_score + 10)
    elif candidate.gap_score <= 5:
        candidate.edge_score = min(10, candidate.device_score // 2)
    else:
        candidate.edge_score = min(15, candidate.first_score + candidate.device_score // 3)

    candidate.compute_total()
    return candidate


def run_discovery(
    root: Optional[Path] = None,
    device_filter: Optional[str] = None,
    limit: int = 20,
    fetch: Callable = fetch_json,
    orgs: Optional[list[str]] = None,
    resolve_base_models: bool = True,
    index: Optional[CatalogIndex] = None,
) -> list[PortCandidate]:
    """Scan upstream HF orgs and return ranked, deduped porting candidates.

    This is the clean entry point for the future ``coreai-catalog discover``
    subcommand and the weekly workflow. ``fetch`` is injectable for tests;
    ``index`` may be pre-built from fixtures.
    """
    if index is None:
        root = root or find_root()
        artifacts = read_yaml(root / "artifacts.yaml")
        base_models: set[str] = set()
        if resolve_base_models:
            base_models = fetch_artifact_base_models(artifacts, fetch)
        index = build_catalog_index(
            root=root,
            catalog=read_yaml(root / "catalog.yaml"),
            artifacts=artifacts,
            base_models=base_models,
        )

    candidates: list[PortCandidate] = []
    for org in orgs if orgs is not None else UPSTREAM_ORGS:
        data = fetch(
            f"https://huggingface.co/api/models?author={org}"
            "&sort=downloads&direction=-1&limit=15"
        )
        if not data or not isinstance(data, list):
            continue

        for m in data:
            model_name = (m.get("modelId") or m.get("id") or "").replace(f"{org}/", "")
            if not model_name:
                continue

            # Skip non-model entries (datasets, spaces mirrors, etc.)
            tags = m.get("tags", [])
            ml_tags = {"pytorch", "safetensors", "coreml", "onnx"}
            if not any(t in tags for t in ml_tags) and "transformers" not in tags:
                if tags:
                    continue

            candidate = score_candidate(model_name, org, m, index)
            if candidate.already_ported:
                continue
            if device_filter == "iphone" and not fits_iphone(candidate.parameters):
                continue
            candidates.append(candidate)

    candidates.sort(key=lambda c: (-c.total_score, -c.downloads))
    return candidates[:limit]


# ── Renderers ──

#: Stable marker embedded in the pinned-issue body so the upsert workflow
#: (and humans) can recognize the ONE managed issue. Never open duplicates.
PINNED_ISSUE_MARKER = "<!-- coreai-catalog:porting-candidates -->"
PINNED_ISSUE_TITLE = "Porting candidates"
PINNED_ISSUE_LABEL = "porting-candidates"


def render_json(candidates: list[PortCandidate]) -> str:
    return json.dumps([c.as_dict() for c in candidates], indent=2, ensure_ascii=False)


def render_markdown(
    candidates: list[PortCandidate],
    scan_date: Optional[str] = None,
    catalog_count: Optional[int] = None,
) -> str:
    """Render the pinned "Porting candidates" issue body (idempotent upsert)."""
    lines = [
        PINNED_ISSUE_MARKER,
        f"# {PINNED_ISSUE_TITLE}",
        "",
        f"**Scan date:** {scan_date or date.today().isoformat()}",
    ]
    if catalog_count is not None:
        lines.append(f"**Catalog:** {catalog_count} models")
    lines += [
        "",
        "Ranked upstream models worth porting to Core AI. This issue is",
        "**upserted in place** by `.github/workflows/discover.yml` (weekly) —",
        "do not open duplicate issues; the next scan overwrites this body.",
        "",
    ]

    if not candidates:
        lines.append("No porting candidates found — all scanned upstream "
                     "models are already in the catalog.")
        return "\n".join(lines)

    lines += [
        "| Score | Model | Org | Arch | Size | Track | Downloads | License |",
        "|---:|---|---|---|---|---|---:|---|",
    ]
    for c in candidates:
        lines.append(
            f"| {c.total_score} | [{c.model_name}]({c.hf_url}) | {c.org} "
            f"| {c.arch} | {c.parameters or '?'} | {c.track} "
            f"| {c.downloads:,} | {c.license or '?'} |"
        )

    lines += ["", "## Top candidate details", ""]
    for c in candidates[:5]:
        lines.append(f"### {c.model_name} ({c.org}) — {c.total_score}/120")
        lines.append(f"- HF: {c.hf_url}")
        track = "V (stateless, easier)" if c.track == "V" else "L (stateful LLM, harder)"
        lines.append(f"- Track: {track}")
        if c.parameters:
            lines.append(f"- Size: ~{c.parameters}")
        for r in c.rationale:
            lines.append(f"- {r}")
        lines.append("")

    lines += [
        "## Scoring criteria (from the Zoo's PORTING.md gates)",
        "",
        "- GAP (0-25): fills capability not in Apple's stock stack",
        "- EDGE (0-20): likely better than MLX alternative",
        "- FIRST (0-20): first Core AI port of this architecture",
        "- DEVICE (0-20): fits iPhone (~6GB ceiling)",
        "- QUALITY (0-15): shippable quantization plausible",
        "- COMMUNITY (0-20): Hugging Face popularity",
        "",
        "Dedup layers: authored `upstream_repo` field → HF `base_model` "
        "metadata → normalized-name fuzzy fallback.",
        "",
        "### How to port a candidate",
        "",
        "These are models that could be converted, not yet how. Convert one with "
        "**[coreai-fabric](https://github.com/kevinqz/coreai-fabric)** — the agent-first "
        "conversion pipeline: `coreai-fabric new <hf_repo>` scaffolds a recipe, then "
        "`convert → verify → publish → register` opens the catalog PR. The artifact "
        "lands in your own Hugging Face namespace; this catalog only indexes it.",
    ]
    return "\n".join(lines)


def format_report(candidates: list[PortCandidate]) -> str:
    """Terminal report (kept for scripts/discover.py human output)."""
    if not candidates:
        return ("No porting candidates found. All upstream models are "
                "already in the catalog.")

    lines = [
        "Core AI Porting Candidates",
        "=" * 60,
        "",
        f"{'Score':>5}  {'Model':45s} {'Arch':12s} {'Size':8s} {'Track':5s}  Downloads",
        "-" * 100,
    ]
    for c in candidates:
        size = c.parameters or "?"
        lines.append(
            f"{c.total_score:>5}  {c.model_name[:44]:45s} {c.arch:12s} {size:8s} "
            f"{c.track:5s}  {c.downloads:>8,}"
        )

    lines += ["", "Top candidate details:", ""]
    for c in candidates[:5]:
        lines.append(f"  {c.model_name} ({c.org}) — Score: {c.total_score}/120")
        lines.append(f"    HF: {c.hf_url}")
        lines.append(
            "    Track: "
            + ("V (stateless, easier)" if c.track == "V" else "L (stateful LLM, harder)")
        )
        if c.parameters:
            lines.append(f"    Size: ~{c.parameters}")
        lines.append("    Rationale:")
        for r in c.rationale:
            lines.append(f"      • {r}")
        lines.append("")

    lines += [
        "Scoring criteria (based on Zoo's PORTING.md gates):",
        "  GAP (0-25): fills capability not in Apple's stock stack",
        "  EDGE (0-20): likely better than MLX alternative",
        "  FIRST (0-20): first Core AI port of this architecture",
        "  DEVICE (0-20): fits iPhone (~6GB ceiling)",
        "  QUALITY (0-15): shippable quantization plausible",
        "  COMMUNITY (0-20): HuggingFace popularity",
    ]
    return "\n".join(lines)


# ── Issue-form parsing (model-request.yml → contribute fields, F6) ──

#: Maps the issue form's rendered "### <label>" headings to the field names
#: consumed by coreai_catalog.contribute.build_model_entry /
#: build_artifact_entry. kind: str | csv | bool3 (true/false/unknown).
#: The labels here MUST match .github/ISSUE_TEMPLATE/model-request.yml —
#: tests/test_p1_discovery.py asserts the two stay in sync.
FORM_FIELDS: list[tuple[str, str, str]] = [
    ("Model ID", "id", "str"),
    ("Display name", "name", "str"),
    ("Family", "family", "str"),
    ("Source group", "source_group", "str"),
    ("Source path (URL)", "source_path", "str"),
    ("Artifact ref", "artifact_ref", "str"),
    ("Capabilities", "capabilities", "csv"),
    ("Input modalities", "input_modalities", "csv"),
    ("Output modalities", "output_modalities", "csv"),
    ("Artifact format", "artifact_format", "str"),
    ("Artifact availability", "availability", "str"),
    ("Parameters", "parameters", "str"),
    ("Precision", "precision", "str"),
    ("Quantization", "quantization", "str"),
    ("Artifact size", "artifact_size", "str"),
    ("Runtime name", "runtime_name", "str"),
    ("Runner", "runner", "str"),
    ("Stock runtime", "stock_runtime", "bool3"),
    ("Custom kernel required", "custom_kernel", "bool3"),
    ("Patch required", "patch_required", "bool3"),
    ("Tokenizer required", "tokenizer_required", "bool3"),
    ("Processor required", "processor_required", "bool3"),
    ("AOT required", "aot_required", "bool3"),
    ("iPhone support", "iphone", "bool3"),
    ("iPad support", "ipad", "bool3"),
    ("Mac support", "mac", "bool3"),
    ("Mac only", "mac_only", "bool3"),
    ("License name", "license_name", "str"),
    ("Commercial use", "commercial_use", "str"),
    ("Status", "status", "str"),
    ("Maturity", "maturity", "str"),
    ("Confidence", "confidence", "str"),
    ("Sources", "sources", "csv"),
    ("Upstream repo", "upstream_repo", "str"),
    ("Hugging Face owner", "hf_owner", "str"),
    ("Hugging Face repo", "hf_repo", "str"),
    ("GitHub owner", "github_owner", "str"),
    ("GitHub repo", "github_repo", "str"),
    ("GitHub path", "github_path", "str"),
    ("Notes", "notes", "str"),
]

#: Fields the parser may leave absent without blocking validation
#: (defaults applied in issue_form_to_fields, or genuinely optional).
_OPTIONAL_FORM_FIELDS = {
    "artifact_ref", "upstream_repo", "notes",
    "github_owner", "github_repo", "github_path",
    "hf_owner", "hf_repo",
}

_NO_RESPONSE = "_No response_"


def parse_issue_form(body: str) -> dict[str, str]:
    """Parse a rendered GitHub issue-form body into {heading: value}.

    Issue forms render as ``### <label>\\n\\n<value>`` blocks; empty
    optional fields render as ``_No response_``.
    """
    sections: dict[str, str] = {}
    current: Optional[str] = None
    buf: list[str] = []
    for line in (body or "").splitlines():
        if line.startswith("### "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[4:].strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return {
        k: v for k, v in sections.items()
        if v and v != _NO_RESPONSE
    }


def _coerce_bool3(value: str):
    v = value.strip().lower()
    if v == "true":
        return True
    if v == "false":
        return False
    return "unknown"


def issue_form_to_fields(parsed: dict[str, str]) -> tuple[dict, list[str]]:
    """Convert parsed form sections into contribute-toolkit fields.

    Returns (fields, problems). Problems are missing required form fields —
    aggregated, never fail-fast (finding A9/F3 discipline). Defaults:
    ``artifact_ref`` ← id, ``last_verified`` ← today, ``notes`` ← None.
    Nothing else is ever invented.
    """
    fields: dict = {}
    problems: list[str] = []
    for label, name, kind in FORM_FIELDS:
        raw = parsed.get(label)
        if raw is None:
            if name not in _OPTIONAL_FORM_FIELDS:
                problems.append(f"missing required form field: '{label}'")
            continue
        if kind == "csv":
            values = [v.strip() for v in re.split(r"[,\n]", raw) if v.strip()]
            if not values:
                problems.append(f"empty required form field: '{label}'")
                continue
            fields[name] = values
        elif kind == "bool3":
            fields[name] = _coerce_bool3(raw)
        else:
            fields[name] = raw.strip()

    if not fields.get("hf_owner") or not fields.get("hf_repo"):
        if not (fields.get("github_owner") and fields.get("github_repo")):
            problems.append(
                "artifact host missing: provide 'Hugging Face owner' + "
                "'Hugging Face repo' (or 'GitHub owner' + 'GitHub repo'). "
                "If no .aimodel artifact exists yet, the catalog can't index it — "
                "convert it first with coreai-fabric "
                "(https://github.com/kevinqz/coreai-fabric): it publishes the "
                "artifact to your own Hugging Face and opens the catalog PR for you."
            )

    fields.setdefault("artifact_ref", fields.get("id"))
    fields.setdefault("last_verified", date.today().isoformat())
    fields.setdefault("notes", None)
    return fields, problems


def process_model_request(body: str, root: Optional[Path] = None) -> dict:
    """Full issue-form pipeline: parse → assemble entries → validate.

    Mirrors ``coreai-catalog contribute model --dry-run`` (same validation
    core, aggregated errors) so the model-request-to-pr workflow and the
    CLI give identical verdicts. Returns::

        {ok, problems: [str], errors: [structured error dicts],
         fields, model_entry, artifact_entry}

    Nothing is written — the caller decides whether to stage a draft PR.
    """
    from . import contribute as contrib

    root = root or find_root()
    parsed = parse_issue_form(body)
    fields, problems = issue_form_to_fields(parsed)
    if problems:
        return {
            "ok": False, "problems": problems, "errors": [],
            "fields": fields, "model_entry": None, "artifact_entry": None,
        }

    model_entry = contrib.build_model_entry(fields)
    artifact_entry = contrib.build_artifact_entry(fields)
    if fields.get("upstream_repo"):
        # Authored upstream lineage (org/name) — powers discovery dedup.
        # Gated on schema support: the field is being introduced in
        # schema/model.schema.json (additionalProperties: false would
        # otherwise reject it); once the schema carries it, submissions
        # flow through automatically.
        model_schema = contrib.load_schema("model", root)
        if "upstream_repo" in (model_schema.get("properties") or {}):
            model_entry["upstream_repo"] = fields["upstream_repo"]

    base_ctx = contrib.ids_context(root)
    xref_ctx = {k: set(v) for k, v in base_ctx.items()}
    xref_ctx["artifact_ids"].add(artifact_entry["id"])

    errors: list[dict] = []
    for kind, entry in (("model", model_entry), ("artifact", artifact_entry)):
        errors.extend(contrib.schema_errors(kind, entry, root))
        errors.extend(contrib.cross_reference_errors(kind, entry, xref_ctx))
        dup = contrib.duplicate_id_error(kind, entry, base_ctx)
        if dup:
            errors.append(dup)

    return {
        "ok": not errors,
        "problems": [],
        "errors": errors,
        "fields": fields,
        "model_entry": model_entry,
        "artifact_entry": artifact_entry,
    }
