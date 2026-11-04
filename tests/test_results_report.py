import xml.etree.ElementTree as ET

import pytest

from costlab import CallResult, PriceTable, Usage
from costlab.cli import main
from costlab.models import Result
from costlab.results_report import (
    build_results_md,
    chart_svg,
    collect_rows,
    nice_step,
    write_report,
)
from costlab.store import ResultStore

MODEL = "claude-haiku-5-5"


def results(workload, strategy, passes, tokens_in):
    """One Result per entry in `passes`, each costing `tokens_in` input tokens."""
    call = CallResult(MODEL, "", "end_turn", Usage(tokens_in, 10), 0.0, 1.0, False)
    return [Result(f"t{i}", workload, strategy, "", ok, [call]) for i, ok in enumerate(passes)]


@pytest.fixture
def store(tmp_path):
    with ResultStore(tmp_path / "r.sqlite") as s:
        all_pass = [True] * 10
        one_fail = [True] * 9 + [False]
        save = s.save_run
        save(
            workload="qa",
            strategy="baseline",
            model=MODEL,
            tasks_hash="h",
            results=results("qa", "baseline", all_pass, 1000),
        )
        # Cheap but loses 10 points: must not be the headline.
        save(
            workload="qa",
            strategy="lossy",
            model=MODEL,
            tasks_hash="h",
            results=results("qa", "lossy", one_fail, 100),
        )
        # Cheaper and keeps quality: the headline.
        save(
            workload="qa",
            strategy="good",
            model=MODEL,
            tasks_hash="h",
            results=results("qa", "good", all_pass, 400),
        )
        # A smoke run and a run on another task file: both left out of the report.
        save(
            workload="qa",
            strategy="smoke",
            model=MODEL,
            tasks_hash="h",
            results=results("qa", "smoke", [True] * 3, 10),
        )
        save(
            workload="qa",
            strategy="other-file",
            model=MODEL,
            tasks_hash="x",
            results=results("qa", "other-file", all_pass, 10),
        )
        yield s


def test_report_leaves_out_partial_and_other_task_file_runs(store):
    rows = collect_rows(store, PriceTable.load())
    assert {r.strategy for r in rows["qa"]} == {"baseline", "lossy", "good"}


def test_headline_skips_strategies_that_lose_quality(store):
    md = build_results_md(collect_rows(store, PriceTable.load()), notes=None)
    assert "**`good` cut cost per successful task by" in md
    assert "Best with quality held: **`good`**" in md
    # The lossy strategy is listed honestly under what didn't work.
    assert "- `lossy` on qa:" in md and "-10.0 pts" in md


def test_notes_are_included_verbatim(store):
    md = build_results_md(collect_rows(store, PriceTable.load()), notes="## Caveats\n\nx")
    assert md.rstrip().endswith("## Caveats\n\nx")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_chart_is_valid_svg_with_every_strategy_labeled(store, theme):
    rows = collect_rows(store, PriceTable.load())["qa"]
    svg = chart_svg("qa", rows, theme)
    root = ET.fromstring(svg)  # well-formed XML
    texts = [t.text for t in root.iter("{http://www.w3.org/2000/svg}text")]
    for name in ("baseline", "lossy", "good"):
        assert name in texts
    assert root.get("role") == "img" and root.get("aria-label")


def test_nice_step():
    assert nice_step(0.0213) == pytest.approx(0.025)
    assert nice_step(0.03) == pytest.approx(0.05)
    assert nice_step(7) == pytest.approx(10)
    assert nice_step(1) == pytest.approx(1)


def test_write_report_writes_markdown_and_both_chart_themes(store, tmp_path):
    out = tmp_path / "results"
    out.mkdir()
    (out / "notes.md").write_text("## Caveats\n\nhand-written", encoding="utf-8")
    path = write_report(store, PriceTable.load(), out)
    assert "hand-written" in path.read_text(encoding="utf-8")
    assert (out / "charts" / "qa-light.svg").exists()
    assert (out / "charts" / "qa-dark.svg").exists()


def test_cli_report(tmp_path, capsys):
    db = tmp_path / "r.sqlite"
    with ResultStore(db) as s:
        s.save_run(
            workload="qa",
            strategy="baseline",
            model=MODEL,
            tasks_hash="h",
            results=results("qa", "baseline", [True], 100),
        )
    assert main(["report", "--db", str(db), "--out", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "RESULTS.md").exists()


def _replayed_results(workload, strategy, n, tokens_in):
    call = CallResult(MODEL, "", "end_turn", Usage(tokens_in, 10), 0.0, 1.0, True)
    return [Result(f"t{i}", workload, strategy, "", True, [call]) for i in range(n)]


def test_replayed_rows_are_labeled_and_never_reported_as_findings(tmp_path):
    with ResultStore(tmp_path / "r.sqlite") as s:
        s.save_run(
            workload="qa",
            strategy="baseline",
            model=MODEL,
            tasks_hash="h",
            results=results("qa", "baseline", [True] * 4, 1000),
        )
        # Every answer replayed from the baseline's recorded calls (same outputs, from cache).
        s.save_run(
            workload="qa",
            strategy="replay-only",
            model=MODEL,
            tasks_hash="h",
            results=_replayed_results("qa", "replay-only", 4, 1000),
        )
        rows = collect_rows(s, PriceTable.load())
    flags = {r.strategy: r.replayed for r in rows["qa"]}
    assert flags == {"baseline": False, "replay-only": True}
    md = build_results_md(rows, notes=None)
    assert "## Headline" not in md  # nothing measured beat the baseline
    assert "= baseline (replayed)" in md
    assert "- `replay-only` on qa" in md  # listed as not measured
    assert "- `replay-only` on qa:" not in md  # never as a measured finding


def test_batch_headline_splits_out_the_discount_and_names_the_no_wait_option(tmp_path):
    with ResultStore(tmp_path / "r.sqlite") as s:
        for name, tokens in (("baseline", 1000), ("lever", 600), ("lever+batch", 300)):
            s.save_run(
                workload="qa",
                strategy=name,
                model=MODEL,
                tasks_hash="h",
                results=results("qa", name, [True] * 4, tokens),
            )
        md = build_results_md(collect_rows(s, PriceTable.load()), notes=None)
    assert "**`lever+batch` cut cost per successful task by" in md
    assert "against a claude-haiku-5-5 baseline" in md
    assert "50% list-price discount" in md
    assert "**Best without the batch wait:** `lever`" in md
    assert "without losing a single task" in md
