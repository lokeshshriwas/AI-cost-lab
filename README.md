# AI Cost Lab

A reproducible benchmark and toolkit that measures how much each LLM cost
optimization saves **at equal quality**. The headline metric is
**cost per successful task**, never cost per call.

## Results

**Prompt caching + low effort + the Batch API cut cost per successful task by 70.4%**
on Claude Haiku 5.5, across 130 tasks (data extraction, document Q&A, code fixes),
without losing a single task. Two fresh repeats gave -70.9% and -71.0%.

- About 31 of those 70 points are the Batch API's 50% price discount, and batch answers wait
  (about 6 minutes here). The best real-time option, caching + low effort, saved 38.9%.
- **A bigger model was not worth it here.** Sonnet 5.5 and Opus 5.5 cost 18.5x and 41.7x
  Haiku's cost per success and scored about 5 points lower: they "over-help" on
  rule-bound tasks.

Full tables, charts, caveats and what didn't work: [results/RESULTS.md](results/RESULTS.md).

## Reproduce every number, free

All 1,400+ real API answers ship with the package (and are committed in `cache/`), so the
results rebuild in any empty folder, without an API key and without spending anything:

```bash
pip install ai-cost-lab-0.1.0-py3-none-any.whl   # or, in a clone: pip install -e ".[dev]"
costlab rebuild      # replays all 42 reported runs into ./results/results.sqlite
costlab compare      # each strategy against the baseline, per workload
costlab report       # writes ./results/RESULTS.md and the charts
```

costlab reads from the folder you run it in first (your own `prices.yaml`, `workloads/`,
`cache/`), then from the bundled benchmark; it writes only to that folder. Set `COSTLAB_HOME`
to use another folder.

## Use it on your own prompts

```bash
costlab estimate prompt.txt --output-tokens 300   # cost per call on every model, before sending
costlab estimate prompt.txt --offline             # approximate, no API key needed
```

`table`, `compare`, `estimate` and `spend` all accept `--json`.

Running new benchmarks needs an API key in `.env` (copy `.env.example`). Paid calls are blocked
unless `COSTLAB_ALLOW_PAID=1`, every answer is cached so nothing is paid for twice, and
`costlab spend` totals what was actually paid, by day and model.

## Building the package

```bash
python scripts/build_bundle.py               # copies prices, workloads, cache, run list into costlab/_bundle
python -m pip wheel --no-deps . -w dist      # dist/ai_cost_lab-0.1.0-py3-none-any.whl (~0.9 MB)
```

## Layout

| Path | What it is |
| --- | --- |
| `costlab/client.py` | The only code that calls the Claude API: cache first, paid-call guard |
| `costlab/strategies/` | The optimizations: prompt caching, context trimming, low effort, cascade, response cache |
| `costlab/runner.py` | Runs a strategy over a workload and grades every answer |
| `costlab/results_report.py` | Builds `results/RESULTS.md` and the charts from SQLite |
| `workloads/` | The three task sets with expected answers |
| `cache/` | Every recorded API answer (replayed for free) |
| `prices.yaml` | Prices per million tokens; the only place prices live |
| `docs/PLAN.md` | The project plan |
| `memory/` | Progress, decisions and spend log |

## Licence

MIT
