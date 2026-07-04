# Competitive Landscape Analysis — Core AI Catalog

> Red-team assessment of positioning gaps, competitor strengths, and what's needed to become the definitive destination for Apple on-device AI model discovery.

> **Update (suitability reshape):** references below to "readiness scoring" as a
> headline differentiator predate the SotA reshape. `readiness_score` is now
> deprecated as a headline (blind to model quality); positioning should lead with
> the decomposed **suitability facets** and **benchmark values**. See
> [`concepts/suitability-facets.md`](concepts/suitability-facets.md).

---

## Executive Summary

Core AI Catalog has a **genuinely unique position**: it's the only structured, source-grounded, agent-native metadata layer for Apple's newest Core AI (`.aimodel`) ecosystem. No competitor combines readiness scoring, provenance chains, license triage, task-based recommendations, and an MCP server in one place.

But the project **under-communicates its unique value** and **lacks several features that competitors use to drive stickiness** — community engagement, leaderboards, live demos, and version history. The positioning answers *what* the catalog is, but not compelling enough *why someone should use it instead of Hugging Face*.

**Top 5 actions to become the definitive destination:**

1. Add a public **benchmark leaderboard** (the single highest-impact feature vs MLPerf/HF)
2. Rewrite the homepage hero with a **competitive elevator pitch** that names the alternative
3. Add **per-model pages with deep links** (SEO + shareability, matching HF model cards)
4. Build **community discussion threads** per model (the engagement loop HF has perfected)
5. Clearly position **Core AI vs MLX** so users understand when to use each

---

## 1. Hugging Face Comparison

### What HF has that this catalog lacks

| Feature | HF | Core AI Catalog | Severity |
|---|---|---|---|
| **Community discussions** | Per-model threads, PRs, community tab | GitHub Issues only (no per-model discussion) | 🔴 High |
| **Version history** | Git-based model revisions, tags, releases | No model version tracking (catalog version only) | 🟡 Medium |
| **Spaces / live demos** | Interactive Gradio/Streamlit demos | No demos (catalog is metadata-only) | 🟡 Medium |
| **Datasets** | Full dataset hub | Not applicable (different scope) | ⚪ Low |
| **Social proof** | Downloads count, likes, followers | No usage metrics or popularity signals | 🟡 Medium |
| **Model card richness** | Full README, training data, eval results, bias | Structured metadata but no narrative card | 🟡 Medium |
| **User profiles** | Per-user/org pages with contribution history | CREDITS.md only | 🟡 Medium |
| **Trending/discovery** | "Trending models" leaderboard | Readiness score (different axis — deployment readiness, not popularity) | 🟡 Medium |

### What this catalog has that HF doesn't

| Feature | Why it's unique | Communication gap |
|---|---|---|
| **Readiness scoring (0-100)** | 13-factor deployment-readiness score — HF has no equivalent. Developers learn *not just "does this model exist" but "can I ship this tomorrow?"* | 🔴 **Massively under-communicated.** This is buried in the About tab. It should be the hero feature. |
| **Task-based recommendations** | `recommend --task "private OCR on iPhone"` returns ranked candidates. HF has task filters but no recommendation engine. | 🟡 Mentioned but not positioned as a killer feature vs "browse HF manually" |
| **Apple-specific provenance chains** | Separates original creator → conversion source → artifact host → license. HF conflates these. | 🟡 Documented in docs but not surfaced in the UI prominently |
| **License triage** | `commercial_use: likely/check_license` is a binary decision filter. HF shows raw license text. | 🟡 Present in filters but the "triage" framing isn't highlighted |
| **Officiality disambiguation** | `apple_export_recipe` vs `community_packaged` — no HF equivalent | 🟢 Well-documented in docs/concepts |
| **MCP server (agent-native)** | 12 tools for AI agents. HF has Inference API but no agent-native discovery. | 🔴 **Major differentiator barely mentioned on the homepage hero.** The tagline says "agent-ready" but doesn't explain why that matters. |
| **Modality transform graph** | `transforms --from audio --to image` plans multi-model pipelines | 🟡 Unique feature, not communicated as such |
| **Verified Apple terminology layer** | 42 terms grounded in official Apple sources | 🟢 Unique, positioned well in docs |
| **Benchmark protocol with anti-gaming** | Ed25519 signing, MAD outlier detection, anchor cohort, k=3 suppression | 🔴 **Incredibly sophisticated but completely invisible on the website.** |

