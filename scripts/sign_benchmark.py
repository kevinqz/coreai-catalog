#!/usr/bin/env python3
"""Sign a benchmark run-manifest with sigstore keyless signing.

This replaces the private-relay Ed25519 single key (redteam finding D4)
with per-submitter identities: the signature is bound to YOUR OIDC
identity via a short-lived Fulcio certificate, and logged in Rekor's
append-only transparency log. CI (benchmark-validate.yml) verifies the
bundle and compares the certificate identity to the PR author before
auto-merging (findings B2/B3/F1).

The canonical payload is byte-identical to the legacy relay scheme:
    json.dumps(entry_without_signature, sort_keys=True).encode()
so one verifier (scripts/verify_benchmark_signature.py) handles both.

Two signing flows, no key material to manage in either:

1. GitHub Actions (ambient OIDC — the recommended, identity-binding
   flow). Run this script inside a workflow in YOUR OWN repository with:

       permissions:
         id-token: write
       ...
       - run: pip install sigstore pyyaml
       - run: python scripts/sign_benchmark.py my-entry.json >> benchmarks.jsonl

   The Fulcio certificate then embeds
   https://github.com/<your-login>/<repo>/.github/workflows/...@<ref>
   as its identity, which CI maps to your GitHub login and compares to
   the PR author.

2. Local browser flow: run the same command on your Mac; a browser
   window opens for the sigstore OAuth flow (GitHub is one of the
   supported identity providers). The certificate identity is then the
   e-mail of the account you authenticated with — CI cannot map an
   e-mail to a PR author automatically, so browser-signed submissions
   land in the curator lane instead of auto-merging.

Usage:
    python scripts/sign_benchmark.py <entry.json | jsonl_line> [--bundle-out FILE] [--staging]

Output: the entry with `_signature` set to the sigstore bundle (a JSON
object — the verifier distinguishes it from the legacy hex string),
printed as one JSONL line ready to append to benchmarks.jsonl.

Exit codes:
    0 — signed successfully
    1 — signing failed (no OIDC identity available, network, bad input)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# sigstore's public OAuth issuer used for the interactive browser flow.
PRODUCTION_OAUTH_ISSUER = "https://oauth2.sigstore.dev/auth"
STAGING_OAUTH_ISSUER = "https://oauth2.sigstage.dev/auth"


def canonical_payload(entry: dict) -> bytes:
    """Canonical signing payload — identical to the legacy relay scheme."""
    stripped = {k: v for k, v in entry.items() if k != "_signature"}
    return json.dumps(stripped, sort_keys=True).encode()


def sign_entry(entry: dict, staging: bool = False) -> dict:
    """Sign an entry's canonical payload; return a copy with `_signature`
    set to the sigstore bundle dict.

    Raises RuntimeError with an actionable message on failure.
    """
    try:
        from sigstore.models import ClientTrustConfig
        from sigstore.oidc import IdentityToken, Issuer, detect_credential
        from sigstore.sign import SigningContext
    except ImportError as e:
        raise RuntimeError(
            "The 'sigstore' package is required: pip install sigstore"
        ) from e

    # 1. Get an OIDC identity: ambient (GitHub Actions id-token) first,
    #    interactive browser flow otherwise.
    raw_token = detect_credential()
    if raw_token:
        token = IdentityToken(raw_token)
        print("Using ambient OIDC credential (CI)", file=sys.stderr)
    else:
        issuer = Issuer(STAGING_OAUTH_ISSUER if staging else PRODUCTION_OAUTH_ISSUER)
        print("No ambient credential — opening browser for OIDC flow", file=sys.stderr)
        token = issuer.identity_token()

    # 2. Sign with an ephemeral key certified by Fulcio; logged in Rekor.
    config = ClientTrustConfig.staging() if staging else ClientTrustConfig.production()
    ctx = SigningContext.from_trust_config(config)
    with ctx.signer(token) as signer:
        bundle = signer.sign_artifact(canonical_payload(entry))

    signed = dict(entry)
    signed["_signature"] = json.loads(bundle.to_json())
    return signed


def _load_entry(arg: str) -> dict:
    """Load the entry from a file path or a literal JSON line."""
    path = Path(arg)
    text = path.read_text() if path.exists() else arg
    lines = [l.strip().lstrip("+") for l in text.strip().splitlines()
             if l.strip() and not l.strip().startswith("#")]
    if len(lines) != 1:
        raise ValueError(f"Expected exactly 1 JSONL entry, found {len(lines)}")
    return json.loads(lines[0])


def main() -> int:
    parser = argparse.ArgumentParser(description="Sign a benchmark entry with sigstore (keyless)")
    parser.add_argument("entry", help="Path to a JSON/JSONL file with one entry, or a literal JSON line")
    parser.add_argument("--bundle-out", help="Also write the raw sigstore bundle JSON to this path")
    parser.add_argument("--staging", action="store_true",
                        help="Use sigstore's staging infrastructure (for testing)")
    args = parser.parse_args()

    try:
        entry = _load_entry(args.entry)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Error: invalid entry input: {e}", file=sys.stderr)
        return 1

    try:
        signed = sign_entry(entry, staging=args.staging)
    except Exception as e:  # sigstore raises several error types
        print(f"Error: signing failed: {e}", file=sys.stderr)
        return 1

    if args.bundle_out:
        Path(args.bundle_out).write_text(json.dumps(signed["_signature"], indent=2))

    print(json.dumps(signed, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
