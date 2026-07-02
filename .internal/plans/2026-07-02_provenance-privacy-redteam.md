# Privacy & Legal Red-Team Review: Crowdsourced Benchmark Provenance Architecture

> **Review date:** 2026-07-02
> **Reviewer:** Privacy-law / security-researcher role (red team)
> **Target:** `2026-07-02_provenance-architecture.md` + stated claims (HMAC device ID, IP stripping, single opt-in, GDPR/LGPD exemption)
> **Verdict:** The design is **not deployable as-is** under EU/Brazilian/California law, and carries at least **two CRITICAL** and **three HIGH** privacy defects. The claim of GDPR/LGPD exemption is legally indefensible.

---

## Scope notes / what the doc actually says vs. what is claimed

The design document (`provenance-architecture.md`) does **not** itself contain the HMAC device-ID scheme, the opt-in prompt, the IP-stripping claim, or the GDPR/LGPD-exemption argument. Those claims were supplied as context (presumably from the Ditto app spec). This review attacks both:

- **(A) What the doc literally specifies** — and it specifies *more* than the claims suggest.
- **(B) The stated privacy claims** — which are weaker than the doc implies.

The single most important factual correction up front: **the design document does not collect only an HMAC'd device ID. It publishes raw device model (`iPhone17,1`), chip (`A18 Pro`), RAM (`ram_gb: 8`), OS version, a deterministic model hash, a DeviceCheck attestation flag, a precise UTC timestamp, and an app-identifier string — all into a public GitHub repository whose history is permanent.** An HMAC on a *separate* device-ID field does not rescue the rest of this record.

---

## Executive summary of findings

| # | Finding | Severity | One-line risk |
|---|---|---|---|
| 1 | Published device fingerprint is quasi-identifying and re-identifies submitters across submissions | **CRITICAL** | (chip+RAM+OS+model+tz) narrows to one person |
| 2 | GitHub username is permanently bound to device fingerprint + model-download set in public history | **CRITICAL** | Builds a public (user → device → app-usage) database; non-erasable |
| 3 | HMAC "device ID" is a weak pseudonymity claim; key + raw device data both shipped | **HIGH** | HMAC is reversible / bruteforceable; and it's redundant with the raw fields anyway |
| 4 | GDPR Art. 4/26 "personal data" test is failed; Art. 17 erasure is *technically impossible* in git | **HIGH** | Permanent public record + no deletion path = Art. 17 violation |
| 5 | Single opt-in is not GDPR Art. 7(1) compliant; no granularity, no withdrawal mechanism | **HIGH** | Consent invalid → all processing unlawful |
| 6 | `model_hash` leaks the user's installed-model inventory (sensitive inference) | **MEDIUM** | Reveals interests / research focus / employer |
| 7 | DeviceCheck attestation ties submission to an Apple device record the user cannot see or revoke | **MEDIUM** | Apple-side correlatable identifier beyond your control |
| 8 | Timestamps leak activity patterns / timezone / working hours | **MEDIUM** | Behavioral inference, correlates across submissions |
| 9 | COPPA: no age gate; minors can submit, creating a permanent public device dossier | **MEDIUM** | Child data in immutable public history |
| 10 | CCPA: "device information" exemption likely **does not apply** once linked to a GitHub account | **MEDIUM** | CA-resident DSAR rights attach |
| 11 | Outlier/audit retention (`rejected/`) keeps rejected submissions forever, public | **LOW** | "No" is not erasure |
| 12 | `submission_channel: ditto-ios-0.1.0` + Git commit cadence can re-identify the lone early submitter | **LOW** | Small-N re-identification |

---

## CRITICAL findings

### CRITICAL-1: The published device fingerprint re-identifies submitters

**What the doc publishes (per benchmark record, §2.1):**
```yaml
device: "iPhone17,1"
device_info:
  chip: "A18 Pro"
  ram_gb: 8
  os_version: "27.0"
environment: "iOS 27.0, coreai-pipelined"
provenance:
  submitted_at: "2026-07-15T12:00:00Z"
  submission_channel: "ditto-ios-0.1.0"
```

**Privacy/legal risk.** Each of these is a *quasi-identifier*. The combination is a textbook fingerprint under the GDPR Recital 26 "means reasonably likely to be used" test. Concretely:

- `iPhone17,1` already narrows to one hardware SKU.
- `chip: A18 Pro` × `ram_gb: 8` narrows to one specific configuration (the Pro-line iPhone 17 with 8 GB — a minority SKU at launch).
- `os_version: 27.0` narrows to a *point release window* (people update within days; a specific x.0 build is held by a small slice at any instant).
- `submitted_at` to the second exposes the submitter's timezone and working hours.
- `submission_channel: ditto-ios-0.1.0` in the early days means "one of the first N users of this app" — tiny population.

