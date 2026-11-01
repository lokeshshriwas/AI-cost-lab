# Progress

Newest first. One line per finished step.

- 2026-11-01 - Phase 1 scaffold: repo layout, `pyproject.toml`, record/replay cache, paid-call guard,
  `prices.yaml` (checked against the pricing page), 14 passing tests, CI workflow. Phase 0 guide and
  exit-check script written.

## Next
1. Phase 0 learning (see `docs/phase0-learning.md`), then run `phase0/exit_check.py`.
2. Console setup (Phase 1 step 1): confirm credit, auto-reload off, `ai-cost-lab` workspace with a
   $15 spend limit, API key into `.env`.
3. `git init`, first commit, push to GitHub; check CI passes.
4. Phase 1 exit check: call `claude-haiku-5-5` twice through `ModelClient`; second call must come from cache.
