"""The latest run per (workload, strategy, model), read from SQLite: as rows of plain values
(for `--json`) and as Markdown tables built from those same rows."""

from __future__ import annotations

from typing import Any

from costlab.models import summarize
from costlab.pricing import PriceTable
from costlab.store import ResultStore

HEADER = (
    "| Workload | Strategy | Model | Tasks | Pass rate | Total cost | Cost per success "
    "| Median latency | Errors | Task hash |\n"
    "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"
)


def _money(x: float | None) -> str:
    return "n/a" if x is None else f"${x:.6f}"


def table_rows(store: ResultStore, prices: PriceTable) -> list[dict[str, Any]]:
    rows = []
    for run in store.latest_runs():
        results = store.load_results(run["id"])
        s = summarize(results, prices)
        rows.append(
            {
                "run_id": run["id"],
                "workload": run["workload"],
                "strategy": run["strategy"],
                "model": run["model"],
                "tasks": s.tasks,
                "passed": s.passed,
                "pass_rate": s.pass_rate,
                "total_cost_usd": s.total_cost_usd,
                "cost_per_success_usd": s.cost_per_success_usd,
                "median_latency_s": s.median_latency_s,
                "errors": sum(1 for r in results if r.error),
                "tasks_hash": run["tasks_hash"],
            }
        )
    return rows


def build_table(store: ResultStore, prices: PriceTable) -> str:
    lines = [HEADER]
    for r in table_rows(store, prices):
        lines.append(
            f"| {r['workload']} | {r['strategy']} | {r['model']} | {r['tasks']} "
            f"| {r['pass_rate']:.1%} | ${r['total_cost_usd']:.6f} "
            f"| {_money(r['cost_per_success_usd'])} "
            f"| {r['median_latency_s']:.2f} s | {r['errors']} | `{r['tasks_hash'][:8]}` |"
        )
    if len(lines) == 1:
        lines.append("| _no runs yet_ |  |  |  |  |  |  |  |  |  |")
    return "\n".join(lines)


COMPARE_HEADER = (
    "| Workload | Strategy | Model | Tasks | Pass rate | Quality vs baseline | Total cost "
    "| Cost vs baseline | Cost per success | Per-success vs baseline | Note |\n"
    "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"
)


def _change(new: float | None, old: float | None) -> float | None:
    """Relative change as a fraction (-0.5 = half), or None when it is undefined."""
    if new is None or old is None or old == 0:
        return None
    return new / old - 1


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:+.1%}"


def comparison_rows(store: ResultStore, prices: PriceTable) -> list[dict[str, Any]]:
    """Each strategy's latest run against the baseline for the same workload (and model).

    Quality change is in percentage points, as the Phase 3 exit check asks. Changes are None
    where no fair comparison exists (no baseline, a partial run); `is_baseline` marks the
    baseline row itself.
    """
    runs = store.latest_runs()
    summaries = {r["id"]: summarize(store.load_results(r["id"]), prices) for r in runs}
    rows = []
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
            notes: list[str] = []
            quality = cost = per_success = None
            if base is None:
                notes.append("no baseline run")
            else:
                b = summaries[base["id"]]
                if run is not base:
                    quality = (s.pass_rate - b.pass_rate) * 100
                    cost = _change(s.total_cost_usd, b.total_cost_usd)
                    per_success = _change(s.cost_per_success_usd, b.cost_per_success_usd)
                if run["tasks_hash"] != base["tasks_hash"]:
                    notes.append("different task file: gate 1 fails")
                if run["task_count"] < base["task_count"]:
                    # A smoke run against a full baseline is not comparable: no deltas.
                    notes.append(f"partial run ({run['task_count']} of {base['task_count']})")
                    quality = cost = per_success = None
            rows.append(
                {
                    "run_id": run["id"],
                    "workload": workload,
                    "strategy": run["strategy"],
                    "model": run["model"],
                    "is_baseline": run is base,
                    "has_baseline": base is not None,
                    "tasks": s.tasks,
                    "pass_rate": s.pass_rate,
                    "quality_change_pts": quality,
                    "total_cost_usd": s.total_cost_usd,
                    "cost_change": cost,
                    "cost_per_success_usd": s.cost_per_success_usd,
                    "per_success_change": per_success,
                    "notes": notes,
                }
            )
    return rows


def build_comparison(store: ResultStore, prices: PriceTable) -> str:
    lines = [COMPARE_HEADER]
    for r in comparison_rows(store, prices):
        if r["is_baseline"]:
            dq = dc = dps = "-"
        else:
            q = r["quality_change_pts"]
            dq = "n/a" if q is None else f"{q:+.1f} pts"
            dc, dps = _pct(r["cost_change"]), _pct(r["per_success_change"])
        lines.append(
            f"| {r['workload']} | {r['strategy']} | {r['model']} | {r['tasks']} "
            f"| {r['pass_rate']:.1%} | {dq} | ${r['total_cost_usd']:.6f} | {dc} "
            f"| {_money(r['cost_per_success_usd'])} | {dps} | {'; '.join(r['notes'])} |"
        )
    if len(lines) == 1:
        lines.append("| _no runs yet_ |  |  |  |  |  |  |  |  |  |  |")
    return "\n".join(lines)
