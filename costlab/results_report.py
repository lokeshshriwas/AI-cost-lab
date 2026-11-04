"""Phase 4: write results/RESULTS.md and one chart per workload, generated from SQLite.

Everything here is derived from stored runs, so the report can be rebuilt at any time with
`python -m costlab report` and never drifts from the data. Hand-written caveats live in
`results/notes.md` and are included verbatim.

Charts are static SVG (GitHub shows SVG as an image, so there is no hover layer); the table
next to each chart is the accessible view of the same numbers. Each chart is written in a
light and a dark version and shown with <picture>, so it follows the reader's theme.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from costlab.models import Summary, summarize
from costlab.pricing import PriceTable
from costlab.store import ResultStore

# The quality loss the headline allows, in percentage points (plan: "at most 1 point").
MAX_QUALITY_LOSS_PTS = 1.0

# Chart colors from the dataviz reference palette. Strategy bars: categorical slot 1 (blue).
# Baseline: a neutral reference mark (deliberately gray; it is labeled, never color-only).
THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "ink2": "#52514e",
        "muted": "#898781",
        "axis": "#c3c2b7",
        "grid": "#e1e0d9",
        "bar": "#2a78d6",
        "baseline": "#898781",
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#f0efec",
        "ink2": "#c3c2b7",
        "muted": "#898781",
        "axis": "#383835",
        "grid": "#2c2c2a",
        "bar": "#3987e5",
        "baseline": "#898781",
    },
}


@dataclass(frozen=True)
class Row:
    workload: str
    strategy: str
    model: str
    summary: Summary
    base: Summary
    # True when every answer was replayed from the baseline's own recorded calls: the strategy
    # sent the baseline's exact requests, so the row equals the baseline by construction.
    replayed: bool = False

    @property
    def is_batch(self) -> bool:
        return "+batch" in self.strategy

    @property
    def quality_pts(self) -> float:
        return (self.summary.pass_rate - self.base.pass_rate) * 100

    @property
    def cost_change(self) -> float | None:
        """Change in cost per successful task vs baseline, as a fraction (-0.5 = half)."""
        new, old = self.summary.cost_per_success_usd, self.base.cost_per_success_usd
        if new is None or old is None or old == 0:
            return None
        return new / old - 1

    @property
    def holds_quality(self) -> bool:
        return self.quality_pts >= -MAX_QUALITY_LOSS_PTS


def collect_rows(store: ResultStore, prices: PriceTable) -> dict[str, list[Row]]:
    """Full, comparable runs per workload: same task file and task count as the baseline."""
    runs = store.latest_runs()
    out: dict[str, list[Row]] = {}
    for workload in sorted({r["workload"] for r in runs}):
        in_w = [r for r in runs if r["workload"] == workload]
        bases = [r for r in in_w if r["strategy"] == "baseline"]
        if not bases:
            continue
        rows = []
        for run in in_w:
            base = next((b for b in bases if b["model"] == run["model"]), bases[0])
            if run["tasks_hash"] != base["tasks_hash"] or run["task_count"] != base["task_count"]:
                continue  # gate 1, and no partial (smoke) runs in the report
            results = store.load_results(run["id"])
            base_results = store.load_results(base["id"])
            replayed = (
                run is not base
                and all(c.from_cache for r in results for c in r.calls)
                and [r.output for r in results] == [r.output for r in base_results]
            )
            rows.append(
                Row(
                    workload,
                    run["strategy"],
                    run["model"],
                    summarize(results, prices),
                    summarize(base_results, prices),
                    replayed,
                )
            )
        out[workload] = rows
    return out


def _money(x: float | None) -> str:
    return "n/a" if x is None else f"${x:.6f}"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:+.1%}"


def per_1k(x: float | None) -> str:
    return "n/a" if x is None else f"${x * 1000:.3f}"


# ---- chart ----


def nice_step(raw: float) -> float:
    """Round a raw tick step up to 1, 2, 2.5 or 5 times a power of ten."""
    power = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * power:
            return m * power
    return 10 * power


def chart_svg(workload: str, rows: list[Row], theme: str) -> str:
    """Horizontal bars: cost per 1,000 successful tasks, one bar per strategy."""
    t = THEMES[theme]
    ordered = [r for r in rows if r.strategy == "baseline"] + sorted(
        (r for r in rows if r.strategy != "baseline"),
        key=lambda r: r.summary.cost_per_success_usd or float("inf"),
    )
    width, left, right = 760, 190, 170
    top, row_h, bar_h = 64, 30, 18
    plot_w = width - left - right
    height = top + row_h * len(ordered) + 34
    values = [(r.summary.cost_per_success_usd or 0) * 1000 for r in ordered]
    step = nice_step((max(values) or 1.0) / 4)
    ticks = math.ceil((max(values) or 1.0) / step)
    vmax = step * ticks

    font = "font-family=\"system-ui, -apple-system, 'Segoe UI', sans-serif\""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(workload)}: cost per 1,000 successful tasks by strategy">',
        f'<rect width="{width}" height="{height}" fill="{t["surface"]}"/>',
        f'<text x="16" y="26" {font} font-size="16" font-weight="600" fill="{t["ink"]}">'
        f"{escape(workload)}: cost per 1,000 successful tasks</text>",
        f'<text x="16" y="46" {font} font-size="12" fill="{t["ink2"]}">'
        f"Lower is better. Pass rate after each value. Model: {escape(ordered[0].model)}.</text>",
    ]
    # Recessive gridlines at round values, starting from $0.
    decimals = max(0, -math.floor(math.log10(step)))
    for i in range(ticks + 1):
        x = left + plot_w * i / ticks
        if i:
            parts.append(
                f'<line x1="{x:.1f}" y1="{top - 6}" x2="{x:.1f}" y2="{height - 34}" '
                f'stroke="{t["grid"]}" stroke-width="1"/>'
            )
        parts.append(
            f'<text x="{x:.1f}" y="{height - 16}" {font} font-size="11" fill="{t["muted"]}" '
            f'text-anchor="middle">${step * i:.{decimals}f}</text>'
        )
    for i, (row, value) in enumerate(zip(ordered, values, strict=True)):
        y = top + i * row_h
        w = max(plot_w * value / vmax, 2.0)
        color = t["baseline"] if row.strategy == "baseline" else t["bar"]
        r = min(4.0, w / 2)
        # Rounded data end, square end anchored on the axis.
        path = (
            f"M{left},{y} H{left + w - r:.1f} Q{left + w:.1f},{y} {left + w:.1f},{y + r} "
            f"V{y + bar_h - r} Q{left + w:.1f},{y + bar_h} {left + w - r:.1f},{y + bar_h} "
            f"H{left} Z"
        )
        parts.append(f'<path d="{path}" fill="{color}"/>')
        weight = ' font-weight="600"' if row.strategy == "baseline" else ""
        parts.append(
            f'<text x="{left - 10}" y="{y + bar_h - 5}" {font} font-size="13" '
            f'fill="{t["ink"]}" text-anchor="end"{weight}>{escape(row.strategy)}</text>'
        )
        parts.append(
            f'<text x="{left + w + 8:.1f}" y="{y + bar_h - 5}" {font} font-size="12" '
            f'fill="{t["ink2"]}">{per_1k(row.summary.cost_per_success_usd)} · '
            f"{row.summary.pass_rate:.0%} pass</text>"
        )
    parts.append(
        f'<line x1="{left}" y1="{top - 6}" x2="{left}" y2="{height - 34}" '
        f'stroke="{t["axis"]}" stroke-width="1"/>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


# ---- markdown ----


def _headline(rows: list[Row], real_time_only: bool = False) -> Row | None:
    """Largest cost-per-success cut among measured strategies that keep quality."""
    candidates = [
        r
        for r in rows
        if r.strategy != "baseline"
        and not r.replayed
        and r.holds_quality
        and r.cost_change is not None
        and not (real_time_only and r.is_batch)
    ]
    return min(candidates, key=lambda r: r.cost_change, default=None)


@dataclass(frozen=True)
class Pooled:
    """One strategy over every workload: total cost / total successful tasks."""

    name: str
    rows: tuple[Row, ...]

    @property
    def tasks(self) -> int:
        return sum(r.summary.tasks for r in self.rows)

    @property
    def passed(self) -> int:
        return sum(r.summary.passed for r in self.rows)

    @property
    def cost(self) -> float:
        return sum(r.summary.total_cost_usd for r in self.rows)

    @property
    def per_success(self) -> float | None:
        return self.cost / self.passed if self.passed else None

    @property
    def base_per_success(self) -> float | None:
        passed = sum(r.base.passed for r in self.rows)
        return sum(r.base.total_cost_usd for r in self.rows) / passed if passed else None

    @property
    def change(self) -> float | None:
        new, old = self.per_success, self.base_per_success
        return new / old - 1 if new is not None and old else None

    @property
    def holds(self) -> bool:
        return all(r.holds_quality for r in self.rows)

    @property
    def no_task_lost(self) -> bool:
        return all(r.summary.passed >= r.base.passed for r in self.rows)


def _overall(by_workload: dict[str, list[Row]]) -> list[Pooled]:
    """Strategies with a full run on every workload, best change first, baseline on top."""
    if not by_workload:
        return []
    names = set.intersection(*({r.strategy for r in rows} for rows in by_workload.values()))
    pooled = [
        Pooled(
            name,
            tuple(next(r for r in rows if r.strategy == name) for rows in by_workload.values()),
        )
        for name in names
    ]
    return sorted(
        pooled, key=lambda p: (p.name != "baseline", p.change if p.change is not None else 9.0)
    )


def _minutes(seconds: float) -> str:
    return f"{seconds / 60:.0f} min" if seconds >= 90 else f"{seconds:.0f} s"


def _headline_section(pooled: list[Pooled]) -> list[str]:
    best = sorted(
        (
            p
            for p in pooled
            if p.name != "baseline"
            and p.holds
            and p.change is not None
            and not all(r.replayed for r in p.rows)
        ),
        key=lambda p: p.change,
    )
    if not best:
        return []
    top = best[0]
    kept = (
        "without losing a single task on any workload"
        if top.no_task_lost
        else f"with no workload losing more than {MAX_QUALITY_LOSS_PTS:g} point of pass rate"
    )
    lines = [
        "## Headline",
        "",
        f"**`{top.name}` cut cost per successful task by {-top.change:.1%}** against a "
        f"{top.rows[0].model} baseline, across all {top.tasks} tasks, {kept}.",
        "",
    ]
    if "+batch" in top.name:
        latency = statistics.median(r.summary.median_latency_s for r in top.rows)
        lines.append(
            f"- **It waits for results.** The Batch API answers asynchronously: about "
            f"{_minutes(latency)} here, up to 24 hours by the API's terms."
        )
        plain = next((p for p in pooled if p.name == top.name.replace("+batch", "")), None)
        if plain is not None and plain.change is not None:
            points = (plain.change - top.change) * 100
            lines.append(
                f"- **About {points:.0f} of those {-top.change * 100:.0f} points are the Batch "
                "API's 50% list-price discount** (`batch_multiplier` in `prices.yaml`), not "
                f"measured token savings. The same strategy without batch: {_pct(plain.change)}."
            )
        real_time = [p for p in best if "+batch" not in p.name]
        if real_time:
            lines.append(
                f"- **Best without the batch wait:** `{real_time[0].name}`, "
                f"{_pct(real_time[0].change)}."
            )
    saved = {r.workload: r.base.total_cost_usd - r.summary.total_cost_usd for r in top.rows}
    total_saved = sum(saved.values())
    if total_saved > 0:
        biggest = max(saved, key=lambda w: saved[w])
        lines.append(
            f"- **{biggest} drives {saved[biggest] / total_saved:.0%} of the money saved.** A "
            "different mix of workloads would move the headline; see each workload below."
        )
    lines += [
        "- **Single runs.** Each strategy ran once; read the caveats on noise before quoting "
        "small differences.",
        "",
    ]
    return lines


def _table_rows(rows: list[Row]) -> list[str]:
    ordered = [r for r in rows if r.strategy == "baseline"] + sorted(
        (r for r in rows if r.strategy != "baseline"),
        key=lambda r: (r.replayed, r.summary.cost_per_success_usd or float("inf")),
    )
    out = []
    for r in ordered:
        if r.strategy == "baseline":
            dq = dc = "-"
        elif r.replayed:
            dq = dc = "= baseline (replayed)"
        else:
            dq, dc = f"{r.quality_pts:+.1f} pts", _pct(r.cost_change)
        latency = r.summary.median_latency_s
        shown = _minutes(latency) if r.is_batch else f"{latency:.2f} s"
        out.append(
            f"| `{r.strategy}` | {r.summary.pass_rate:.1%} | {dq} "
            f"| {_money(r.summary.total_cost_usd)} | {per_1k(r.summary.cost_per_success_usd)} "
            f"| {dc} | {shown} |"
        )
    return out


def _workload_section(workload: str, rows: list[Row]) -> list[str]:
    base = next((r for r in rows if r.strategy == "baseline"), None)
    head = _headline(rows)
    head_rt = _headline(rows, real_time_only=True)
    lines = [f"## {workload}", ""]
    if base is not None:
        lines.append(
            f"Baseline: {base.summary.tasks} tasks, {base.summary.pass_rate:.1%} pass, "
            f"{per_1k(base.summary.cost_per_success_usd)} per 1,000 successful tasks."
        )
    if head is not None:
        lines.append(
            f"Best with quality held: **`{head.strategy}`**, {_pct(head.cost_change)} cost "
            f"per success, {head.quality_pts:+.1f} pts."
        )
    if head_rt is not None and head is not None and head_rt is not head:
        lines.append(
            f"Best without the batch wait: **`{head_rt.strategy}`**, "
            f"{_pct(head_rt.cost_change)}, {head_rt.quality_pts:+.1f} pts."
        )
    return [
        *lines,
        "",
        "<picture>",
        f'  <source media="(prefers-color-scheme: dark)" srcset="charts/{workload}-dark.svg">',
        f'  <img alt="{workload}: cost per 1,000 successful tasks by strategy" '
        f'src="charts/{workload}-light.svg">',
        "</picture>",
        "",
        "| Strategy | Pass rate | Quality vs baseline | Total cost | Cost per 1k successes "
        "| vs baseline | Median latency |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        *_table_rows(rows),
        "",
    ]


def _didnt_work_section(by_workload: dict[str, list[Row]]) -> list[str]:
    measured = [r for rows in by_workload.values() for r in rows if r.strategy != "baseline"]
    worse = [
        r
        for r in measured
        if not r.replayed
        and (not r.holds_quality or (r.cost_change is not None and r.cost_change >= 0))
    ]
    replayed = [r for r in measured if r.replayed]
    lines = ["## What didn't work (from the data)", ""]
    if worse:
        lines += [
            "Measured runs that cost the same or more than the baseline, or lost more than "
            f"{MAX_QUALITY_LOSS_PTS:g} point of quality:",
            "",
        ]
        for r in sorted(worse, key=lambda r: (r.workload, r.strategy)):
            lines.append(
                f"- `{r.strategy}` on {r.workload}: {_pct(r.cost_change)} cost per success, "
                f"{r.quality_pts:+.1f} pts."
            )
    else:
        lines.append("No measured run cost more than the baseline or lost quality.")
    if replayed:
        lines += [
            "",
            "Not measured, identical to the baseline: on these workloads the strategy sent the "
            "baseline's exact requests (no escalation, nothing to trim, no repeated prompt), so "
            "its answers are the baseline's recorded ones:",
            "",
        ]
        lines += [
            f"- `{r.strategy}` on {r.workload}"
            for r in sorted(replayed, key=lambda r: (r.workload, r.strategy))
        ]
    lines.append("")
    return lines


def build_results_md(by_workload: dict[str, list[Row]], notes: str | None) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d")
    pooled = _overall(by_workload)
    lines = [
        "# Results",
        "",
        f"_Generated by `python -m costlab report` on {now} from `results/results.sqlite`. "
        "Do not edit by hand: change `results/notes.md` or re-run the report._",
        "",
        *_headline_section(pooled),
        "## All workloads together",
        "",
        'Pooled over every workload: total cost divided by total successful tasks. "Quality '
        f'held" means no workload lost more than {MAX_QUALITY_LOSS_PTS:g} point (one task is '
        "2 points on qa and extraction, 3.3 on codefix, so in practice: no task lost).",
        "",
        "| Strategy | Tasks | Passed | Total cost | Cost per 1k successes | vs baseline "
        "| Quality held |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for p in pooled:
        is_base = p.name == "baseline"
        held = "-" if is_base else ("yes" if p.holds else "**no**")
        if is_base:
            vs = "-"
        elif all(r.replayed for r in p.rows):
            vs, held = "= baseline (replayed)", "-"
        else:
            vs = _pct(p.change)
        lines.append(
            f"| `{p.name}` | {p.tasks} | {p.passed} | {_money(p.cost)} "
            f"| {per_1k(p.per_success)} | {vs} | {held} |"
        )
    lines.append("")
    for workload, rows in by_workload.items():
        lines += _workload_section(workload, rows)
    lines += _didnt_work_section(by_workload)
    if notes:
        lines += [notes.strip(), ""]
    return "\n".join(lines)


def write_report(store: ResultStore, prices: PriceTable, out_dir: Path) -> Path:
    by_workload = collect_rows(store, prices)
    charts = out_dir / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    for workload, rows in by_workload.items():
        for theme in THEMES:
            (charts / f"{workload}-{theme}.svg").write_text(
                chart_svg(workload, rows, theme), encoding="utf-8"
            )
    notes_path = out_dir / "notes.md"
    notes = notes_path.read_text(encoding="utf-8") if notes_path.exists() else None
    path = out_dir / "RESULTS.md"
    path.write_text(build_results_md(by_workload, notes), encoding="utf-8")
    return path
