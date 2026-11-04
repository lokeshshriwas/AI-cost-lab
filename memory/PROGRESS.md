# Progress

Newest first. One line per finished step.

- 2026-11-04 - Gate 4 repeat runs, part 1 ($0.026427, logged): baseline repeat1/repeat2 on all
  three workloads (runs 46-51: extraction 48/50 and 47/50 vs 46/50 originally, qa 46 and 47,
  codefix 30 and 30); batch strategy repeat1 on extraction (run 52, 46/50) and qa (run 53, 47/50,
  recovered after a network drop). Not done: batch repeat1 on codefix (failed before sending, no
  charge) and all batch repeat2 runs. RESULTS.md was NOT regenerated: tagged runs would show as
  extra strategy rows until the report folds them into a spread.

- 2026-11-01 - Phase 4 step 4 (sceptical review by a fresh agent, $0 spent): headline reproduced exactly
  (-70.38%). Fixed what it found: two wrong claims in notes.md (cascade "+151% per success" is
  +145.7% per success; "combined matched the best single lever" was false on codefix and
  extraction); headline now names the Haiku 5.5 baseline, the batch wait (~6 min), that ~31 of
  the 70 points are the Batch API list-price discount, the best no-wait strategy
  (caching+low-effort, -38.9%) and qa's 52% share of savings; replay-only rows are labeled
  "= baseline (replayed)" and kept out of findings; tables use cost per 1k successes like the
  charts; notes add cost noise (~13 pts between identical setups) and the stitched/recovered
  batch answers. Added `--repeat-tag` (fresh calls, separate cache keys) for gate 4. 205 tests.

- 2026-11-01 - Phase 4 steps 1-3 ($0 spent, nothing pushed or committed): `python -m costlab report`
  writes `results/RESULTS.md` and light/dark SVG charts per workload (`results/charts/`) from
  SQLite (`costlab/results_report.py`); hand-written caveats in `results/notes.md` are included
  verbatim. Headline: `caching+low-effort+batch` -70.4% cost per success over 130 tasks, quality
  held on every workload. Only full runs on the baseline's task file are reported. Charts checked
  by rendering them in headless Edge. 200 tests passing. Step 4 (sceptical review) in progress.

- 2026-11-01 - **Phase 3 exit check PASSED**: every strategy has a full-run row with its quality
  change vs baseline (`python -m costlab compare`). Batch runs ($0.003355 new spend):
  `caching+low-effort+batch` vs baseline, quality held on all three: qa -89.9%, extraction -56.2%,
  codefix -57.2%. Prompt caching still hits inside a batch (qa: 2 writes, 48 reads vs 1/49
  normally). Month total $0.051908 of $40.

- 2026-11-01 - Phase 3 combined + batch ($0.007616 new spend, logged). `caching+low-effort` full:
  qa -80.5%, extraction -10.8%, codefix -6.2%, quality held: about the best single lever per
  workload, not better (each lever only acts on one workload). The background job was killed by
  Claude Code for low memory during the first batch; the submitted batch
  (msgbatch_01UiUwSbaQPEpoDeXZEJCh3J) was found with `ModelClient.recent_batches()` and recovered
  with `import_batch()`, so it was not paid twice: extraction batch smoke 5/5 at exactly 50% of
  the normal price. Partial runs no longer show deltas in `compare`. 192 tests passing.

- 2026-11-01 - **Phase 3 runs (steps 1-5) + steps 6-7 built** ($0.028932 new spend, logged; nothing
  pushed or committed). Full runs on Haiku 5.5 vs baseline (`python -m costlab compare`):
  qa prompt-caching -81% cost (+2 pts), qa trim-context -46% (+0), low-effort -20% codefix /
  -14% extraction / -4% qa (quality held), cascade +151% on qa for +2 pts (4 escalations, none
  elsewhere), response-cache 0% (no repeated prompts; replayed free). Step 6: `--batch` runs any
  single-call strategy through the Message Batches API at `batch_multiplier` 0.5 from
  prices.yaml, with a worst-case cost check before sending. Step 7: `caching+low-effort`.
  Not yet run: caching+low-effort and any --batch run. 189 tests passing.

