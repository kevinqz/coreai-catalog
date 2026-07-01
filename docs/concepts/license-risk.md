# License Risk: Reading the License Block

The `license` block in `catalog.yaml` is a **triage label**, not a legal opinion. It
exists so developers can quickly filter models by commercial-safety risk before doing
a proper license review. This page explains how to read it, what the common licenses
mean, and how to make a "can I use this commercially?" decision.

> **Not legal advice.** The `commercial_use` field is a heuristic triage label set by
> catalog maintainers. Always verify the upstream model license, conversion code
> license, and artifact hosting license yourself before shipping.

## The `license` block

Every model in `catalog.yaml` carries:

```yaml
license:
  name: Apache-2.0
  commercial_use: likely
```

| Field | Type | Values | Purpose |
|-------|------|--------|---------|
| `name` | string | SPDX-style name or custom label | The license family |
| `commercial_use` | enum | `likely` or `check_license` | Triage flag for commercial use |

There are exactly **two** values for `commercial_use`:

### `commercial_use: likely`

The license is a well-known permissive license (Apache-2.0, MIT) that broadly permits
commercial use with standard obligations (attribution, notice). The catalog marks these
`likely` rather than `yes` because:

- The label reflects the **model's stated license**, not a legal determination.
- Obligations still apply (include license text, state changes, etc.).
- Edge cases exist (patent litigation clauses, trademark restrictions).

### `commercial_use: check_license`

The license is custom, non-standard, or has known restrictions that require human
review before commercial use. This covers:

- **Gemma Terms** — Google's custom license with usage policies.
- **Meta SAM License** — Meta's custom license with acceptable-use conditions.
- **LFM Open License** — Liquid AI's custom license.
- **OpenRAIL** — Responsible AI licenses with use-case restrictions.
- **Apache-2.0 + OpenRAIL++** — Dual-licensed models where the restrictive layer applies.

## Common licenses in the catalog

| License | `commercial_use` | Models | Key characteristics |
|---|---|---|---|
| **Apache-2.0** | `likely` | Majority (Qwen, Granite, RF-DETR, Whisper, etc.) | Permissive; patent grant; attribution required |
| **MIT** | `likely` | GLM-4.7-Flash, Unlimited-OCR | Permissive; minimal obligations; attribution required |
| **Gemma Terms** | `check_license` | Gemma 4 family (E2B, E4B, 12B, 31B), EmbeddingGemma | Google custom license; usage policies; redistribution conditions |
| **Meta SAM License** | `check_license` | SAM 3 | Meta custom license; acceptable-use conditions |
| **LFM Open License v1.0** | `check_license` | LFM2.5-1.2B-Instruct, LFM2.5-8B-A1B | Liquid AI custom license; tiered usage rights |
| **Apache-2.0 + OpenRAIL++** | `check_license` | AdcSR x4 | Dual license; OpenRAIL adds use-case restrictions on top of Apache |

## Four licenses may apply to one model

A single model in the catalog can be governed by **up to four separate licenses**, each
covering a different layer of the stack:

| License layer | What it covers | Where to check |
|---|---|---|
| **Model license** | The trained weights | Original model card on Hugging Face (e.g. `Qwen/Qwen3-VL-2B`) |
| **Code license** | The conversion recipe / scripts | The conversion repo (e.g. `john-rocky/coreai-model-zoo`) |
| **Hosting license** | Terms of the artifact host | Hugging Face terms of service + the host account's repo license |
| **Repo license** | This catalog's code | MIT (see root `LICENSE`) |

> **Example:** Qwen3-VL-2B has **Apache-2.0 weights** (from Qwen), conversion code
> under the **zoo repo's license**, hosted by **mlboydaisuke** under **HF terms**, and
> cataloged under this repo's **MIT license**. All four can differ.

The `license.name` field in `catalog.yaml` reflects the **model weights license** —
the most consequential one for downstream use. But you should verify all layers.

## Decision tree: Can I use this commercially?

```
START: Read catalog.yaml → license.commercial_use
│
├─ likely
│   ├─ Is it Apache-2.0 or MIT?
│   │   ├─ YES → Probably safe. Include license text + notices.
│   │   │        Verify conversion code + hosting terms.
│   │   └─ NO  → Check the specific license anyway.
│   │            (edge cases: patent clauses, trademark limits)
│   │
├─ check_license
│   ├─ Gemma Terms?
│   │   └─ Read Google's Gemma Terms of Use.
│   │      Check prohibited-use policies. May require attribution.
│   │
│   ├─ Meta SAM License?
│   │   └─ Read Meta's SAM license. Check acceptable-use policy.
│   │      Some commercial uses permitted; restrictions apply.
│   │
│   ├─ LFM Open License?
│   │   └─ Read Liquid AI's license. Check tiered usage rights.
│   │      Verify your use case against the tier table.
│   │
│   ├─ OpenRAIL / OpenRAIL++?
│   │   └─ Read the Responsible AI License.
│   │      Use-case restrictions apply (no harm, no deception, etc.)
│   │      These are binding restrictions, not suggestions.
│   │
│   └─ Apache + OpenRAIL++?
│       └─ Both layers apply. The MORE restrictive one wins.
│          You must comply with OpenRAIL use-case restrictions
│          even though Apache-2.0 alone would be permissive.
│
└─ ACTION: When in doubt, consult a lawyer.
           The catalog label is a triage signal, not permission.
```

## Reading the catalog for license filtering

### CLI

```bash
# Only commercially-safe models
coreai-catalog search --capability chat --license likely

# Full license triage for one model
coreai-catalog check-license gemma-4-e2b
```

### MCP (agent API)

```python
# Agent calls check_license tool
check_license(model_id="gemma-4-e2b")
# → { license: "Gemma Terms", commercial_use: "check_license", ... }
```

### YAML (manual)

```yaml
# catalog.yaml — Gemma 4 E2B
license:
  name: Gemma Terms
  commercial_use: check_license   # ← requires review before commercial use

# catalog.yaml — Qwen3.5-0.8B
license:
  name: Apache-2.0
  commercial_use: likely          # ← broadly permissive, verify obligations
```

## Why conservative labels?

The catalog uses `likely` (not `yes`) and `check_license` (not `no`) deliberately:

1. **`likely` prevents false confidence.** Even Apache-2.0 has obligations (patent
   retaliation, state-changes disclosure). "Likely" signals "probably fine, but verify."
2. **`check_license` prevents false rejection.** Gemma Terms and Meta SAM License *do*
   permit many commercial uses — they just require review. "Check" means "look before
   you ship," not "don't use."
3. **No legal advice.** The catalog is an independent project, not affiliated with
   Apple or any model creator. It cannot grant permissions.

## Summary table

| Scenario | `commercial_use` | Action |
|---|---|---|
| Apache-2.0 / MIT model | `likely` | Include license text, verify code + hosting |
| Gemma Terms | `check_license` | Read Google's terms, check usage policy |
| Meta SAM License | `check_license` | Read Meta's license, check acceptable use |
| LFM Open License | `check_license` | Read Liquid AI's tiered license |
| OpenRAIL++ | `check_license` | Read use-case restrictions, comply with all |
| Dual Apache + OpenRAIL | `check_license` | Most restrictive layer wins |
| Unknown / unverified | (field absent or `unknown`) | Treat as `check_license` |

For model-vs-artifact provenance context, see
[Model vs Artifact](./model-vs-artifact.md).
