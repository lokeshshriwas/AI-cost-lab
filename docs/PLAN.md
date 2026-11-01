# AI Cost Lab: Project Plan

Copy of the live planner: https://claude.ai/artifact/KAVtxB1xG8F5XjNJBaCnfu
(the live doc has the architecture diagram). Last synced 2026-11-01. If the two differ, update this
file from the live doc.

## Goal and deliverables

Build an open-source toolkit that proves, with reproducible numbers, how much each AI cost
optimization saves while keeping output quality the same. The headline metric is
**cost per successful task**, never cost per call.

The one-sentence pitch for your CV: *"I built a benchmark and CLI that cut LLM cost by X% at equal
accuracy, measured on N real tasks."*

| # | Deliverable | Why it matters | Priority |
| --- | --- | --- | --- |
| 1 | **Benchmark harness** (Python): 3 workloads, graders, results database | This is the proof. Everything else is packaging. | Must have |
| 2 | **Results report**: one table + one chart per workload, honest about what failed | What recruiters and founders actually read | Must have |
| 3 | **CLI** (`costlab`): run evals, compare strategies, print a savings report | Makes it usable by anyone on their own prompts | Must have |
| 4 | **GitHub repo + README** with the headline numbers in the first screen | Your public portfolio | Must have |
| 5 | **VS Code extension**: thin UI over the CLI (run, view report, estimate cost of a prompt file) | Nice reach, but only after 1 to 4 are solid | Stretch |
| 6 | Blog or LinkedIn post with the chart | Distribution; this is what gets you interviews | Must have |

**What we are NOT building:** a proxy, a hosted dashboard, or a chat app. LiteLLM, Helicone and
Langfuse already do those.

## Budget and limits strategy

Expected cash spend: **$0**. The Team plan's 2 Standard seats include **$40 of Claude API credit
every month** ($20 per seat, pooled), which covers the whole project's planned API use. There are
two separate meters:

| Meter | What it pays for | How it runs out | How we protect it |
| --- | --- | --- | --- |
| **Claude Team seat** | Building the project: Claude Code, chat, planning, reviews | Usage limits that reset over time windows | Small, scoped sessions. One phase step per session. |
| **Monthly API credit** ($40, shown in the Claude Console) | The benchmark calling models through the Claude API | Expires at the end of each billing cycle, no rollover. At $0, requests stop until next month; nothing is charged while auto-reload is off. | Own workspace with a spend limit, cheapest model first, record/replay cache, tiny test sets |

The credit covers the Claude API, Agent SDK and Playground only, not Claude Code. The amount
depends on seats at the start of each billing month: dropping to 1 seat makes it $20.

**Rules that keep spend at $0:**

1. **Keep auto-reload OFF and never click Add funds.** Requests simply stop when the credit hits $0.
2. **Give the project its own Console workspace** (`ai-cost-lab`) with a monthly spend limit (start at $15).
3. **Develop on the cheapest Claude model.** Ollama is optional.
4. **Record once, replay forever.** Every real response is cached; tests and re-runs use no credit.
5. **Smoke set before full set.** 5 tasks first; only a passing smoke run earns a full run.
6. **Plan paid runs around the billing cycle.** Unused credit expires; schedule full runs before renewal.
7. **Use the Batch API for full runs** (50% cheaper, results within hours).
8. **Keep a spend log** (`memory/SPEND.md`), cross-checked against the Console's Cost page.

