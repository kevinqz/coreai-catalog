# Core AI License Triage

## When to use
Use this skill when evaluating whether a Core AI model can be used commercially, or when reviewing license risk for a project.

## Prerequisites
Access to the Core AI Catalog data (`catalog.yaml` or the CLI/MCP tools).

## Procedure

1. **Look up the model.**
   ```bash
   coreai-catalog show <model-id>
   ```
   Or via MCP: `check_license(model_id="<id>")`

2. **Check the `commercial_use` field.**
   - `likely` — license permits commercial use (Apache-2.0, MIT, BSD-3)
   - `check_license` — review required (Gemma Terms, OpenRAIL, OpenMDW, etc.)

3. **Identify the license type.**
   - **Apache-2.0** (47 models) — generally safe for commercial use
   - **MIT** (14 models) — permissive, commercial-friendly
   - **BSD-3-Clause** — permissive, commercial-friendly
   - **Gemma Terms** (8 models) — Google's custom terms, review required
   - **LFM Open License** — Liquid AI terms, review required
   - **CC-BY-4.0** — attribution required
   - **OpenRAIL** / **OpenRAIL-M** — use-case restrictions may apply
   - **Stability Community** — Stability AI terms, review required
   - **OpenMDW-1.1** — open model license, review required
   - **Other** — investigate upstream

4. **Check three license layers.** A Core AI model has:
   - **Original model license** (Qwen, Google, Meta, etc.)
   - **Conversion code license** (coreai-model-zoo is BSD-3-Clause)
   - **Artifact license** (usually inherits from original model)

5. **Report findings.**
   ```
   Model: <name>
   License: <license-name>
   Commercial use: <likely | check_license>
   
   Recommendation: <safe to use | review required — check upstream>
   Upstream: <link to original model>
   ```

## Rules

- **Never give legal advice.** The `commercial_use` field is a triage label, not a permission.
- **Always recommend verifying** the upstream license directly.
- **Flag OpenRAIL licenses** — they may restrict specific use cases.
- **Apple-hosted artifacts** are currently always false in this catalog — all artifacts are community-hosted.