### Verdict

**The catalog's unique features are real and valuable, but the marketing doesn't lead with them.** The homepage says "82 Core AI models with provenance, licenses, benchmarks, and readiness scores" — which sounds like a list. It should say something closer to:

> *"Hugging Face tells you what models exist. Core AI Catalog tells you which one to ship."*

---

## 2. MLX Ecosystem Comparison

### Current MLX landscape
- **ml-explore.github.io**: Apple's official MLX examples and docs
- **mlx-lm / mlx-vlm**: Community packages with Hugging Face integration
- **MLX model hub**: Effectively Hugging Face (mlx-community org) — there's no separate MLX model hub
- **MLX benchmarks**: Scattered across blog posts and READMEs, no central registry

### How Core AI (.aimodel) compares to MLX

The project has an excellent comparison doc (`docs/concepts/core-ai-vs-core-ml-vs-mlx.md`) that clearly explains:
- Core AI = on-device deployment (iOS 26+, `.aimodel`, pipeline-based)
- MLX = research/training (macOS only, Python-first, `.safetensors`)
- Core ML = classic ML (iOS 11+, `.mlmodel`, ANE-optimized)

### Positioning gaps

| Gap | Severity | What's missing |
|---|---|---|
| **No clear "when to use Core AI vs MLX" decision in the hero** | 🔴 High | The comparison is buried in docs. A developer landing on the homepage doesn't immediately understand *why Core AI vs MLX*. The site should have a one-sentence positioning: "MLX is for research on Mac. Core AI is for shipping on iPhone." |
| **No MLX model cross-referencing** | 🟡 Medium | Many models exist in both MLX and Core AI form (e.g., Qwen3, Gemma 3). The catalog could note "also available as MLX" to help users understand the ecosystem. Not a full MLX catalog — just cross-references. |
| **Conversion path documentation exists but isn't discoverable** | 🟡 Medium | `mlx2coreai` is documented in upstreams.yaml but a user wouldn't know to look there. A "Conversion paths" section on the site would help. |
| **No "MLX equivalent" field** | 🟢 Low | Optional `mlx_equivalent` field on models that have both representations |

### Should the catalog list MLX-compatible models?

**No — but it should cross-reference them.** The catalog's identity is "Core AI models." Expanding to MLX would dilute the focus and duplicate Hugging Face's mlx-community. Instead:
- Add a `cross_format` field noting when a model also has MLX/Core ML versions
- Add a "Framework comparison" widget on the site
- Keep the conversion-path docs prominent

---

## 3. Benchmark Comparison (vs MLPerf)

### MLPerf's approach
- **Strict submission rules**: audited, reproducible, standardized hardware
- **Peer review**: submissions reviewed by MLCommons members
- **Standardized benchmarks**: ResNet, BERT, GPT-J, etc. — fixed workloads
- **Result tables**: public, filterable, with submission-level detail
- **Trust model**: institutional (MLCommons membership, audit process)

### Core AI Catalog's benchmark protocol

The project has a **surprisingly rigorous** benchmark infrastructure:

| Feature | MLPerf | Core AI Catalog | Assessment |
|---|---|---|---|
| **Protocol versioning** | Benchmark versions | `protocol_version: "1.0"` / `"2.0"` | ✅ Comparable |
| **Warmup + measured runs** | Documented | 3 warmup, 10 measured, median + P50/P95 | ✅ Solid |
| **Outlier detection** | Manual review | MAD (Median Absolute Deviation) with anchor cohort | ✅ Novel and well-designed |
| **Anti-gaming** | Institutional audit | Ed25519 signing, DeviceCheck attestation, k=3 suppression | ✅ Strong for community-submitted data |
| **Reproducibility** | Submission includes full config | `environment`, `runtime_config`, `model_hash` | ✅ Good |
| **Standardized workloads** | Fixed benchmarks | Per-model (no standardized suite) | 🟡 Gap — no cross-model comparison benchmark |
| **Result visibility** | Public result tables | Per-model in modal, no leaderboard view | 🔴 **Major gap — no leaderboard** |
| **Trust model** | Institutional | Cryptographic + statistical | Different but valid |

