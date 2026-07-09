# Community Watchlist

Curated (not generated). Community Core AI (`.aimodel`) artifacts that surfaced
during upstream discovery but are **not yet catalog-ready**. Revisit when the
blocking reason clears; promote to `catalog.yaml` + `artifacts.yaml` then.

The scope bar for ingestion is a verifiable, atomic `.aimodel` artifact with a
usable model card (see `docs/sota-maintenance.md`). Foreign formats
(MLX / AWQ / GGUF / GPTQ / FP8 / LiteRT) are out of scope by definition.

| Repo | Kind | Surfaced | Why held | Recheck signal |
|---|---|---|---|---|
| [augustZheng/TTS-Core-AI](https://huggingface.co/augustZheng/TTS-Core-AI) | Kokoro-based TTS (Core ML), MIT | 2026-07-09 HF sweep | Experimental "Lab" collection (315 files across many profiles), **no model card**, 13 downloads. Below the atomic-artifact + rich-card ingestion bar. Catalog already indexes `kokoro-82m`. | A pinned, single-profile release with a proper card → evaluate as an alternate Kokoro packaging. |
| [bryanbblewis11/Boogu-CoreAI](https://huggingface.co/bryanbblewis11/Boogu-CoreAI) | Unknown (CoreAI-named) | 2026-07-09 HF sweep + source_monitor | **Gated (HTTP 401)** — contents, base model, license and provenance cannot be verified. | Repo becomes public → inspect and triage. |

## Explicitly excluded (not Core AI)

Recorded so future sweeps don't re-litigate them:

- `ordlibrary/core-ai-clawd-1.5b`, `solanaclawd/solana-clawd-core-ai-1.5b-lora` — Solana/crypto models in **GGUF / LoRA** format; "core-ai" is brand naming, not the Apple Core AI artifact format.
- `lexi-core-ai/*-poc` (gguf-rce, joblib-rce, onnx-overflow, msgpack-segfault, paddle-rce, gguf-dos, …) — security **proof-of-concept** repos, not models.
- `CoreAI-<hash>` repos (e.g. `sharper740/CoreAI-32b85f`, `smart099/CoreAI-1725`) — staging/spam, 0 downloads.
