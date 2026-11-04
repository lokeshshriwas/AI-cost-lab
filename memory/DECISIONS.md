# Decisions

Newest first. Why we chose something, so later sessions don't undo it.

- 2026-11-04 - **results.sqlite stays uncommitted; `results/runs.json` + `cache/` are the source
  of truth.** `costlab rebuild` replays the manifest into a fresh DB and reproduces every number
  exactly, so the DB is a derived file. `rebuild` refuses a DB that already has runs.
- 2026-11-04 - **`--json` emits raw values** (fractions, USD floats, null for n/a), built from the
  same row functions as the Markdown tables, so the two can never disagree.

- 2026-11-04 - **`estimate` counts tokens with the API, not a local tokenizer.** Claude's
  tokenizer is not public and other tokenizers (tiktoken) undercount; count_tokens is free and
  per-model. Counts are cached under their own key (`_count_tokens`) so they never replay as
  answers and never show up as spend. Offline fallback: 2.5 chars/token, measured here.
- 2026-11-04 - **Output tokens are an input to `estimate`, not a guess we hide.** Reply length
  (and thinking) cannot be known before sending; the table states the assumption.

- 2026-11-04 - **A run with API errors is not saved** (exit 3). An error means no answer, not a
  wrong answer; saving it scored a network drop as model failure (Opus qa 8/50 -> 43/50 after a
  re-run). Re-running is cheap: answers that arrived are cached. `--allow-errors` for errors
  that are permanent.
- 2026-11-04 - **The cache is the spend ledger** (`costlab spend`). One cache file = one paid
  answer, including batch answers recovered with `import_batch` that SQLite shows as replayed.
  New entries carry `recorded_at`; older ones use file mtime (wrong in a fresh clone).
- 2026-11-04 - **Strategies are compared on one reference model** (the model with the most
  strategies, Haiku). Other models appear only as plain baselines in "Which model?", so a
  Sonnet baseline never becomes another "baseline" row in Haiku's tables.
- 2026-11-04 - **Answer keys unchanged after the bigger models scored lower.** Their misses are
  real against the task rules (null when the document gives no date, fixed label set, short
  answers); the grader's strictness is written up as a caveat instead.

- 2026-11-04 - **Repeats are paired by tag.** The headline is re-measured as
  `strategy@repeatN` vs `baseline@repeatN` (both fresh), never a fresh strategy run against the
  original baseline, so baseline noise is not counted as a saving or a loss. A pooled repeat
  needs the tag on every workload for both; otherwise the report says it is partial.
- 2026-11-04 - **Gate 4 spread = max/min - 1 of cost per success** across the reported run and its
  repeats, compared with 5% (`MAX_REPEAT_SPREAD`). Kept at 5% as the plan says, even though the
  baseline alone spreads ~6.5%; the report shows that rather than hiding it.

- 2026-11-01 - **RESULTS.md is generated, never hand-edited.** `python -m costlab report` rebuilds it from
  SQLite; only `results/notes.md` is hand-written. Only full runs on the baseline's task file are
  reported. Rows whose answers were all replayed from the baseline are labeled "= baseline
  (replayed)" and never counted as findings or headlines.
- 2026-11-01 - **A batch headline must split out the discount.** When the best strategy uses the Batch
  API, the report states how many points are the list-price discount and names the best
  strategy that needs no wait.
- 2026-11-01 - **Repeat runs use a cache tag** (`--repeat-tag`), part of the cache key only, never sent
  to the API. Untagged keys are unchanged, so existing recorded answers stay valid.

- 2026-11-01 - **Interrupted batches are recovered, not re-sent.** A batch keeps running (and billing)
  after the local process dies. `recent_batches()` finds it and `import_batch()` caches its results
  by custom_id (= the batch cache key); recovered entries record latency 0 rather than a guess.
- 2026-11-01 - **`compare` shows no deltas for partial runs.** A 5-task smoke run against a 50-task
  baseline gave "-95% cost, +8 pts", which is meaningless; the row now shows its own numbers only.

- 2026-11-01 - **Batch calls are cached under their own key** (request + `_batch` marker) and carry a
  `batch` flag through CallResult, the store and the cost math, so batch and normal answers never
  replay each other and batch pricing always comes from `prices.yaml` (`batch_multiplier: 0.5`).
- 2026-11-01 - **A batch is refused up front if its worst-case cost is over --max-cost** (1 token per
  2 prompt characters, full max_tokens of output). A batch cannot be stopped halfway, so the
  per-task budget check used by normal runs does not apply.
- 2026-11-01 - **Only single-call strategies can batch** (they expose `build(task)`). Cascade and the
  response cache decide their next call from earlier answers, so `--batch` rejects them.
- 2026-11-01 - **Combined = prompt caching + low effort.** Trimming is left out (a trimmed qa prompt
  falls under the 512-token caching minimum, cancelling the bigger caching win); cascade is left
  out (+151% cost for +2 points).
- 2026-11-01 - **Run-to-run noise is about 2 points.** Strategies that send the same prompt text as
  the baseline (prompt-caching on extraction) still moved +2 points (one task of 50). Quality
  changes of 2 points or less are noise until gate 4's repeat runs say otherwise.

