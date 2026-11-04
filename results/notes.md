## Caveats (hand-written, `results/notes.md`)

- **One model, the cheapest.** Every run uses Claude Haiku 5.5, which is also the baseline. It
  already passed 92-100%, so nothing here measures switching models. That is also why the
  cascade could not win: escalating from the cheapest model can only add cost.
- **Small, self-written task sets.** 50 extraction tasks, 50 Q&A questions over two short
  fictional documents, 30 code fixes. One task is 2 points of pass rate (3.3 on code fixes).
- **Quality noise is about 2 points.** Strategies that send exactly the baseline's prompt text
  still moved by 2 points (one task).
- **Cost noise is large too.** On code fixes, `low-effort` and `caching+low-effort` send the same
  text (the shared prefix is too short to cache), yet they came out at -19.5% and -6.2%: about
  13 points apart, from run-to-run variation in how many output (thinking) tokens Haiku spends.
  Every strategy ran once, so treat single-digit differences on one workload as noise.
- **Half the headline is a price, not a measurement.** The Batch API's 50% comes from the price
  list (`batch_multiplier` in `prices.yaml`), applied to the measured tokens. It has not yet
  been checked against the Console bill.
- **Costs are computed, not billed.** Cost comes from stored token counts and `prices.yaml`
  (checked 2026-11-01). Replayed answers are priced as if they were paid, so each row shows what
  the run costs. Actual spend is in `memory/SPEND.md`.
- **The batch runs are stitched together.** In each workload the first 5 answers come from a
  separate 5-task smoke batch, the rest from the full batch. On Q&A that means two cache writes
  instead of one (slightly pessimistic). The 5 extraction smoke answers were recovered from a
  batch whose local process was killed for low memory; they record latency 0, which pulls the
  median latency down a little. Batch latency is the turnaround of the whole batch, not the time
  per answer.

## What didn't work, and why

- **Cascade (Haiku, then Sonnet when a check fails)** cost +145.7% per success on Q&A (+151%
  total cost) for a 2-point gain, which is inside the noise. It escalated 4 of 50 Q&A tasks and
  none elsewhere: the cheap model's answers mostly passed the prompt-only checks, including the
  wrong ones.
- **Prompt caching only helps long shared prefixes.** Claude Haiku 5.5 caches prefixes of 512
  tokens or more. Only the Q&A prompts (about 860 shared tokens) qualify; on extraction and code
  fixes it changed nothing.
- **Context trimming and caching cancel out.** Trimming cut Q&A prompts by ~45% (-46% cost), but
  a trimmed prompt falls under the caching minimum, and caching alone saved more (-81%). The
  retriever was also written by the same person as the questions, so its perfect document
  choice is optimistic.
- **Response cache saved nothing.** The benchmark never repeats a prompt, so every answer was the
  baseline's. Real savings depend on how often production traffic repeats.
- **Combining caching and low effort did not beat the single levers.** Each acts on a different
  workload. Combined, it was close to caching alone on Q&A (-80.5% vs -81.3%) but behind low
  effort alone on extraction (-10.8% vs -13.6%) and code fixes (-6.2% vs -19.5%), differences
  that are within the cost noise above. The large extra saving came from the Batch API, which
  only suits work that can wait.

## Quality gates

| Gate | Status |
| --- | --- |
| 1. Same tasks | Checked automatically: rows whose task-file hash differs from the baseline are left out. |
| 2. Grader sanity | Passed: tests check every grader passes the expected answers and fails wrong ones. |
| 3. Quality held | Per row above (no workload lost more than 1 point, i.e. no task). |
| 4. Repeatability | **Not done yet.** Needs fresh repeat runs (`costlab run --repeat-tag`). |
| 5. Cost cross-check | **Not done yet** (compare the Console Cost page with `memory/SPEND.md`). |
| 6. No leakage | Prompts hold no answers (the cascade's check reads only the prompt); CI scans for API keys. |
