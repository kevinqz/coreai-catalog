#!/usr/bin/env python3
"""Verify the signature on a benchmark JSONL line.

Two accepted schemes over the SAME canonical payload
(json.dumps(entry_without_signature, sort_keys=True).encode()):

1. Legacy Ed25519 relay: `_signature` is a hex string produced by the
   relay's private key; verified against .github/relay-pubkey.pem.
   Kept working for the existing relay pipeline.

2. Sigstore keyless bundle (scripts/sign_benchmark.py): `_signature` is
   a JSON object (a sigstore bundle). Verification checks the Fulcio
   certificate chain, the Rekor transparency-log inclusion proof and the
   signature, and requires the certificate's OIDC issuer to be GitHub
   (Actions or OAuth). The verified identity is EXPOSED (stdout
   `identity=` / `github_login=` lines and, when $GITHUB_OUTPUT is set,
   as step outputs) so CI can compare it to the PR author — that
   comparison is what replaces the single-relay-key trust model (D4).

   Identity mapping: a GitHub-Actions-signed bundle carries a SAN like
   https://github.com/<login>/<repo>/.github/workflows/...@<ref>, from
   which `github_login` is derived. A browser-flow bundle carries an
   e-mail SAN; `github_login` stays empty and CI routes the PR to the
   curator lane instead of auto-merging.

Usage:
    python scripts/verify_benchmark_signature.py <jsonl_line_or_file>
        [--expect-identity LOGIN] [--require-scheme {any,ed25519,sigstore}]

Exit codes:
    0 — signature valid (and identity matches, if --expect-identity)
    1 — signature invalid, missing, or identity mismatch
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.serialization import load_pem_public_key

ROOT = Path(__file__).resolve().parents[1]
PUBKEY_PATH = ROOT / ".github" / "relay-pubkey.pem"

# OIDC issuers accepted for sigstore bundles.
GITHUB_ACTIONS_ISSUER = "https://token.actions.githubusercontent.com"
GITHUB_OAUTH_ISSUER = "https://github.com/login/oauth"
SIGSTORE_OAUTH_ISSUER = "https://oauth2.sigstore.dev/auth"
ACCEPTED_ISSUERS = (GITHUB_ACTIONS_ISSUER, GITHUB_OAUTH_ISSUER, SIGSTORE_OAUTH_ISSUER)


def canonical_payload(entry: dict) -> bytes:
    """Canonical signing payload, shared by both schemes."""
    stripped = {k: v for k, v in entry.items() if k != "_signature"}
    return json.dumps(stripped, sort_keys=True).encode()


def github_login_from_identity(identity: str | None) -> str | None:
    """Derive a GitHub login from a Fulcio certificate identity.

    GitHub-Actions identities look like
    https://github.com/<login>/<repo>/.github/workflows/<wf>.yml@<ref>.
    E-mail identities (browser flow) return None — an e-mail cannot be
    mapped to a GitHub login without an extra lookup, so CI treats those
    as curator-lane submissions.
    """
    if not identity:
        return None
    m = re.match(r"^https://github\.com/([^/]+)/[^/]+/", identity)
    return m.group(1) if m else None


def _verify_ed25519(payload: bytes, signature_hex: str,
                    pubkey_path: Path) -> tuple[bool, str]:
    """Legacy relay scheme: hex Ed25519 signature over the payload."""
    if not pubkey_path.exists():
        return False, f"Public key not found at {pubkey_path}"
    public_key = load_pem_public_key(pubkey_path.read_bytes())

    try:
        sig_bytes = bytes.fromhex(signature_hex)
    except ValueError:
        return False, f"Invalid signature hex: {signature_hex[:20]}..."

    try:
        public_key.verify(sig_bytes, payload)
        return True, "Ed25519 relay signature verified"
    except Exception:
        return False, "Signature verification failed"


def _verify_sigstore(payload: bytes, bundle_dict: dict,
                     offline: bool = False) -> tuple[bool, str, str | None]:
    """Sigstore scheme. Returns (valid, message, identity).

    Never raises: malformed bundles are rejected with a clean message.
    """
    try:
        from sigstore.models import Bundle
        from sigstore.verify import Verifier, policy
    except ImportError:
        return False, "sigstore package not installed (pip install sigstore)", None

    try:
        bundle = Bundle.from_json(json.dumps(bundle_dict))
    except Exception as e:
        return False, f"Invalid sigstore bundle: {e}", None

    # Extract the certificate identity up front so failures still report
    # who *claimed* to sign.
    identity: str | None = None
    try:
        cert = bundle.signing_certificate
        san = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
        uris = san.get_values_for_type(x509.UniformResourceIdentifier)
        emails = san.get_values_for_type(x509.RFC822Name)
        identity = (uris or emails or [None])[0]
    except Exception:
        pass

    try:
        verifier = Verifier.production(offline=offline)
        # Accept any identity from a GitHub-tied issuer; the *identity ==
        # PR author* comparison happens in CI, not here.
        pol = policy.AnyOf([policy.OIDCIssuer(iss) for iss in ACCEPTED_ISSUERS])
        verifier.verify_artifact(payload, bundle, pol)
        return True, f"Sigstore bundle verified (identity: {identity})", identity
    except Exception as e:
        return False, f"Sigstore verification failed: {e}", identity


def verify_line_detailed(line: str, pubkey_path: Path = PUBKEY_PATH,
                         offline: bool = False) -> dict:
    """Verify a single JSONL line's `_signature` field.

    Returns {"valid": bool, "scheme": "ed25519"|"sigstore"|None,
             "message": str, "identity": str|None, "github_login": str|None}.
    """
    result = {"valid": False, "scheme": None, "message": "",
              "identity": None, "github_login": None}

    line = line.strip().lstrip("+")
    if not line:
        result["message"] = "Empty line"
        return result

    try:
        entry = json.loads(line)
    except json.JSONDecodeError as e:
        result["message"] = f"Invalid JSON: {e}"
        return result

    signature = entry.pop("_signature", None)
    if not signature:
        result["message"] = (
            "No _signature field — sign with scripts/sign_benchmark.py "
            "(sigstore keyless) or submit through the relay"
        )
        return result

    payload = canonical_payload(entry)

    if isinstance(signature, dict):
        result["scheme"] = "sigstore"
        valid, msg, identity = _verify_sigstore(payload, signature, offline=offline)
        result.update(valid=valid, message=msg, identity=identity,
                      github_login=github_login_from_identity(identity))
    elif isinstance(signature, str):
        result["scheme"] = "ed25519"
        valid, msg = _verify_ed25519(payload, signature, pubkey_path)
        result.update(valid=valid, message=msg)
    else:
        result["message"] = f"Unsupported _signature type: {type(signature).__name__}"
    return result


def verify_line(line: str, pubkey_path: Path = PUBKEY_PATH) -> tuple[bool, str]:
    """Back-compat wrapper: returns (success, message)."""
    r = verify_line_detailed(line, pubkey_path)
    return r["valid"], r["message"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify benchmark entry signatures")
    parser.add_argument("input", help="A JSONL line or a file containing JSONL lines")
    parser.add_argument("--expect-identity",
                        help="Fail unless the verified github_login equals this login (case-insensitive)")
    parser.add_argument("--require-scheme", choices=("any", "ed25519", "sigstore"), default="any",
                        help="Restrict which signature scheme is acceptable")
    parser.add_argument("--offline", action="store_true",
                        help="Skip TUF refresh; use cached/embedded trust root (sigstore only)")
    args = parser.parse_args()

    if Path(args.input).exists():
        lines = Path(args.input).read_text().strip().splitlines()
    else:
        lines = [args.input]

    all_valid = True
    last: dict = {}
    for i, line in enumerate(lines):
        r = verify_line_detailed(line, offline=args.offline)
        last = r
        ok = r["valid"]

        if ok and args.require_scheme != "any" and r["scheme"] != args.require_scheme:
            ok = False
            r["message"] += f" — but scheme '{r['scheme']}' not allowed (require {args.require_scheme})"

        if ok and args.expect_identity:
            login = r["github_login"] or ""
            if login.lower() != args.expect_identity.lower():
                ok = False
                r["message"] += (
                    f" — identity mismatch: signer github_login="
                    f"{r['github_login']!r}, expected {args.expect_identity!r}"
                )

        status = "OK" if ok else "FAIL"
        print(f"  Line {i+1}: {status} — {r['message']}")
        if not ok:
            all_valid = False

    # Expose the verified identity for CI (last line's identity).
    print(f"scheme={last.get('scheme') or ''}")
    print(f"identity={last.get('identity') or ''}")
    print(f"github_login={last.get('github_login') or ''}")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"scheme={last.get('scheme') or ''}\n")
            f.write(f"identity={last.get('identity') or ''}\n")
            f.write(f"github_login={last.get('github_login') or ''}\n")

    if all_valid:
        print("All signatures valid")
        return 0
    print("Signature verification failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