### Key gaps

| Gap | Severity | What to add |
|---|---|---|
| **No benchmark leaderboard** | 🔴 Critical | A sortable, filterable table: model × device × metric → ranked. This is the #1 feature MLPerf and HF Spaces leaderboards offer. The data exists (66 benchmark records) — it's just not surfaced as a comparison view. |
| **No standardized cross-model benchmark** | 🟡 Medium | A "Core AI Benchmark Suite" — same prompt, same device, same protocol across all chat models. Would enable apples-to-apples comparison. MLPerf's power is standardization. |
| **No visual benchmark comparison** | 🟡 Medium | The modal shows numbers in a table. Bar charts, device comparison graphs, or a "benchmarks" tab would make data more digestible. |
| **Trust model not explained on site** | 🟡 Medium | The Ed25519/MAD/anchor-cohort system is sophisticated but invisible on the website. A "How we prevent benchmark gaming" section would build enormous trust. |

### Trust model assessment

The catalog's trust model is **architecturally stronger for community-submitted data** than MLPerf's institutional model — because MLPerf assumes trusted submitters, while this catalog assumes untrusted submitters and uses cryptography + statistics to validate. **This is a differentiator that should be communicated.**

---

## 4. Positioning Gaps

### "Why this exists" — assessment

The README's "Why this exists" section and `PROJECT_PHILOSOPHY.md` are **technically excellent but competitively weak**. They explain what the catalog does and why it's needed, but they don't answer the user's actual question:

> **"Why would I use this instead of just searching Hugging Face?"**

The closest the project gets is in `PROJECT_PHILOSOPHY.md`:

```
Hugging Face Hub = model hub (weights, model cards, spaces)
Apple = runtime/platform ecosystem (Core AI, Core ML, MLX, Neural Engine)
Core AI Catalog = decision + provenance layer between them
```

This is accurate but abstract. A developer reads this and thinks "okay, but I can still just search HF for 'coreai' and find the models."

### Missing elevator pitch

**The project needs a competitive elevator pitch that names the alternative.** Current one-liner:

> *"The agent-ready registry for Apple local AI."*

This is good but doesn't differentiate. Proposed alternatives:

> *"Hugging Face has 1M models and no opinion. Core AI Catalog has 82 models and tells you which one to ship."*

> *"The only place that tells you: which Core AI model runs on your iPhone, what license risk it carries, and how fast it actually is — with proof."*

> *"Stop guessing. Core AI Catalog scores every Apple Core AI model for deployment readiness, verifies its provenance chain, and gives your AI agent the tools to choose for you."*

### Specific positioning gaps

| Gap | Severity | Fix |
|---|---|---|
| **No "vs Hugging Face" comparison on the site** | 🔴 High | Add a comparison table or section: "Why not just search HF?" with specific answers (scoring, recommendations, license triage, provenance, agent-native) |
| **"Agent-ready" isn't explained** | 🔴 High | Most developers don't know what MCP is. Show a concrete example: "Ask Claude: 'find me a vision model for iPhone' → it queries this catalog → returns ranked results" |
| **"Source-grounded" is jargon** | 🟡 Medium | Translate to user benefit: "Every claim links to a real source. No hallucinated metadata." |
| **No success story / use case** | 🟡 Medium | "A developer needed OCR on iPhone. In 30 seconds, the catalog recommended Unlimited-OCR, verified the MIT license, and gave them a Swift snippet." |
| **"82 models" sounds small** | 🟡 Medium | Reframe: "Every known Core AI model" not "82 models." The number should signal completeness, not limitation. |

---

## 5. Site UX vs Competitors

### Current state

The web UI (`site/index.html` + `app.js`) is a **clean, fast, single-page explorer** with:
- Model grid with readiness scores, capability chips, device labels
- Filters: search, capability, device (segmented), license, source, sort
- Model detail modal with score breakdown, benchmarks, provenance chain, install command
- Tasks tab (browse by capability with task synonyms)
- About tab with quick start, MCP setup, scoring explanation
- Dark/light theme, copy buttons, responsive design

### Comparison to Hugging Face's model hub

