#!/usr/bin/env python3
"""Verify an Apple DeviceCheck JWT token.

This script verifies that a benchmark submission came from genuine Apple
hardware by calling Apple's DeviceCheck API. It requires the Apple Team ID,
Key ID, and private key (ES256) configured as environment variables.

Usage:
    DEVICECHECK_TEAM_ID=... DEVICECHECK_KEY_ID=... DEVICECHECK_PRIVATE_KEY=... \
    python scripts/verify_devicecheck.py <device_token> <transaction_id>

Exit codes:
    0 — token is valid (real device)
    1 — token is invalid or verification failed

Environment variables:
    DEVICECHECK_TEAM_ID     — Apple Developer Team ID
    DEVICECHECK_KEY_ID      — DeviceCheck key ID from Apple Developer portal
    DEVICECHECK_PRIVATE_KEY — ES256 private key (PEM format, from Apple)

Note: In Phase 3, this runs in the CF Worker (not the GitHub Action) because
the Apple private key can't be in the public repo. The Worker verifies and
sets device_verified: true in the signed payload. The Action trusts the
Ed25519 relay signature as proof that the Worker verified DeviceCheck.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


def generate_apple_jwt(team_id: str, key_id: str, private_key_pem: str) -> str:
    """Generate a JWT for Apple's DeviceCheck API using ES256.

    The JWT authenticates our app to Apple's server.
    """
    import base64
    import hashlib

    header = {"alg": "ES256", "kid": key_id, "typ": "JWT"}
    payload = {
        "iss": team_id,
        "iat": int(time.time()),
        "aud": "devicecheck-apple",
    }

    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(d, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()

    header_b64 = b64(header)
    payload_b64 = b64(payload)
    signing_input = f"{header_b64}.{payload_b64}".encode()

    # Sign with ES256
    from cryptography.hazmat.primitives.asymmetric.ec import (
        ECDSA, EllipticCurvePrivateKey,
    )
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    key = load_pem_private_key(private_key_pem.encode(), password=None)
    if not isinstance(key, EllipticCurvePrivateKey):
        raise ValueError("Private key must be EC (ES256), got wrong key type")

    der_sig = key.sign(signing_input, ECDSA(hashes.SHA256()))

    # Convert DER to raw r||s (64 bytes)
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    r, s = decode_dss_signature(der_sig)
    raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    sig_b64 = base64.urlsafe_b64encode(raw_sig).rstrip(b"=").decode()

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_devicecheck_token(
    device_token: str,
    transaction_id: str,
    team_id: str,
    key_id: str,
    private_key_pem: str,
) -> tuple[bool, str]:
    """Call Apple's DeviceCheck API to validate a device token.

    Returns (is_valid, message).
    """
    jwt = generate_apple_jwt(team_id, key_id, private_key_pem)

    payload = json.dumps({
        "device_token": device_token,
        "transaction_id": transaction_id,
        "timestamp": int(time.time() * 1000),
    }).encode()

    req = urllib.request.Request(
        "https://api.developer.apple.com/devicecheck/validate_token",
        data=payload,
        headers={
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read())
            if result.get("status") == "valid":
                return True, "Device verified"
            else:
                return False, f"Apple API status: {result.get('status', 'unknown')}"
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return False, f"HTTP {e.code}: {body}"
    except Exception as e:
        return False, f"Error: {e}"


def main() -> int:
    team_id = os.environ.get("DEVICECHECK_TEAM_ID", "")
    key_id = os.environ.get("DEVICECHECK_KEY_ID", "")
    private_key = os.environ.get("DEVICECHECK_PRIVATE_KEY", "")

    if not all([team_id, key_id, private_key]):
        print("Error: DEVICECHECK_TEAM_ID, DEVICECHECK_KEY_ID, and "
              "DEVICECHECK_PRIVATE_KEY must be set", file=sys.stderr)
        return 1

    if len(sys.argv) < 3:
        print("Usage: verify_devicecheck.py <device_token> <transaction_id>",
              file=sys.stderr)
        return 1

    device_token = sys.argv[1]
    transaction_id = sys.argv[2]

    valid, message = verify_devicecheck_token(
        device_token, transaction_id, team_id, key_id, private_key
    )

    if valid:
        print(f"✅ {message}")
        return 0
    else:
        print(f"❌ {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
