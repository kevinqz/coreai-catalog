# Site redesign — Apple-like UX/UI overhaul

Status: implemented (site/index.html, site/app.js, site/style.css) and verified in-browser (keyboard nav, dark/light, mobile, console). See "Not in scope" below for deferred items.
Source: multi-persona UX/UI redteam audit (96 findings, 8 personas) + iterative visual brainstorm (v1→v5).

## Goals

- Apple-HIG-quality experience: real keyboard accessibility, 44pt touch targets, visible focus states, type hierarchy, restrained color.
- "I have X, I need Y" mental model: Input→Output is the primary, intelligent filter — not one dropdown among many.
- Zero emoji anywhere. Monoline SVG icons only, consistent stroke weight.
- No regressions to existing Explore/Scores/Tasks/About/Contribute functionality.

## Visual system

- **Theme**: Dark Pro (Direction C), kept as default with existing light-theme toggle preserved.
- **Logo**: replace the "C"-in-a-square wordmark with a "núcleo aninhado" (nested core) mark — concentric vector rings, no letter. Applies to header and favicon.
- **Color**: keep the existing `--accent` blue family; reduce the capability-chip rainbow (11 distinct hues today) to a smaller, deliberate set grouped by modality family rather than one hue per capability.
- **Typography**: replace the current flat rem scale with a real hierarchy (site title must be visually dominant — currently `.header-text h1` at `.92rem` is smaller than body text elsewhere, which is backwards). Increase base sizes for HIG-quality reading (many current sizes sit at .6–.7rem).
- **Spacing**: move from ad hoc rem values to a consistent 4px-based grid; open up whitespace (current layout is packed edge-to-edge).
- **Iconography**: audit `site/index.html` and `app.js`-generated markup for emoji (`➕ 📊 🐞 🔧` in Contribute cards, plus any in dynamically rendered strings) and replace with monoline SVGs matching the existing header icon style.

## Input → Output filter (primary, intelligent)

Applies to both the Explore sidebar and the Scores/Leaderboard filter bar.

- "Eu tenho" (Input) / "Eu quero" (Output) replace the current plain `Input`/`Output` `<select>` pair as the visually primary control — top-aligned bar, not centered, sitting above the rest of the filters.
- Output options are always listed (not hidden) but **dimmed/disabled** when no model exists for the current Input choice, with a model count next to each option (e.g. "Texto (transcrição) — 12 modelos" vs "Imagem — 0, sem modelo").
- When a selected combination only exists with an additional input (e.g. output "texto describing image" needs image+text), show the missing input as a **dashed "suggested" chip** below the bar — one add affordance only (icon), not a duplicated "+" in both icon and label.
- Selected Input/Output render as a **pinned chip** (icon + label + removable ×) at the same height/padding as the closed `<select>` state, so toggling between "open" and "pinned" doesn't shift the arrow/alignment between them.

## Critical/high fixes to land alongside the visual work

Grounded in redteam findings (file:line evidence in the original audit); the audit's adversarial-verification pass hit a provider rate limit partway through, so items marked *(unverified)* are still code-grounded but weren't double-checked by a second pass — treat with slightly lower confidence than the 13 fully confirmed findings, not as unreliable.

**Accessibility (P0 — blocks "Apple-like" claim on its own)**
- Model cards (`.model-card`) and leaderboard rows (`.lb-table tbody tr`) are click-only `div`/`tr` — make them real keyboard-operable controls (`tabindex`, `role="button"` or actual `<button>`, `Enter`/`Space` handling).
- `input:focus, select:focus { outline: none; }` in `style.css:164` strips the focus ring with nothing to replace it — add a visible `:focus-visible` treatment site-wide (nav tabs, icon buttons, chips, copy buttons, filter pills currently rely on browser default or suppress it entirely).
- Modal (`#modal-overlay`) has no accessible name, no focus trap, and doesn't return focus to the triggering element on close.
- Filter `<label>` elements aren't associated with their controls (missing `for`/`id` pairing).
- Filter pills and the score-breakdown toggle are click-only `<span>`s — need keyboard access.
- Header icon buttons are 30×30px (`style.css:109`), under the 44×44pt HIG minimum — same for mobile tab bar and device segmented buttons.

**Trust / data (P0–P1)**
- Leaderboard "Bench" column shows only a count — surface the actual benchmark value the export already provides *(unverified)*.
- No data freshness / last-updated indicator anywhere in the UI *(unverified)*.
- Benchmark `confidence`/`needs_review` state is invisible in leaderboard rows *(unverified)*.
- License trust signal collapses distinct risk levels into one visual treatment with no legend *(unverified)*.

**Content / IA (P1)**
- No headline/explanatory copy above the fold on Explore *(unverified)* — the real pitch currently lives inside a `<noscript>` block (`index.html:115-118`), invisible with JS enabled.
- `.header-tagline` disappears entirely on mobile (`style.css:556`) and is 10.9px on desktop — it's the only plain-language description in the header.
- "Add a Model" (Contribute tab) jumps straight to scripts without stating the actual PR workflow (fork → branch → PR) — confirmed finding, `index.html:327-333`.

**Reliability (P1)**
- Every page load fetches JSON from `raw.githubusercontent.com` with no timeout, retry, or cache — confirmed finding. Add a fetch timeout + one retry + a friendly, actionable error state (current `Failed to load data.` has no retry button — confirmed finding).
- Copy-to-clipboard buttons give no failure feedback when the Clipboard API is blocked — confirmed finding.

## Implementation plan

1. `site/style.css` — design tokens (type scale, spacing scale, restrained chip palette), focus-visible system, 44pt touch targets, logo mark, Input→Output bar + pinned-chip + suggested-chip styles.
2. `site/index.html` — swap logo markup, restructure Explore filter sidebar and Scores filter bar around the new Input→Output component, replace Contribute emoji with inline monoline SVGs, promote a real headline out of `<noscript>`, add ARIA wiring (`for`/`id`, `role`, `aria-live` on result count, modal `aria-labelledby`).
3. `site/app.js` — Input→Output intelligent logic (dim/count unavailable outputs, suggested-input chip, pinned/removable state), keyboard handlers for cards/rows/pills, modal focus trap + return-focus, fetch timeout/retry + retry-capable error UI, clipboard-failure feedback, leaderboard benchmark-value display + confidence indicator.
4. Verify: keyboard-only pass (tab through cards, modal, leaderboard), screenshot dark+light+mobile, `preview_console_logs` for errors.

Not in scope for this pass: full color-blind audit, i18n copy pass for the "international user" persona, full glossary/tooltip system for jargon — flagged for a follow-up.