**Monthly API plan (each month stays inside that month's $40 credit):**

| Month | Phases | Planned API use | Left as buffer |
| --- | --- | --- | --- |
| 1 | 0 Learning, 1 Setup | up to $5 | $35 |
| 2 | 2 Baseline, 3 Optimizations | up to $30 | $10 |
| 3 | 4 Report, 5 CLI, 6 Extension, 7 Launch | up to $15 | $25 |
| **Total** | | **up to $50 of credit, $0 cash** | |

## Architecture

All logic lives in one Python package; the CLI and the VS Code extension are thin front ends.

```
VS Code extension (stretch) --calls--> CLI: costlab (run, compare, report, estimate)
                                          |
             Core library: Runner | Strategies | Graders | Reporter
                    |                                        |
   Model client (Anthropic SDK)                      Results store (SQLite)
   record/replay cache + COSTLAB_ALLOW_PAID guard
        |                  |
   Paid Claude API     Ollama (optional)
```

```
ai-cost-lab/
  CLAUDE.md            project rules for Claude (short)
  memory/              PROGRESS.md, DECISIONS.md, SPEND.md
  costlab/
    client.py          Anthropic SDK wrapper + record/replay cache + paid guard
    runner.py
    strategies/        caching.py, trimming.py, cascade.py, limits.py
    graders/           exact.py, tests.py, judge.py
    report.py
    cli.py
  workloads/           extraction/, qa/, codefix/  (tasks + expected answers)
  cache/               recorded responses (committed, so anyone can replay)
  results/             results.sqlite, RESULTS.md, charts/
  prices.yaml
  tests/
  vscode-extension/    (Phase 6 only)
```

## Phase-by-phase plan

Eight phases, about 8 to 10 weeks at 1 to 2 hours a day. Each phase ends with an **exit check**;
don't start the next phase until it passes. Each numbered step fits **one Claude session**.

### Phase 0: Learning (week 1 to 2, $0)

Detailed checklist: [phase0-learning.md](phase0-learning.md).

1. Python basics refresh if needed: virtual environments, `pip`, functions, classes, `pytest`.
2. How LLM APIs work: messages, system prompt, max tokens, thinking and effort, and above all
   **input vs output tokens and how each is priced**.
3. Structured output: JSON schemas, Pydantic models.
4. Evals: graders, exact match vs rubric vs test-based grading, why a fixed task set matters.
5. Anthropic Python SDK basics: creating a client, reading usage (input, output, cache tokens).
6. Create an API key in your Console workspace and call the cheapest Claude model from Python.

**Exit check:** a ~30-line script that calls a cheap and a strong Claude model with the same prompt,
prints the tokens used, and computes the cost (reference: `phase0/exit_check.py`).

### Phase 1: Project setup (week 2, under $1 of credit)

1. Console: confirm the $40 credit under Billing, check auto-reload is off, create an `ai-cost-lab`
   workspace with a $15 monthly spend limit, create its API key (kept only in `.env`). Create the
   GitHub repo `ai-cost-lab`, MIT licence, `.gitignore` for Python and `.env`.
2. Folder layout and `pyproject.toml`.
3. `CLAUDE.md` and `memory/` (`DECISIONS.md`, `PROGRESS.md`, `SPEND.md`).
4. Model client wrapper through the official Anthropic SDK that **always** passes through the
   record/replay cache.
5. `prices.yaml` copied from the official pricing page.
6. `pytest`, `ruff` and a GitHub Actions workflow with **no API keys** in CI.

**Exit check:** `pytest` passes in CI; calling the cheapest model twice with the same prompt hits
the cache the second time (the Console shows only one request).

### Phase 2: Baseline harness (weeks 3 to 4, cap $5)

1. `Task` and `Result` data models: task id, input, expected output, grader type; result = model,
   tokens in, tokens out, cost, latency, pass/fail.
2. Workload A, **data extraction**: 50 short invoices or emails (self-written, no private data) to
   JSON fields. Grader: exact field match.
3. Workload B, **document Q&A**: one public document set, 50 questions with short reference answers.
   Grader: normalized match, plus an LLM judge only for ambiguous cases.
4. Workload C, **code fixes**: 30 tiny buggy Python functions with unit tests. Grader: tests pass.
5. The runner: run a strategy over a workload, write every result to SQLite.
6. Smoke run (5 tasks per workload) on the cheapest model (Haiku).
7. Full baseline run on the strongest model you plan to compare against, via Batch API.

**Exit check:** a table of pass rate, total cost, cost per successful task and median latency for
each workload x model, generated from SQLite with one command.

### Phase 3: Optimizations, one at a time (weeks 5 to 6, cap $20)

Each optimization is a **strategy** class with the same interface.

1. **Prompt caching**
2. **Context trimming / retrieval**
3. **Output limits**: tight max tokens, "answer only", JSON schema output, lower effort.
4. **Model cascade**: cheap model first; escalate to the strong model if a validator fails.
5. **Response cache**
6. **Batch API** as a pricing mode, reported separately.
7. **Combined** strategy.

For each: smoke run on 5 tasks, check quality held, then one full run.

**Exit check:** every strategy has a full-run row stating quality change vs baseline (in percentage
points), not just cost.

### Phase 4: Results report (week 7, cap $5)

1. Auto-generate `RESULTS.md` and one chart per workload from SQLite.
2. Headline: best cost reduction at a quality loss of at most 1 point.
3. "What didn't work", written honestly.
4. A fresh Claude session reviews the report as a sceptical reader; fix or re-run doubtful numbers.

**Exit check:** someone new can read `RESULTS.md` in 2 minutes and repeat the headline number.

### Phase 5: CLI (week 8, cap $2)

1. `costlab run --workload extraction --strategy cascade`
2. `costlab compare`
3. `costlab report`
4. `costlab estimate prompt.txt --model X`
5. Bring-your-own workload from a JSONL file.
6. `--json` output on every command.
7. Publish to PyPI as `ai-cost-lab`.

**Exit check:** a fresh venv can `pip install ai-cost-lab` and run `costlab compare` on the bundled
cached results without an API key.

### Phase 6: VS Code extension (week 9, $0, stretch)

Only if Phases 0 to 5 passed.

1. Scaffold with `yo code` (TypeScript).
2. "Cost Lab: Estimate this prompt" runs `costlab estimate --json` on the open file.
3. "Cost Lab: Show report" opens the latest report in a webview.
4. Setting for the path to `costlab`.
5. Publish to the VS Code Marketplace.

**Exit check:** a clean VS Code shows a cost estimate for a prompt file in under 3 seconds.

### Phase 7: Launch and job use (week 10, cap $5)

1. README: headline number and chart first, 3-line quickstart, link to `RESULTS.md`.
2. One clean final re-run if any number is older than the latest code.
3. Blog or LinkedIn post: problem, method, chart, what didn't work, repo link.
4. Post in 2 to 3 relevant communities.
5. Add to your CV; send to your friend's orchestration company.

**Exit check:** repo public, post live, project on your CV.

## Testing strategy and quality gates

| Tier | What it tests | Calls a model? | Cost | When it runs |
| --- | --- | --- | --- | --- |
| 1 Unit | Graders, cost math, price table, data models, CLI parsing | No (fake client) | $0 | Every save, every push (CI) |
| 2 Replay | Runner and strategies using recorded responses | No (cache only; a miss fails) | $0 | Every push (CI) |
| 3 Dev | New prompts and strategies end to end | Cheapest Claude model (or Ollama) | Fractions of a cent | While developing a feature |
| 4 Smoke | 5 tasks per workload on a cheap model | Yes | Cents | Before any full run |
| 5 Full | 30 to 50 tasks per workload | Yes, Batch API where possible | Dollars, within the month's plan | Once per strategy, logged in `SPEND.md` |

**Guardrails in the code:** real API calls need `COSTLAB_ALLOW_PAID=1` (CI never sets it); a
`--max-cost` flag on every run (default $1); replay mode is the default in tests.

**Quality gates (all must pass before a number goes into the report):**

1. **Same tasks:** identical task set (checked by a hash of the task file).
2. **Grader sanity:** 100% on expected answers, 0% on obviously wrong ones.
3. **Quality held:** pass rate within 1 point of baseline, or the trade is stated.
4. **Repeatability:** headline strategy run twice with fresh calls (the API no longer accepts
   `temperature`); numbers agree within 5%.
5. **Cost cross-check:** computed cost matches the Console within 5%.
6. **No leakage:** no answers in prompts; no API keys in the repo (CI scan).

## Working routine with Claude

**One numbered step per session, then stop.**

1. Fresh session: *"Read CLAUDE.md and memory/PROGRESS.md. Today's step: Phase 2, step 3. Only touch
   files in workloads/qa/."*
2. Plan first (2 to 3 messages), then build.
3. Run tier 1 and 2 tests (free). No paid calls unless the step needs them.
4. Update `memory/PROGRESS.md` and `memory/DECISIONS.md`.
5. Commit and close.

Habits: point Claude at specific files; keep `CLAUDE.md` short; paste only failing output; do easy
edits yourself; use claude.ai chat for Phase 0 questions; a hit limit is the natural end of a session.

| Day | Work |
| --- | --- |
| Mon to Thu | One step per day, one session each |
| Fri | Smoke or full runs, log spend |
| Sat | Fix what failed; one review session |
| Sun | Rest, or blog notes |

## Risks

| Risk | Early sign | What to do |
| --- | --- | --- |
| API spend creeps up | Workspace spend past half its monthly limit mid-month | Stop full runs, cut the task set to 30, replay from cache |
| Hitting Claude limits every day | Sessions ending mid-step | Smaller steps, fresher sessions, more manual edits |
| Scope creep | "It would be cool if..." | Write it in `IDEAS.md`; build after Phase 7 |
| Weak graders | Grader passes wrong answers | Grader sanity tests before any paid run |
| Prices change | Cost cross-check fails | Update `prices.yaml`; costs recompute from stored tokens |
| Losing motivation | No commits for a week | Ship something small and public each phase |
| VS Code extension eats weeks | Phase 6 past 1 week | Cut it |

## Master progress tracker

- [ ] Phase 0: can call a cheap and a strong Claude model and compute cost
- [ ] Phase 1: repo, CI, cache, `CLAUDE.md` and `memory/` in place; tests pass without keys
- [ ] Phase 2: baseline table for 3 workloads from one command
- [ ] Phase 3: every strategy has a full-run row with quality change
- [ ] Phase 4: `RESULTS.md` readable in 2 minutes, all 6 quality gates passed
- [ ] Phase 5: `pip install ai-cost-lab` works, `costlab compare` runs with no API key
- [ ] Phase 6 (stretch): VS Code extension shows an estimate in under 3 seconds
- [ ] Phase 7: repo public, post live, project on CV
- [ ] Every month's API use stayed within that month's $40 credit; $0 cash spent