- 2026-11-01 - Phase 3 started (code only, $0 spent, nothing pushed or committed): strategies in
  `costlab/strategies/` - `prompt-caching` (cache breakpoint after the shared prefix),
  `trim-context` (QA: send only the matching document; offline check: 49/50 trimmed, 0 wrong
  documents, ~45% fewer characters), `low-effort` (`output_config.effort=low`), `cascade`
  (Haiku first, Sonnet if a prompt-only validator rejects the reply). `python -m costlab run
  --strategy <name>` and `python -m costlab compare` (quality change in points vs baseline,
  flags gate-1 hash mismatches and partial runs). Baseline replays unchanged from cache.
  170 tests passing. Smoke and full runs for these strategies are waiting for a go-ahead.

- 2026-11-01 - **Phase 2 step 7 + exit check: full baseline on Haiku 5.5** (runs 4-6, $0.010628 new
  spend). `python -m costlab table`: extraction 46/50 (92%), qa 46/50 (92%), codefix 30/30 (100%).
  Failures reviewed by hand, answer keys NOT changed: extraction = 2 real model errors (invented
  due dates from "within N days") + 2 judgment-call labels (complaint vs payment); qa = 4 format
  misses under the strict grader ("65 W", "About 20 minutes.", etc.), facts were right.
  Still open: Console cross-check (gate 5) and a stronger-model baseline if wanted.

- 2026-11-01 - Phase 2 step 6 (smoke run, Haiku 5.5, 5 tasks per workload, $0.001377 total):
  extraction 5/5, qa 5/5, codefix 5/5. Outputs spot-checked by hand. Runs 1-3 in
  `results/results.sqlite`; logged in `memory/SPEND.md`. Added `--limit` and `.env` loading to the CLI.

- 2026-11-01 - Phase 2 steps 3-5 (no paid calls, nothing pushed or committed): Workload B
  `workloads/qa/` (fictional returns policy + product sheet, 50 questions, `normalized_text`);
  Workload C `workloads/codefix/` (30 buggy functions with tests, `unit_tests` grader run in a
  separate `python -I` process with a timeout); runner (`costlab/runner.py`, baseline strategy,
  `--max-cost` guard), SQLite store (`costlab/store.py`), table (`costlab/report.py`), CLI
  (`python -m costlab run|table`). Replay of an empty cache stops cleanly and saves nothing.
  150 tests passing. Steps 6 (smoke run) and 7 (full baseline) are NOT done: they spend credit
  and need an explicit go-ahead, so the Phase 2 exit table does not exist yet.

- 2026-11-01 - Phase 2 step 2: Workload A, `workloads/extraction/tasks.jsonl` - 50 invented
  documents (30 invoices, 20 emails) with expected JSON; `costlab/graders/exact.py` (`exact_json`)
  with gate-2 sanity tests (passes every expected answer, fails 13 wrong ones). Dataset checked:
  invoice arithmetic adds up, every expected answer passes its own grader. 52 tests passing. $0 spent.

- 2026-11-01 - Phase 2 step 1: `costlab/models.py` - `Task`, `Result` (holds every call, cost
  recomputed from tokens), `Summary` with cost per successful task, `load_tasks` (JSONL with loud
  errors), `tasks_hash` for quality gate 1. 27 tests passing. $0 spent.

- 2026-11-01 - **Phase 1 exit check PASSED.** `phase1/cache_check.py`: first call paid ($0.000006),
  second from cache; a re-run with paid calls blocked used $0. Key is scoped to the `ai-cost-lab`
  workspace (org-level keys are rejected in this org).

- 2026-11-01 - Repo pushed to github.com/lokeshshriwas/AI-cost-lab (commit e765611); CI passed.
  Added `phase1/cache_check.py` for the Phase 1 exit check (waiting on the API key).
- 2026-11-01 - Phase 1 scaffold: repo layout, `pyproject.toml`, record/replay cache, paid-call guard,
  `prices.yaml` (checked against the pricing page), 14 passing tests, CI workflow. Phase 0 guide and
  exit-check script written.

## Next
1. Finish gate 4: `caching+low-effort --batch --repeat-tag repeat1` on codefix, then `repeat2` on
   all three workloads (~$0.004). Then teach the report to fold `@repeatN` runs into a spread per
   strategy before regenerating RESULTS.md.
2. Quality gate 5: compare the Console Cost page with SPEND.md (~$0.078 for November so far).
3. Phase 4 exit check: someone new reads RESULTS.md in 2 minutes and repeats the headline.
