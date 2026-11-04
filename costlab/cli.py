"""`python -m costlab`: run a baseline over a workload, or print the results table.

python -m costlab run extraction --model claude-haiku-5-5          # replay: free
python -m costlab run extraction --model claude-haiku-5-5 --mode record
    # paid: needs COSTLAB_ALLOW_PAID=1 and must be requested by you
python -m costlab table
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from costlab.cache import ResponseCache
from costlab.client import CacheMiss, ModelClient, PaidCallNotAllowed
from costlab.models import load_tasks, summarize, tasks_hash
from costlab.pricing import PriceTable
from costlab.report import build_comparison, build_table
from costlab.results_report import write_report
from costlab.runner import BudgetExceeded, run_batch, run_strategy
from costlab.store import ResultStore
from costlab.strategies import STRATEGIES, Cascade

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "results" / "results.sqlite"


def make_strategy(args):
    cls = STRATEGIES[args.strategy]
    if cls is Cascade:
        return Cascade(model=args.model, strong_model=args.strong_model, max_tokens=args.max_tokens)
    return cls(model=args.model, max_tokens=args.max_tokens)


def cmd_run(args) -> int:
    tasks_path = (
        Path(args.tasks) if args.tasks else ROOT / "workloads" / args.workload / "tasks.jsonl"
    )
    tasks = load_tasks(tasks_path)
    if args.limit is not None:
        # Smoke runs: the first N tasks. The saved hash is still the full file's hash.
        tasks = tasks[: args.limit]
    prices = PriceTable.load()
    client = ModelClient(ResponseCache(), prices, mode=args.mode, cache_tag=args.repeat_tag)
    strategy = make_strategy(args)

    try:
        if args.batch:
            results = run_batch(tasks, strategy, client, prices, max_cost=args.max_cost)
        else:
            results = run_strategy(tasks, strategy, client, prices, max_cost=args.max_cost)
    except (CacheMiss, PaidCallNotAllowed, BudgetExceeded, ValueError) as e:
        print(f"stopped: {e}", file=sys.stderr)
        print("nothing was saved to the results database.", file=sys.stderr)
        return 2

    strategy_name = f"{strategy.name}+batch" if args.batch else strategy.name
    if args.repeat_tag:
        strategy_name += f"@{args.repeat_tag}"
    with ResultStore(args.db) as store:
        run_id = store.save_run(
            workload=args.workload,
            strategy=strategy_name,
            model=args.model,
            tasks_hash=tasks_hash(tasks_path),
            results=results,
        )
    s = summarize(results, prices)
    print(
        f"run {run_id}: {args.workload} / {strategy_name} / {args.model}: "
        f"{s.passed}/{s.tasks} passed, ${s.total_cost_usd:.6f} total"
    )
    return 0


def cmd_table(args) -> int:
    with ResultStore(args.db) as store:
        print(build_table(store, PriceTable.load()))
    return 0


def cmd_compare(args) -> int:
    with ResultStore(args.db) as store:
        print(build_comparison(store, PriceTable.load()))
    return 0


def cmd_report(args) -> int:
    with ResultStore(args.db) as store:
        path = write_report(store, PriceTable.load(), Path(args.out))
    print(f"wrote {path} and charts in {path.parent / 'charts'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")  # ANTHROPIC_API_KEY lives only in .env (gitignored)
    parser = argparse.ArgumentParser(prog="costlab")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the baseline strategy over a workload")
    run.add_argument("workload", help="workload folder name, e.g. extraction, qa, codefix")
    run.add_argument("--model", required=True, help="the model (for cascade: the cheap one)")
    run.add_argument("--strategy", choices=sorted(STRATEGIES), default="baseline")
    run.add_argument(
        "--strong-model", default="claude-sonnet-5-5", help="cascade only: the fallback model"
    )
    run.add_argument("--tasks", help="path to a tasks.jsonl (default: workloads/<workload>/)")
    run.add_argument(
        "--mode",
        choices=["replay", "record"],
        default="replay",
        help="replay (default) uses only the cache; record may call the API",
    )
    run.add_argument("--max-tokens", type=int, default=1024)
    run.add_argument(
        "--max-cost", type=float, default=1.0, help="stop once spend reaches this (USD)"
    )
    run.add_argument("--limit", type=int, help="run only the first N tasks (smoke runs)")
    run.add_argument(
        "--batch",
        action="store_true",
        help="send all tasks as one Message Batch (50%% price, can take up to 24 h); "
        "single-call strategies only",
    )
    run.add_argument(
        "--repeat-tag",
        help="make fresh calls for a repeat run (quality gate 4); saved as <strategy>@<tag>",
    )
    run.add_argument("--db", default=str(DEFAULT_DB))
    run.set_defaults(func=cmd_run)

    table = sub.add_parser("table", help="print the latest run per workload, strategy and model")
    table.add_argument("--db", default=str(DEFAULT_DB))
    table.set_defaults(func=cmd_table)

    compare = sub.add_parser("compare", help="each strategy against the baseline, per workload")
    compare.add_argument("--db", default=str(DEFAULT_DB))
    compare.set_defaults(func=cmd_compare)

    report = sub.add_parser("report", help="write results/RESULTS.md and charts from SQLite")
    report.add_argument("--db", default=str(DEFAULT_DB))
    report.add_argument("--out", default=str(ROOT / "results"))
    report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)
