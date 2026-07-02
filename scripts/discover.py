#!/usr/bin/env python3
"""Discover: analyze upstream model landscape and prioritize porting candidates.

Uses the Zoo's GAP/EDGE/FIRST/DEVICE/QUALITY criteria to score which models
are worth porting to Core AI. This is the "what should I bring next?" command.

Usage:
    coreai-catalog discover                    # full scan
    coreai-catalog discover --device iphone    # iPhone-capable only
    coreai-catalog discover --json             # JSON output
    coreai-catalog discover --limit 10         # top 10 candidates
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

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

    def compute_total(self):
        self.total_score = (
            self.gap_score + self.edge_score + self.first_score
            + self.device_score + self.quality_score + self.community_score
        )


def load_existing_models() -> set[str]:
    """Load model IDs and names from catalog.yaml."""
    import yaml
    catalog_path = ROOT / "catalog.yaml"
    if not catalog_path.exists():
        return set()
    data = yaml.safe_load(catalog_path.read_text()) or {}
    ids = set()
    for m in data.get("models", []):
        ids.add(m.get("id", "").lower())
        # Also add the base name for fuzzy matching
        name = m.get("name", "").lower()
        if name:
            ids.add(name)
    return ids


def load_existing_hf_repos() -> set[str]:
    """Load HF repo names from artifacts.yaml."""
    import yaml
    artifacts_path = ROOT / "artifacts.yaml"
    if not artifacts_path.exists():
        return set()
    data = yaml.safe_load(artifacts_path.read_text()) or {}
    repos = set()
    for a in data.get("artifacts", []):
        hf = a.get("huggingface", {})
        repo = hf.get("repo", "")
        if repo:
            repos.add(repo.lower())
    return repos


def fetch_json(url: str, timeout: int = 15) -> list | dict | None:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def detect_arch(model_name: str) -> tuple[str, str]:
    """Detect architecture and track from model name."""
    name_lower = model_name.lower()
    for pattern, info in ARCH_PATTERNS.items():
        if pattern in name_lower:
            return info["arch"], info["track"]
    return "unknown", "L"


def estimate_parameters(model_name: str) -> Optional[str]:
    """Try to extract parameter count from model name."""
    # Match patterns like "7B", "1.5B", "350M", "0.8B", "E2B"
    match = re.search(r'(\d+\.?\d*)([BM])', model_name, re.IGNORECASE)
    if match:
        return f"{match.group(1)}{match.group(2).upper()}"

    # Effective params notation (E2B, E4B)
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
        # int4 quant: ~0.5 bytes per param → param_count * 0.5 = GB
        # iPhone ceiling ~6GB → max ~12B at int4
        return value <= 12
    elif unit == "M":
        return True  # Any M model fits
    return False


def score_candidate(
    model_name: str,
    org: str,
    model_data: dict,
    existing_ids: set[str],
    existing_repos: set[str],
) -> PortCandidate:
    """Score a model against porting criteria."""
    candidate = PortCandidate(
        model_name=model_name,
        org=org,
        hf_url=f"https://huggingface.co/{org}/{model_name}",
        parameters=estimate_parameters(model_name) or model_data.get("parameters"),
        license=model_data.get("license"),
        last_modified=model_data.get("lastModified", "")[:10],
        downloads=model_data.get("downloads", 0),
        likes=model_data.get("likes", 0),
    )

    # Check if already ported
    name_lower = model_name.lower()
    repo_key = f"{org.lower()}/{name_lower}"
    if name_lower in existing_ids or repo_key in existing_repos:
        candidate.already_ported = True
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
        candidate.rationale.append(f"Apple already ships {caps[0]} — only worth it if significantly better")

    # ── FIRST: Is this a first Core AI port? ──
    # Check if any existing catalog model has this arch
    arch_exists = any(candidate.arch.lower() in eid for eid in existing_ids)
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
    # High edge = first-of-kind or fills a real gap
    # Low edge = Apple already ships this capability
    if candidate.gap_score >= 20:
        # Real gap → likely has edge
        candidate.edge_score = min(20, candidate.first_score + 10)
    elif candidate.gap_score <= 5:
        # Apple already ships this → need to be significantly better
        candidate.edge_score = min(10, candidate.device_score // 2)
    else:
        candidate.edge_score = min(15, candidate.first_score + candidate.device_score // 3)

    candidate.compute_total()
    return candidate


def run_discover(
    device_filter: Optional[str] = None,
    limit: int = 20,
) -> list[PortCandidate]:
    """Run the discover scan.

    Returns a list of PortCandidate sorted by total_score descending.
    """
    existing_ids = load_existing_models()
    existing_repos = load_existing_hf_repos()

    candidates: list[PortCandidate] = []

    for org in UPSTREAM_ORGS:
        # Fetch top models by downloads (no filter — we classify ourselves)
        data = fetch_json(
            f"https://huggingface.co/api/models?author={org}"
            "&sort=downloads&direction=-1&limit=15"
        )
        if not data or not isinstance(data, list):
            continue

        for m in data:
            model_name = m.get("modelId", "").replace(f"{org}/", "")
            if not model_name:
                continue

            # Skip non-model entries
            tags = m.get("tags", [])
            ml_tags = {"pytorch", "safetensors", "coreml", "onnx"}
            if not any(t in tags for t in ml_tags) and "transformers" not in tags:
                # Only skip if we have tags to check against
                if tags:
                    continue

            candidate = score_candidate(
                model_name, org, m, existing_ids, existing_repos
            )

            if candidate.already_ported:
                continue

            if device_filter == "iphone" and not fits_iphone(candidate.parameters):
                continue

            candidates.append(candidate)

    # Sort by score descending, then by downloads
    candidates.sort(key=lambda c: (-c.total_score, -c.downloads))
    return candidates[:limit]


def format_report(candidates: list[PortCandidate]) -> str:
    """Format as human-readable report."""
    if not candidates:
        return "No porting candidates found. All upstream models are already in the catalog."

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

    lines.append("")
    lines.append("Top candidate details:")
    lines.append("")

    for c in candidates[:5]:
        lines.append(f"  {c.model_name} ({c.org}) — Score: {c.total_score}/120")
        lines.append(f"    HF: {c.hf_url}")
        lines.append(f"    Track: {'V (stateless, easier)' if c.track == 'V' else 'L (stateful LLM, harder)'}")
        if c.parameters:
            lines.append(f"    Size: ~{c.parameters}")
        lines.append(f"    Rationale:")
        for r in c.rationale:
            lines.append(f"      • {r}")
        lines.append("")

    lines.append("Scoring criteria (based on Zoo's PORTING.md gates):")
    lines.append("  GAP (0-25): fills capability not in Apple's stock stack")
    lines.append("  EDGE (0-20): likely better than MLX alternative")
    lines.append("  FIRST (0-20): first Core AI port of this architecture")
    lines.append("  DEVICE (0-20): fits iPhone (~6GB ceiling)")
    lines.append("  QUALITY (0-15): shippable quantization plausible")
    lines.append("  COMMUNITY (0-20): HuggingFace popularity")

    return "\n".join(lines)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Discover models worth porting to Core AI"
    )
    parser.add_argument("--device", choices=["iphone", "mac"], help="Filter by device")
    parser.add_argument("--limit", type=int, default=20, help="Max results")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    candidates = run_discover(device_filter=args.device, limit=args.limit)

    if args.json:
        print(json.dumps([{
            "model": c.model_name,
            "org": c.org,
            "hf_url": c.hf_url,
            "score": c.total_score,
            "parameters": c.parameters,
            "arch": c.arch,
            "track": c.track,
            "rationale": c.rationale,
        } for c in candidates], indent=2, ensure_ascii=False))
    else:
        print(format_report(candidates))

    return 0


if __name__ == "__main__":
    sys.exit(main())
