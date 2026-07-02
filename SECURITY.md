# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Core AI Catalog, please:

1. **Do NOT open a public GitHub issue.**
2. Email the maintainer directly or open a private security advisory via GitHub's Security tab.
3. Include a description of the vulnerability and steps to reproduce.

You will receive a response within 48 hours.

## Scope

- Vulnerabilities in the MCP server, CLI, or Python API that could allow code execution or data leakage
- Private key exposure (Ed25519 relay keys, Apple API keys)
- Benchmark data poisoning vectors that bypass the validation pipeline

## Not in Scope

- The privacy relay (Cloudflare Worker) — that lives in a separate private repo
- Issues with individual model conversions — report to the upstream source