| UX Feature | HF Model Hub | Core AI Catalog | Severity |
|---|---|---|---|
| **Permalink per model** | `huggingface.co/{org}/{model}` | ❌ No per-model URL (modal only) | 🔴 High (SEO + shareability) |
| **Search relevance** | Full-text + semantic search | Simple `indexOf` substring match | 🟡 Medium |
| **Model detail page** | Full page with tabs (Files, Metrics, Discussions) | Modal popup | 🟡 Medium |
| **Filtering** | By task, library, language, license, size | By capability, device, license, source | 🟢 Good for scope |
| **Sorting** | Trending, downloads, likes, modified | Readiness score, name, size | 🟡 No popularity sort |
| **Visual benchmark display** | Model cards sometimes show eval results | Table in modal (no charts) | 🟡 Medium |
| **Mobile UX** | Responsive | Responsive | 🟢 Parity |
| **Load performance** | Server-rendered | Client-side fetch from raw GitHub | 🟡 Medium (single JSON fetch, but no caching/SWR) |
| **Comparison feature** | ❌ HF has no native comparison | ✅ Side-by-side via CLI/MCP, but **not in web UI** | 🟡 The web UI is missing the compare feature that the CLI has |

### Features that would make this the go-to destination

| Feature | Impact | Effort | Description |
|---|---|---|---|
| **Per-model pages with URLs** | 🔴 Critical | Medium | `/#model/qwen3-vl-2b` deep links. Enables sharing, SEO, and bookmarking. This is table stakes for a model registry. |
| **Benchmark leaderboard tab** | 🔴 Critical | Medium | A dedicated tab showing all benchmark records sortable by metric × device. The "leaderboard" concept that HF Spaces and MLPerf both have. |
| **Side-by-side comparison in web UI** | 🔴 High | Medium | The CLI has `compare` — bring it to the web. Select 2-3 models, see them overlaid. |
| **Visual benchmark charts** | 🟡 High | Medium | Bar charts for throughput comparison. Humans process visual data faster than tables. |
| **"Copy as Swift" integration snippets** | 🟡 High | Low | The CLI generates `snippet.swift` — show it in the modal. |
| **Task-based search in the web UI** | 🟡 High | Medium | The CLI has `recommend --task` — the web UI only has capability filter. A natural-language task search box would be a killer feature. |
| **Keyboard navigation** | 🟢 Medium | Low | Arrow keys to browse models, enter to open, escape to close. Power-user feature. |
| **Bookmark/share filter state** | 🟢 Low | Low | URL-encoded filter state so you can share "vision-language models on iPhone with MIT license" |

### Leaderboard concept

**There is no leaderboard on the site.** This is the single biggest UX gap. The data exists (66 benchmark records, readiness scores for 82 models) — it's just not presented as a ranked comparison.

Recommended leaderboard views:
1. **Readiness leaderboard**: All models ranked by readiness score (exists in CLI, not web)
2. **Throughput leaderboard**: LLM decode tok/s by device class
3. **Latency leaderboard**: Detection/embedding latency by device class
4. **RTF leaderboard**: Audio model realtime factor

---

## 6. Community Features

### Current state

| Feature | Status |
|---|---|
| **Discuss models** | ❌ No per-model discussions (GitHub Issues only) |
| **Request models** | ✅ Issue template exists (`model-request.md`) |
| **Rate models** | ❌ No rating system |
| **Submit benchmarks** | ✅ Issue template + Ed25519 signed intake pipeline |
| **Contribute models** | ✅ CONTRIBUTING.md with templates |
| **Contributor recognition** | ❌ CREDITS.md only (no badges, no profile) |
| **Community showcases** | ❌ No "built with Core AI Catalog" gallery |

### What competitors do

| Feature | HF | MLPerf | CoreML-Models (predecessor) |
|---|---|---|---|
| Discussions | Per-model community tab | — | GitHub Issues |
| Ratings | Likes, downloads | — | GitHub stars |
| Leaderboards | Spaces leaderboards, trending | Result tables | — |
| Contributor profiles | Full user pages | Member organizations | — |
| Showcases | Spaces gallery | — | README links |
| Gamification | Following, likes, org badges | — | — |

### Recommended community features (by impact)

