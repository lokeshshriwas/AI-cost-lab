"""Markdown table of the latest run per (workload, strategy, model), read from SQLite."""

from __future__ import annotations

from costlab.models import summarize
from costlab.pricing import PriceTable
from costlab.store import ResultStore

HEADER = (
    "| Workload | Strategy | Model | Tasks | Pass rate | Total cost | Cost per success "
    "| Median latency | Errors | Task hash |\n"
    "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"
)


def build_table(store: ResultStore, prices: PriceTable) -> str:
    lines = [HEADER]
    for run in store.latest_runs():
        results = store.load_results(run["id"])
        s = summarize(results, prices)
        errors = sum(1 for r in results if r.error)
        per_success = "n/a" if s.cost_per_success_usd is None else f"${s.cost_per_success_usd:.6f}"
        lines.append(
            f"| {run['workload']} | {run['strategy']} | {run['model']} | {s.tasks} "
            f"| {s.pass_rate:.1%} | ${s.total_cost_usd:.6f} | {per_success} "
            f"| {s.median_latency_s:.2f} s | {errors} | `{run['tasks_hash'][:8]}` |"
        )
    if len(lines) == 1:
        lines.append("| _no runs yet_ |  |  |  |  |  |  |  |  |  |")
    return "\n".join(lines)


COMPARE_HEADER = (
    "| Workload | Strategy | Model | Tasks | Pass rate | Quality vs baseline | Total cost "
    "| Cost vs baseline | Cost per success | Per-success vs baseline | Note |\n"
    "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"
)


def _pct_change(new: float | None, old: float | None) -> str:
    if new is None or old is None or old == 0:
        return "n/a"
    return f"{(new / old - 1):+.1%}"


def build_comparison(store: ResultStore, prices: PriceTable) -> str:
    """Each strategy's latest run against the baseline for the same workload (and model).

    Quality change is in percentage points, as the Phase 3 exit check asks.
    """
    runs = store.latest_runs()
    summaries = {r["id"]: summarize(store.load_results(r["id"]), prices) for r in runs}
    lines = [COMPARE_HEADER]
    for workload in sorted({r["workload"] for r in runs}):
        in_workload = [r for r in runs if r["workload"] == workload]
        baselines = [r for r in in_workload if r["strategy"] == "baseline"]
        # Baseline first, then strategies in name order.
        ordered = baselines + sorted(
            (r for r in in_workload if r["strategy"] != "baseline"),
            key=lambda r: (r["strategy"], r["model"]),
        )
        for run in ordered:
            s = summaries[run["id"]]
            same_model = [b for b in baselines if b["model"] == run["model"]]
            base = (same_model or baselines or [None])[0]
            notes = []
            if base is None:
                notes.append("no baseline run")
                dq = dc = dps = "n/a"
            else:
                b = summaries[base["id"]]
                if run is base:
                    dq, dc, dps = "-", "-", "-"
                else:
                    dq = f"{(s.pass_rate - b.pass_rate) * 100:+.1f} pts"
                    dc = _pct_change(s.total_cost_usd, b.total_cost_usd)
                    dps = _pct_change(s.cost_per_success_usd, b.cost_per_success_usd)
                if run["tasks_hash"] != base["tasks_hash"]:
                    notes.append("different task file: gate 1 fails")
                if run["task_count"] < base["task_count"]:
                    # A smoke run against a full baseline is not comparable: no deltas.
                    notes.append(f"partial run ({run['task_count']} of {base['task_count']})")
                    dq = dc = dps = "n/a"
            per_success = (
                "n/a" if s.cost_per_success_usd is None else f"${s.cost_per_success_usd:.6f}"
            )
            lines.append(
                f"| {workload} | {run['strategy']} | {run['model']} | {s.tasks} "
                f"| {s.pass_rate:.1%} | {dq} | ${s.total_cost_usd:.6f} | {dc} "
                f"| {per_success} | {dps} | {'; '.join(notes)} |"
            )
    if len(lines) == 1:
        lines.append("| _no runs yet_ |  |  |  |  |  |  |  |  |  |  |")
    return "\n".join(lines)