Per the Panopticlick / EFF fingerprinting literature and the *Breyer* (CJEU C-582/14) line, a combination of quasi-identifiers that singles out an individual **is personal data**, regardless of whether a name is attached. EU DPAs (and the EDPB) treat device fingerprints as personal data routinely.

**Concrete attack.** An adversary scrapes `benchmarks.yaml` + the Issues. They cluster by `(chip, ram_gb, os_version)`. Each cluster of size 1 = a re-identified device. Cross-referencing the submission timestamp's timezone with the GitHub username's public location pins it to a person. Inside a 50-person office running the same SKU/OS, the timestamp + the choice of models benchmarked is frequently unique.

**Severity rationale.** This is the load-bearing defect: it converts "anonymous benchmarks" into "a public log of identifiable people's device usage." Everything downstream (CRITICAL-2, HIGH-4) compounds on it.

**Mitigation.**
- Do **not** publish `chip`, `ram_gb`, or sub-major `os_version` at submission granularity. Bucket: store only `device_family` (e.g. `iphone-pro-a18`), round OS to major version, drop RAM or bin it (`<=6` / `8` / `>=12`).
- Drop the per-second `submitted_at` from the public record; publish only `observed` rounded to the **week**.
- Require **k-anonymity ≥ 5** before a bucket's data is published: if fewer than 5 distinct submitters share a fingerprint bucket, withhold or merge.
- Run the submission through a **linkage-risk test** server-side (not in a public Issue) before anything is committed.

---

### CRITICAL-2: GitHub Issues bind a real identity to the device fingerprint, permanently, in public history

**The flow (doc §2.4):** App → **GitHub Issue** (auto-generated) → GitHub Action → `benchmarks/pending/` → curated into `benchmarks.yaml`.

**Three compounding problems:**

1. **GitHub Issues are public, indexed, and attributed.** A submission Issue carries the submitter's GitHub username, avatar, and profile link — permanently. The Issue body contains the device fingerprint + model hash + timestamp. So the public artifact is: *GitHub user X, on device Y, downloaded and benchmarked models Z₁…Zₙ, at times T₁…Tₙ.* That is a ready-made **(identity → device → app-usage)** dossier.

2. **Scraping is trivial and lawful under GitHub's ToS for public data.** `gh issue list --search label:benchmark-submission` → full corpus. An attacker now has a searchable database of "who runs which models on which iPhone." For a niche ML tool this population is small and the re-identification surface is correspondingly large.

3. **Git history is immutable.** The doc itself boasts "Git-native… attributable" (§2.8) and stores rejected submissions under `rejected/` "kept for audit." Even if a curator *deletes* a benchmark from `benchmarks.yaml` and closes the Issue, **the blob persists in git history forever** (no force-push reflog expiry on a shared repo), and the Issue lives in the GitHub Events API / archive.org / search-engine caches.

