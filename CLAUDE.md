# AI Cost Lab - rules for Claude

Read `memory/PROGRESS.md` first. The full plan is `docs/PLAN.md`; work one numbered step per session.

## Stack
- Python 3.12, venv in `.venv` (Windows: `.venv\Scripts\python`).
- Official Anthropic SDK (`anthropic`). No LiteLLM or OpenAI-compatible shims.
- Models: `claude-haiku-5-5` (cheap), `claude-sonnet-5-5`, `claude-opus-5-5` (strong).
- Prices live only in `prices.yaml`. Never hard-code a price in code.

## Commands
- Tests: `.venv\Scripts\python -m pytest -q`
- Lint: `.venv\Scripts\python -m ruff check .` and `ruff format .`

## Money rules (do not break)
- All model calls go through `costlab.client.ModelClient`. Never call the SDK elsewhere
  (only `phase0/exit_check.py` is exempt).
- Never set `COSTLAB_ALLOW_PAID=1` or run a paid command unless the user asks for that run.
- Tests use fakes or replay mode only. A cache miss in tests is a failure, not an API call.
- Budget: $40/month Team API credit; auto-reload stays off. Log every paid run in `memory/SPEND.md`.
- `temperature`/`top_p`/`top_k` are rejected by the API (since 2026-10-21); don't send them.

## Working style
- Keep changes scoped to the files named for the step.
- After a step: add a line to `memory/PROGRESS.md`; record any design choice in `memory/DECISIONS.md`.
