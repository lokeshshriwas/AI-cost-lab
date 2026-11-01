# AI Cost Lab

A reproducible benchmark and toolkit that measures how much each LLM cost
optimization saves **at equal quality**. The headline metric is
**cost per successful task**, never cost per call.

> Status: Phase 1 (setup). No benchmark results yet. Full plan: [docs/PLAN.md](docs/PLAN.md).

## What it will show

For three workloads (data extraction, document Q&A, code fixes), the cost and
pass rate of a baseline compared with each optimization: prompt caching, context
trimming, output limits, model cascade, response cache, Batch API, and all of
them combined.

## Setup (Windows PowerShell)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env   # then paste your API key into .env
.venv\Scripts\python -m pytest -q
```

Tests never call the API. Real calls need `COSTLAB_ALLOW_PAID=1` and are
recorded in `cache/` so they're never paid for twice.

## Layout

| Path | What it is |
| --- | --- |
| `costlab/client.py` | The only code that calls the Claude API: cache first, paid-call guard |
| `costlab/cache.py` | Record/replay cache of real responses |
| `costlab/pricing.py` + `prices.yaml` | Token counts to dollars |
| `phase0/` | Phase 0 learning exit check |
| `docs/` | Plan and learning guide |
| `memory/` | Progress, decisions and spend log (read these first when resuming) |

## Licence

MIT
