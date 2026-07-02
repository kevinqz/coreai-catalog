#!/usr/bin/env python3
"""Verify Ed25519 signature on a benchmark JSONL line.

The relay signs each payload before opening a PR. This script verifies
that signature so direct PRs (bypassing the relay) are rejected.

Usage:
    python scripts/verify_benchmark_signature.py <jsonl_line_or_file>

Exit codes:
    0 — signature valid
    1 — signature invalid or missing
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)
from cryptography.hazmat.primitives.serialization import load_pem_public_key

ROOT = Path(__file__).resolve().parents[1]
PUBKEY_PATH = ROOT / ".github" / "relay-pubkey.pem"


def verify_line(line: str, pubkey_path: Path = PUBKEY_PATH) -> tuple[bool, str]:
    """Verify a single JSONL line's _signature field.

    Returns (success, message).
    """
    line = line.strip().lstrip("+")
    if not line:
        return False, "Empty line"

    try:
        entry = json.loads(line)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"

    signature_hex = entry.pop("_signature", None)
    if not signature_hex:
        return False, "No _signature field — direct PRs must go through the relay"

    # Re-serialize without _signature for verification
    payload = json.dumps(entry, sort_keys=True).encode()

    # Load public key
    if not pubkey_path.exists():
        return False, f"Public key not found at {pubkey_path}"
    public_key = load_pem_public_key(pubkey_path.read_bytes())

    try:
        sig_bytes = bytes.fromhex(signature_hex)
    except ValueError:
        return False, f"Invalid signature hex: {signature_hex[:20]}..."

    try:
        public_key.verify(sig_bytes, payload)
        return True, "Signature verified"
    except Exception:
        return False, "Signature verification failed"


def main():
    if len(sys.argv) < 2:
        print("Usage: verify_benchmark_signature.py <jsonl_line_or_file>", file=sys.stderr)
        sys.exit(1)

    arg = sys.argv[1]
    if Path(arg).exists():
        lines = Path(arg).read_text().strip().splitlines()
    else:
        lines = [arg]

    all_valid = True
    for i, line in enumerate(lines):
        success, msg = verify_line(line)
        status = "OK" if success else "FAIL"
        print(f"  Line {i+1}: {status} — {msg}")
        if not success:
            all_valid = False

    if all_valid:
        print("All signatures valid")
        sys.exit(0)
    else:
        print("Signature verification failed", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
