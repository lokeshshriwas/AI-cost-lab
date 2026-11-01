# Progress

Newest first. One line per finished step.

- 2026-11-01 - Repo pushed to github.com/lokeshshriwas/AI-cost-lab (commit e765611); CI passed.
  Added `phase1/cache_check.py` for the Phase 1 exit check (waiting on the API key).
- 2026-11-01 - Phase 1 scaffold: repo layout, `pyproject.toml`, record/replay cache, paid-call guard,
  `prices.yaml` (checked against the pricing page), 14 passing tests, CI workflow. Phase 0 guide and
  exit-check script written.

## Next
1. Phase 0 learning (see `docs/phase0-learning.md`), then run `phase0/exit_check.py`.
2. Console setup (Phase 1 step 1): confirm credit, auto-reload off, `ai-cost-lab` workspace with a
   $15 spend limit, API key into `.env`.
3. Phase 1 exit check: `phase1/cache_check.py` (needs `.env` with the key and `COSTLAB_ALLOW_PAID=1`).
   Then commit the new `cache/` entry and log the cost in `SPEND.md`.
4. Phase 2 step 1: `Task` and `Result` data models.
