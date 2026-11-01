# Decisions

Newest first. Why we chose something, so later sessions don't undo it.

- 2026-11-01 - **Anthropic SDK instead of LiteLLM.** The $40/month Team credit only pays for the
  Claude API, and the SDK reports cache-read and cache-write tokens exactly. Ollama/local models
  are optional and can be added later behind the same `ModelClient` interface.
- 2026-11-01 - **Cost is recomputed from stored token counts** on every read, never stored as
  dollars. A price change needs no re-run.
- 2026-11-01 - **Repeatability = run twice and compare.** The API no longer accepts `temperature`,
  so we can't force deterministic output; quality gate 4 compares two runs within 5%.
- 2026-11-01 - **Cache is committed to git** (`cache/`), so anyone can replay results without a key.
- 2026-11-01 - **YAML for prices** (`prices.yaml`, PyYAML) to match the plan.