- 2026-11-01 - **The baseline request is frozen.** `Baseline` must send exactly
  `[{"role": "user", "content": task.input}]` with no extra options, so its recorded replies stay
  valid; a test pins this. Strategies that leave the prompt unchanged (trim on non-QA, the cascade's
  first call) replay baseline answers from cache for free.
- 2026-11-01 - **Prompt caching splits at a per-format marker** ("Question:", "Invoice:", "Email:",
  "Tests:") and puts `cache_control` on the prefix block. The model sees the same text. Only QA's
  prefix (~860 tokens) is over Haiku 5.5's 512-token minimum; the others will show no effect, and
  that is reported, not hidden.
- 2026-11-01 - **The cascade validator only reads the prompt** (listed JSON keys, short-answer shape,
  the tests shown in the prompt), never `task.expected`, so it cannot leak answers.
- 2026-11-01 - **Low effort keeps `max_tokens` at 1024.** `max_tokens` is a cap the model can't see;
  lowering it truncates answers. Effort is the lever that cuts thinking (billed as output).
- 2026-11-01 - **Trimming keeps every document on a tie**, so a weak match never drops the needed
  document. Its retrieval was written by the same person as the questions, so its 0-wrong-document
  result is optimistic; say so in the report.

- 2026-11-01 - **Baseline model is Haiku 5.5**, not the strongest model the plan suggested. The user
  asked for the best result at the lowest cost; Haiku passed 15/15 smoke tasks and the full run
  cost ~$0.01 (a larger model would be ~20x). Phase 3 savings are measured against this baseline.
- 2026-11-01 - **Answer keys stay fixed after seeing results.** The 8 baseline failures were reviewed
  but no expected answer or grader rule was loosened to pass them; that would fit the grader to
  one model's style. Format misses belong to the LLM judge (not built yet), not to the key.

- 2026-11-01 - **`unit_tests` runs code in a separate `python -I` process with a timeout.** That is
  not a security sandbox; it is fine because the code comes from our own model calls on our own
  tasks. Revisit before pointing it at anything untrusted.
- 2026-11-01 - **`normalized_text` is exact after normalizing** (case, punctuation, spacing). The
  prompt asks for a short answer; no sentence-matching. The LLM judge from the plan is not built
  yet, so ambiguous answers simply fail until it is.
- 2026-11-01 - **Cost cap counts cached replays too.** `--max-cost` uses the cost the run represents,
  so a replay can hit the cap; that is deliberate, to keep the guard simple and conservative.
- 2026-11-01 - **A run is saved only when it finishes.** Cache misses, paid-call blocks and budget
  stops abort the run and write nothing, so the table never shows a partial run as complete.
- 2026-11-01 - **API errors count as failed tasks** (with the error text), not as aborts, so a
  flaky API shows up in the table's Errors column instead of hiding.

- 2026-11-01 - **`exact_json` is strict, with two forgivenesses.** The reply must be a JSON object
  equal to the expected one: no extra or missing keys, no type changes, case and punctuation count.
  Only string whitespace is collapsed and a ```json fence is stripped. Booleans are tagged so
  `false` never equals `0` (found by a sanity test).
- 2026-11-01 - **Each extraction task's `input` carries its own instructions and schema**, so the
  prompt is fixed in the task file and covered by the gate-1 hash. The runner just sends `input`.
- 2026-11-01 - **Workload documents are invented** (fictional companies, example.com addresses),
  so they can be committed and shared without private data.
- 2026-11-01 - **Graders live in `costlab/graders/`** (package, listed in `pyproject.toml`), one
  module per grader type, matching the architecture in `docs/PLAN.md`.

- 2026-11-01 - **A `Result` holds a list of calls**, not one call. A cascade makes a cheap call and
  sometimes a strong one; cost per task must add both, each at its own model's price.
- 2026-11-01 - **Failed tasks count in cost per success.** Total cost / passed tasks, so a cheap
  strategy that fails often is not flattered. No passes -> no number (None), never infinity or 0.
- 2026-11-01 - **Tasks are JSONL, one file per workload** (`workloads/<name>/tasks.jsonl`), with
  graders limited to `exact_json`, `normalized_text`, `unit_tests`. Bad files fail loudly with the
  line number.
- 2026-11-01 - **Dataclasses, not Pydantic**, to match the existing code. Revisit if validation grows.

- 2026-11-01 - **Anthropic SDK instead of LiteLLM.** The $40/month Team credit only pays for the
  Claude API, and the SDK reports cache-read and cache-write tokens exactly. Ollama/local models
  are optional and can be added later behind the same `ModelClient` interface.
- 2026-11-01 - **Cost is recomputed from stored token counts** on every read, never stored as
  dollars. A price change needs no re-run.
- 2026-11-01 - **Repeatability = run twice and compare.** The API no longer accepts `temperature`,
  so we can't force deterministic output; quality gate 4 compares two runs within 5%.
- 2026-11-01 - **Cache is committed to git** (`cache/`), so anyone can replay results without a key.
- 2026-11-01 - **YAML for prices** (`prices.yaml`, PyYAML) to match the plan.
