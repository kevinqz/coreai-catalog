# Core AI Benchmark Privacy Policy

> How the Core AI Catalog collects, processes, and protects benchmark data.

## Summary

The Core AI Catalog collects **anonymous performance benchmarks** from volunteer devices to build the most trustworthy source of on-device AI performance data. We collect **no personal data**.

## What We Collect

When you opt in to benchmark sharing, each submission contains:

| Data | Example | Why needed |
|---|---|---|
| Model ID | `official-qwen3-4b` | Identifies which model was benchmarked |
| Metric + Value | `145.4 tokens/sec` | The performance measurement |
| Methodology | Protocol v1.0, 10 iterations, median | Makes the result reproducible |
| Device class | `iphone-a18-pro` | Coarsened — not your exact device. Millions share each class. |
| RAM | `8 GB` | Affects performance. Only 2-3 possible values per device class. |
| OS major version | `27.0` | Affects performance. Minor version stripped. |
| Runtime config | `coreai-pipelined engine` | Identifies the inference engine used |
| Thermal state | `nominal` | Affects performance significantly |
| Model hash | `sha256:abc123...` | Proves which model weights were used |
| Date | `2026-07-15` | When the benchmark ran. Date only — no time. |

## What We Never Collect

- Your name, email, or Apple ID
- Your exact device model (e.g., `iPhone17,1`)
- Your IP address (stripped before any data leaves your device)
- Your location
- Time of day (coarsened to date only)
- Your GitHub username (submissions are posted by an automated bot)
- Content you generate with models (prompt text, output text, images)
- Your app usage data
- Your contacts, photos, or any personal files
- Any persistent device identifier

## How Submissions Work

1. You run a benchmark in the app
2. The app shows you the **exact data** it will share
3. You tap "Share" to confirm
4. The app sends the data to our privacy relay (a Cloudflare Worker)
5. The relay validates your device is genuine (via Apple App Attest)
6. The relay **coarsens** any remaining granular data
7. The relay posts the benchmark to our public repository as an anonymous submission
8. A GitHub Action validates the data and merges it

**Your GitHub account is never linked to the benchmark.** The relay posts using a bot account. There is no way to trace a benchmark back to you.

## Your Control

- **Opt in:** You choose to share. No data is sent without explicit action.
- **Per-submission:** You see and approve each submission before it's sent.
- **Revoke anytime:** Settings → Benchmark Sharing → Off. Stops all future submissions.
- **Pre-view:** Before each submission, you see the complete JSON payload.

## Legal Basis

- **GDPR (EU):** The data collected is anonymous. Device class + date + model performance is not personal data under Article 4(1). It cannot identify a natural person.
- **LGPD (Brazil):** Anonymous data is excluded from scope (Art. 12, II).
- **CCPA (California):** Device data not linked to a consumer is exempt (§1798.140(d)(2)(B)).
- **Apple App Store:** Privacy label: "Performance Data — Not Linked to You."

## Data Storage

Benchmark data is stored in our public GitHub repository as JSONL (one line per benchmark). The data is anonymous, public, and open source. Anyone can audit it.

## App Attest

We use Apple's App Attest framework to verify that submissions come from genuine apps on genuine devices. This prevents fabricated submissions. The attestation token:

- Proves your device is real (not an emulator)
- Does NOT identify you or your device to us
- Is validated by Apple's servers, then discarded
- Is never stored, logged, or written to git

## Dedup

To prevent duplicate submissions, the relay uses a temporary (60-day) hash of your device attestation in Cloudflare KV. This hash:

- Is computed with a server-side key (not in the app)
- Is used ONLY to prevent the same device submitting the same benchmark twice
- Expires automatically after 60 days
- Is never written to git or any persistent store

## Contact

For privacy questions: open an issue on our GitHub repository.

## Changes

This policy is version-controlled in our repository. Any changes are public and tracked in git history.
