# Privacy Policy — Core AI Benchmark Submissions

> This document describes how benchmark data is collected, processed, and published.

## What we collect

When you choose to share benchmark results from the app:

| Data collected | Example | Why |
|---|---|---|
| Model performance metric | `145.4 tokens_per_second` | This IS the benchmark |
| Device chip class | `A18 Pro` | Hardware affects performance |
| OS major version | `27` | OS version affects performance |
| Date of benchmark | `2026-07-02` | Tracks performance over time |
| Model ID | `official-qwen3-4b` | Identifies which model was tested |
| Engine variant | `coreai-pipelined` | Runtime affects performance |
| Thermal state | `nominal` | Thermal throttling affects results |
| Battery state | `charging` | Power mode affects results |
| Protocol version | `2.0` | Ensures comparability |
| App version | `ditto-ios-0.1.0` | Identifies submission source |
| DeviceCheck attestation | Verified, then **discarded** | Proves genuine hardware |

## What we NEVER collect

- Your name, email, or Apple ID
- Your device's serial number or UDID
- Your IP address (stripped by the relay before publishing)
- Your location or timezone
- What you type or generate with the models
- Which other apps you use
- Your GitHub username (submissions are authored by a bot account)

## How data flows

```
Your device → Privacy Relay (Cloudflare Worker) → Public GitHub Repository
```

1. The app sends benchmark data to the Privacy Relay via HTTPS
2. The relay verifies DeviceCheck (proves real device), then **discards the token**
3. The relay coarsens device data (iPhone17,1 → "A18 Pro")
4. The relay strips time precision (keeps date only, not time)
5. The relay signs the sanitized payload with Ed25519
6. The relay opens a Pull Request via a bot account (not your account)
7. The GitHub Action validates the signature + schema + outlier check
8. If all checks pass, the benchmark is merged into the public dataset

## Data publication

All benchmark data is published in the public GitHub repository
`kevinqz/coreai-catalog` under the MIT license. This means:

- **Your benchmark numbers are public** — anyone can see them
- **The data is permanent** — git history cannot be erased
- **The data is attributed to a bot** — not linked to your identity

### Aggregate suppression

Aggregate statistics with fewer than 3 samples are suppressed to prevent
de-anonymization. If you are the only person to benchmark a specific
model+device combination, your individual result will not appear in
aggregate statistics until at least 2 other people contribute.

## Consent

Benchmark sharing is **opt-in**. You will see a consent dialog on first
launch with separate toggles for:

1. Share performance data (benchmark results)
2. Share device class (chip family)
3. Share benchmark dates

All default to OFF. You can change these at any time in Settings.

### Withdrawal

To withdraw consent:
1. Toggle off the sharing options in Settings
2. No new benchmarks will be submitted after that

**Note:** Previously submitted benchmarks remain in the public repository's
git history. We cannot remove data from git history without breaking
all existing clones of the repository. If you need data removed for legal
reasons, please open an issue and we will evaluate on a case-by-case basis.

## Your rights

Depending on your jurisdiction, you may have rights under GDPR (EU),
LGPD (Brazil), CCPA (California), or other privacy laws. While we believe
the coarsened, non-attributed benchmark data does not constitute personal
data under these regulations, we are committed to working with you to
address any concerns.

For privacy inquiries: open a GitHub issue with the `privacy` label.

## DeviceCheck

The app uses Apple's DeviceCheck framework to verify that benchmark
submissions come from genuine Apple hardware. This:

- Proves you're using a real device (not a simulator)
- Helps prevent fabricated benchmark submissions
- Does NOT identify you personally — DeviceCheck tokens are per-device
  but cannot be used to look up your identity

You can disable DeviceCheck in Settings > Privacy & Security on your device.
If disabled, your benchmarks will still be accepted but marked with lower
confidence.