| Feature | Impact | Effort | Description |
|---|---|---|---|
| **Per-model GitHub Discussions** | 🔴 High | Low | Enable GitHub Discussions with a `model-qwen3-vl-2b` category template. Low effort, high engagement. HF's community tab is its stickiest feature. |
| **"Tested on my device" community submissions** | 🔴 High | Medium | Let users report "I ran this on iPhone 15 Pro, got X tok/s" — crowdsource the benchmark dataset. The signed intake pipeline already supports this architecturally. |
| **Contributor badges** | 🟡 Medium | Medium | Badge on CREDITS.md or a contributors page: "Added 5 models", "Submitted 10 benchmarks", "Verified 3 licenses". Gamification drives contribution. |
| **Model rating / "works for me" button** | 🟡 Medium | Medium | Simple thumbs up/down or "confirmed working on [device]" per model. Adds social proof that HF has via downloads/likes. |
| **Showcase gallery** | 🟡 Medium | Low | A `showcase.md` or site section: "Apps built with models from this catalog." Creates an ecosystem flywheel. |
| **Newsletter / changelog** | 🟢 Low | Low | "New models this week" — keeps users coming back. The version history already exists in git. |
| **Discord / community chat** | 🟢 Low | Low | Real-time community for a niche ecosystem. Apple developer communities are underserved. |

---

## Summary: Priority Matrix

### 🔴 Critical (do first)

1. **Benchmark leaderboard** — the data exists, just not surfaced as a ranked view. Highest impact vs MLPerf/HF.
2. **Competitive elevator pitch on homepage** — answer "why not just search HF?" directly.
3. **Per-model pages with permalinks** — table stakes for shareability and SEO.
4. **Per-model discussions (GitHub Discussions)** — the engagement loop that HF has perfected.
5. **Communicate the benchmark anti-gaming infrastructure** — Ed25519 + MAD + anchor cohort is a massive trust differentiator that's invisible.

### 🟡 High value (do next)

6. **Side-by-side comparison in web UI** — the CLI has it, the web doesn't.
7. **Natural-language task search in web UI** — the CLI's killer feature, missing from web.
8. **"Core AI vs MLX vs Core ML" decision widget on homepage** — the comparison doc is excellent but buried.
9. **Visual benchmark charts** — bar graphs beat tables.
10. **Crowdsource "works on my device" reports** — the pipeline exists, just needs a UI.
11. **Contributor recognition system** — badges or profile page.

### 🟢 Nice to have

12. **Keyboard navigation** — power-user feature.
13. **Showcase gallery** — ecosystem flywheel.
14. **Cross-format references** (MLX equivalents).
15. **Standardized cross-model benchmark suite** — the "MLPerf for Core AI."
16. **Newsletter / "new this week" feed.**

---

## The Unique Value Proposition (Not Being Communicated)

The catalog's **actual** unique value, distilled:

> **Core AI Catalog is the only platform that tells you:**
> 1. **Which Core AI model to use** (task-based recommendations, not browsing)
> 2. **Whether you can ship it** (13-factor readiness score — no competitor has this)
> 3. **Where it really came from** (4-layer provenance: creator → recipe → host → license)
> 4. **How fast it actually runs** (environment-scoped benchmarks with anti-gaming)
> 5. **And lets your AI agent do all of this autonomously** (MCP server with 12 tools)

**None of these five points are clearly stated on the homepage.** The homepage leads with "82 models" (a number) instead of "the only platform that..." (a position).

### Recommended hero copy

```
Core AI Catalog
The decision layer for Apple on-device AI.

Hugging Face tells you what models exist.
We tell you which one to ship — with proof.

✓ Task-based recommendations ("find me OCR for iPhone")
✓ 13-factor readiness scoring (can I deploy this tomorrow?)
✓ 4-layer provenance (who made it, who converted it, who hosts it)
✓ Anti-gamed benchmarks (Ed25519-signed, MAD-validated)
✓ Agent-native (12 MCP tools for Claude, Cursor, any AI client)
```

---

*Analysis completed: 2026-07-02. Based on review of README.md, llms.txt, PROJECT_PHILOSOPHY.md, site/index.html, site/app.js, docs/concepts/*, docs/benchmark-protocol.md, docs/privacy-policy.md, docs/anchor-cohort.md, CONTRIBUTING.md, and .github/ISSUE_TEMPLATE/*.*