**Legal risk.**
- **GDPR Art. 17 (right to erasure):** a data subject can demand deletion. You **cannot comply** without `git filter-repo` history rewrites across every fork and mirror (you don't control forks), plus Issue deletion (you can close, not truly purge, and caches retain it). This is an *unsolvable* structural defect of the chosen storage medium. The same applies to **LGPD Art. 18 (VI)** (Brazil) and arguably **CCPA §1798.105** (deletion).
- **GDPR Art. 5(1)(c) data minimization + Art. 25 data protection by design:** publishing *more* than the benchmark value, into an immutable public store, is the opposite of minimization.

**Concrete attack.** A recruiter or employer scrapes the repo. "Alice benchmarks only vision models on a Mac Studio; Bob benchmarks only jailbreak-detection-related models at 3 a.m. local." Inferable: Alice works in CV; Bob is doing security research off-hours. Both are now public, permanent, and were never told this would happen.

**Severity rationale.** Identity-binding + permanence + publicity = the worst-case combination for privacy. No amount of hashing the device-ID field fixes this, because the identity comes from the **GitHub account**, not the device.

**Mitigation (the only real one: change the intake).**
- **Do not use GitHub Issues for raw intake.** Use a **privacy-preserving relay** (a small serverless function) that:
  1. Receives the submission,
  2. Strips the GitHub identity (or never requires login — submit via signed token, no account),
  3. Performs k-anonymity / outlier checks,
  4. Publishes **only the aggregated, bucketed, time-rounded benchmark row** — never the raw device fingerprint or per-user hash.
- If Issues *must* be used, the Issue body must contain **only** the already-anonymized, bucketed record (no chip, no per-second timestamp, no model hash), and a separate private channel must carry anything sensitive.
- Adopt a **retention + history-rewrite policy** with tooling (`git filter-repo`) documented, and disclose to users up front that *full* erasure is not guaranteed — which then forces you back to "collect almost nothing."

---

## HIGH findings

### HIGH-3: The HMAC "device ID" claim is broken in three independent ways

The brief claims "device ID is HMAC hashed." Even taking the claim at face value, it fails:

1. **Where is the key?** An HMAC is only as secret as its key. In an **open-source** app, a key compiled into the binary is recoverable in minutes (strings/class-dump/Hopper on an IPA). If the key is per-install random, then the HMAC is just an opaque ID that the server can't dedupe (so it provides no anti-spam value either). There is no key-management design here that survives the open-source constraint. **Open-source + client-side HMAC = plaintext-equivalent.**

2. **It's redundant.** Even if the HMAC were a perfect unlinkable pseudonym, the record *also publishes the raw quasi-identifiers* (chip, RAM, OS, device model) that the HMAC was supposedly protecting. An attacker doesn't need to invert the HMAC — they group on the raw fields. The HMAC is **security theater** against the actual threat model.

3. **Brute-forceability.** HMAC over a low-entropy input (a device's hardware identifiers — a small enumerable space: a handful of chip×RAM×serial-prefix combinations) is **dictionary-attackable**. If the HMAC input is, e.g., the IDFV or a serial-derived value, an attacker who knows roughly the device population can enumerate candidate inputs and test HMAC collisions. Pseudonymization that is reversible by the data holder (or anyone with the key) is **not anonymization** under GDPR Art. 4(5); it's pseudonymization, which remains in scope of GDPR.

**Mitigation.**
- Drop client-side HMAC entirely; it provides no real protection in an OSS client.
- If anti-spam/dedup is needed, do it **server-side** with a key the client never sees, and store only a salted hash you cannot invert and *never publish it*.
- Treat any retained device identifier as **pseudonymous personal data** (not anonymous) for all compliance purposes.

---

### HIGH-4: GDPR scope + non-erasability = unlawful processing

**Is the device fingerprint "personal data"? — Yes.**

- **GDPR Art. 4(1):** personal data is any info relating to an identified or *identifiable* natural person.
- **Recital 26:** identifiability includes singling out by "means reasonably likely to be used," explicitly including online identifiers and device fingerprints.
- **CJEU C-582/14 (*Breyer*):** even data requiring third-party databases to link is personal data if those databases are reasonably available. GitHub usernames + public device specs are trivially linkable.
- **EDPB Guidelines 01/2020 on processing of personal data in the context of connected vehicles** (and several DPA decisions on telemetry) treat (model + OS version + timing) as personal data.

The doc's "no PII collected" framing is the classic and consistently-rejected "we removed the name so it's anonymous" fallacy. The benchmark record is **personal data** for EU users.

**Consequences:**
- **Art. 6 lawfulness:** you need a valid basis. "Legitimate interest" (Art. 6(1)(f)) is arguable for *aggregate* benchmarking but **not** for publishing per-user device fingerprints publicly. Consent (Art. 6(1)(a)) requires Art. 7 quality (see HIGH-5) — which the single opt-in fails.
- **Art. 5(1)(c) minimization:** violated — you collect and *publish* chip, RAM, OS, per-second timestamps, and a per-model hash, none of which are needed to report a throughput number.
- **Art. 5(1)(e) storage limitation:** violated — git history is permanent by design.
- **Art. 17 erasure:** **structurally impossible** to satisfy. `git filter-repo` cannot reach forks, mirrors, GitHub's own Issue/event caches, archive.org, or clones. A data subject's erasure request would be **unenforceable**, exposing the controller to Art. 82 damages + Art. 83 fines (up to €20M / 4% global turnover).
- **Art. 25 (data protection by design/default) & Art. 35 (DPIA):** a system publishing device fingerprints to an immutable public store *requires* a DPIA; none exists.
- **Cross-border (Art. 44+):** the data ends up on GitHub/Microsoft infrastructure (US). Even post-Schrems II, a *new* public disclosure of EU residents' device fingerprints to a US platform needs a valid transfer mechanism and, for sensitive inferences, likely fails the necessity test.

**LGPD (Brazil) mirror:** Art. 2º, II (device data is "dado pessoal"); Art. 18 (VI) deletion right; ANAT guidance treats device fingerprints as personal data. Same non-erasability problem.

**Mitigation.** Redesign so the published record contains *no personal data at all* (aggregate, k-anonymous, time-binned). Then GDPR/LGPD largely fall away *for the published artifact* — but the **intake** (Issue) still processes personal data transiently and must be deleted on a short schedule. If you cannot delete from git, do not put it in git.

---

### HIGH-5: The opt-in is not valid GDPR consent

The brief claims "explicit opt-in, single prompt on first launch."

**Why it fails Art. 7(1) + Recital 32/43:**
1. **Not granular.** A single binary consent bundles (a) running a benchmark, (b) publishing my device fingerprint, (c) publishing my model-download set, (d) publishing to an *immutable* store, (e) attribution to my GitHub account. Art. 7(2) + Recital 43 require **separate consent for separate purposes**. "Run benchmark" and "publish my device specs permanently to the public internet under my name" are not the same purpose.
2. **Not informed.** The user must understand *before* consenting that the data is permanent, public, indexed by search engines, attributable to their GitHub handle, and not deletable. A "single prompt on first launch" cannot convey this. Recital 42: consent is invalid if the data subject is unaware of "the possible consequences" of processing.
3. **Conditioned on a precondition?** If benchmarking requires submission, consent is not "freely given" (Recital 42: detriment if you refuse). If submission is optional, say so loudly and default to off.
4. **Withdrawal (Art. 7(3)) must be as easy as giving consent.** There is **no withdrawal mechanism** described — and because of git immutability (HIGH-4), withdrawal is *technically impossible* for already-published data. This alone makes the consent invalid and the ongoing processing unlawful.

**Mitigation.**
- Layered, granular consent: separate toggles for "run local benchmark," "share results (anonymized)," "attribute to my GitHub account." All default off.
- Plain-language notice that explicitly states: *public, permanent, not deletable, attributable*.
- A working withdrawal flow that at minimum stops future submissions and removes the *current* `benchmarks.yaml` entry (with a documented, honest limitation that historical/git-cached copies may persist).
- Because true erasure is impossible, **do not attribute submissions to GitHub accounts in the first place.**

---

## MEDIUM findings

### MEDIUM-6: `model_hash` leaks the user's installed-model inventory

**What it is (doc §2.5 step 7, §2.1):** `SHA256 of .aimodel bundle` is published per benchmark.

**Risk.** A SHA256 over the bundle bytes is a *deterministic* identifier of *which exact model artifact* the user downloaded. The set of `model_hash`es a single device fingerprint produces over time is the user's **model library** — i.e., what they're working on. Inferences:
- Only vision-language models → CV practitioner.
- Only uncensored / jailbreak-tuned variants → security research or sensitive personal use.
- A specific niche model (e.g., a corporate fine-tune) → employer affiliation.
- The hash is also a **cohort membership signal**: anyone else with the same hash downloaded the same artifact.

**Does it leak filesystem paths?** Only if the bundle hash includes path data. Per §2.5 the hash is over the `.aimodel` bundle (a packaged artifact), so it should be path-independent — **but the doc does not specify the canonicalization** (zip ordering, metadata, extended attributes). If the implementation hashes the on-disk directory tree with paths, it could leak usernames embedded in macOS paths (`/Users/<name>/...`). This must be pinned down: hash only the canonical, reproducibly-packed bundle contents.

**Mitigation.**
- Hash only a normalized, path-stripped bundle (document the canonicalization).
- Consider whether the per-submission hash is even needed publicly; it's mainly useful for *verifying reproducibility*, which can be done by a *server-side* check that discards the hash after validation.
- Never publish a per-user sequence of hashes.

---

### MEDIUM-7: DeviceCheck attestation is an identifier you can't see or revoke

**What it is (doc §2.1):** `device_attestation: true` (Apple DeviceCheck).

**Risk.** DeviceCheck issues a per-device token that Apple can correlate across apps. Setting a flag is harmless, but if the *token* or any device-bound bit is transmitted (the doc is silent — a risk in itself), Apple (and anyone Apple shares with) gains a cross-app device identifier. The user has no visibility into it and cannot revoke it per-app easily. This is a **third-party processor** relationship (Apple) that must be disclosed in the privacy notice and (for EU users) covered by Art. 26 joint-controller or Art. 28 processor terms.

**Mitigation.** Specify exactly what is sent to Apple. Use the attestation only to validate legitimacy, **discard the token server-side**, never persist it, and disclose Apple as a processor/sub-processor.

---

### MEDIUM-8: Timestamps leak behavior, timezone, and working patterns

**What it is:** `submitted_at` (per-second UTC) + `observed` date.

**Risk.** Per-second timestamps reveal timezone (→ country/region), working hours, sleep patterns, and — across multiple submissions — a behavioral fingerprint that re-identifies a user even *without* the hardware fields. Combined with CRITICAL-1 this is synergistic.

**Mitigation.** Publish `observed` only, rounded to the week. Drop `submitted_at` from the public record entirely. Keep precise time only in a short-lived private intake log with a 30-day TTL.

---

### MEDIUM-9: COPPA — no age gate; minors create permanent public dossiers

**Risk.** A 13-year-old installs Ditto, opts in (a child cannot validly consent under COPPA / GDPR Art. 8 / LGPD Art. 14), submits a benchmark. Result: a **permanent, public, device-attributed** record of a minor's device usage, undeletable from git. COPPA requires verifiable parental consent (VPC) for under-13s; GDPR Art. 8 sets 16 (member states may lower to 13) and requires parental consent. There is **no age verification** anywhere in the flow.

**Mitigation.** Given the public+permanent nature, the realistic option is to **age-gate the submission feature** (e.g., require a one-time 18+ assertion with a clear "do not use if under 16/13" notice) and, because VPC is hard for an OSS project, **disable submission for users who cannot affirm adulthood.** Treat the absence of a robust age gate as a launch blocker.

---

### MEDIUM-10: CCPA "device information" exemption likely does not apply once linked to a GitHub account

**The nuance.** CCPA §1798.140(d)(2)(A) exempts "device information" *collected* by a business. But:
- The data is **linked to a GitHub username**, which is an identifier → it becomes personal information under §1798.140(v).
- §1798.135 prohibits conditioning service on a "global privacy control" opt-out; a benchmark-sharing feature must honor GPC.
- Once linked to an account, the **right to delete (§1798.105)** and **right to know (§1798.100)** attach — and deletion is (again) structurally impossible (HIGH-4).

**Mitigation.** Honor GPC at the intake layer. Treat submissions as in scope of CCPA and publish a compliant privacy policy + deletion procedure (with honest caveats).

---

## LOW findings

### LOW-11: `rejected/` retention publishes rejected submissions "for audit"

The doc keeps rejected submissions under `benchmarks/rejected/`. A user who submitted and was rejected still has their device fingerprint + model hash + identity permanently public. "We didn't use your benchmark" is not "we deleted your data."

**Mitigation.** Do not persist raw rejected submissions. Store only a redacted rejection record (reason code, no device/model-hash/identity).

### LOW-12: Small-N re-identification via `submission_channel` + commit cadence

Early on, `submission_channel: ditto-ios-0.1.0` + the first few commits uniquely identify "the people who installed v0.1.0." Combined with GitHub commit timestamps, an adversary can often pin a submission to a specific person even without the device fields.

**Mitigation.** Withhold `submission_channel` versions from the published record; track them privately for fraud detection only.

---

## Cross-cutting observations the doc gets right, and a structural recommendation

**What the doc does *well*** from a provenance/integrity standpoint (these are orthogonal to privacy and should be preserved):
- Per-claim provenance + `extraction_method` taxonomy → excellent for data trust.
- Deterministic benchmark protocol → reproducible science.
- Outlier (MAD) checks → integrity.

**The structural fix.** The privacy catastrophe comes entirely from **publishing raw, per-submission, identifiable data into an immutable public store via an identity-bound channel.** The fix is a one-architecture-change solution:

> **Introduce a thin privacy-preserving relay between the app and the public repo.**

```
App  →  Relay (serverless, no login)  →  Aggregate/Anonymize  →  Publish ONLY to benchmarks.yaml
                ↓
          k-anonymity + outlier check
                ↓
          Discard raw device fingerprint, model hash, identity, sub-day timestamp
```

- The **GitHub Issue** channel should carry *only* the already-anonymized, bucketed, week-rounded row (or be replaced entirely).
- The **git repo** should never contain raw device fingerprints, per-user hashes, or anything attributable.
- A **DPIA** (Art. 35) and a written **privacy notice + deletion procedure** are mandatory pre-launch.

This keeps every scientific benefit of the design (provenance, reproducibility, transparency) while removing the parts that make it unlawful.

---

## Bottom line

The "no PII, therefore GDPR-exempt" premise is **wrong as a matter of law** (device fingerprints + account binding = personal data) and **unworkable as a matter of technology** (git immutability defeats the right to erasure). Two findings are **CRITICAL** (device-fingerprint re-identification; permanent public identity-binding via GitHub Issues) and **cannot be patched by hashing a device ID** — they require changing the intake channel and what gets published. Until that redesign and a DPIA are done, this system should not ship to EU, Brazilian, or Californian users.
