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


# ---- repeat runs (quality gate 4) ----


def per_success(tokens_in):
    """Cost per success for `results(...)` rows where every task passes."""
    return (tokens_in * 0.10 + 10 * 0.50) / 1e6


def _save(s, workload, strategy, tokens, passes=(True,) * 4):
    s.save_run(
        workload=workload,
        strategy=strategy,
        model=MODEL,
        tasks_hash="h",
        results=results(workload, strategy, list(passes), tokens),
    )


def test_repeats_fold_into_their_strategy_row_and_never_become_rows(tmp_path):
    with ResultStore(tmp_path / "r.sqlite") as s:
        _save(s, "qa", "baseline", 1000)
        _save(s, "qa", "baseline@repeat1", 1000)
        _save(s, "qa", "lever", 600)
        _save(s, "qa", "lever@repeat1", 605)
        _save(s, "qa", "lever@repeat2", 600, passes=(True,) * 2)  # partial: left out
        rows = {r.strategy: r for r in collect_rows(s, PriceTable.load())["qa"]}
        svg = chart_svg("qa", list(rows.values()), "light")
    assert set(rows) == {"baseline", "lever"}
    assert set(rows["lever"].repeats) == {"repeat1"}
    assert set(rows["lever"].base_repeats) == {"repeat1"}
    assert set(rows["baseline"].repeats) == {"repeat1"}
    assert "@repeat" not in svg


def test_repeat_spread_is_checked_against_five_percent(tmp_path):
    with ResultStore(tmp_path / "r.sqlite") as s:
        _save(s, "qa", "baseline", 1000)
        _save(s, "qa", "steady", 600)
        _save(s, "qa", "steady@repeat1", 605)
        _save(s, "qa", "noisy", 600)
        _save(s, "qa", "noisy@repeat1", 800)
        rows = collect_rows(s, PriceTable.load())
        md = build_results_md(rows, notes=None)
    by_name = {r.strategy: r for r in rows["qa"]}
    assert by_name["steady"].cost_spread == pytest.approx(per_success(605) / per_success(600) - 1)
    assert by_name["noisy"].cost_spread == pytest.approx(per_success(800) / per_success(600) - 1)
    assert "## Repeatability (quality gate 4)" in md
    assert "| qa | `steady` | 2 | 100% |" in md and "| 0.8% | yes |" in md
    assert "| qa | `noisy` | 2 | 100% |" in md and "| **no** |" in md


def test_headline_is_re_measured_against_the_baselines_own_repeat(tmp_path):
    with ResultStore(tmp_path / "r.sqlite") as s:
        _save(s, "qa", "baseline", 1000)
        _save(s, "qa", "baseline@repeat1", 1000)
        _save(s, "qa", "lever", 600)
        _save(s, "qa", "lever@repeat1", 400)
        md = build_results_md(collect_rows(s, PriceTable.load()), notes=None)
    reported = per_success(600) / per_success(1000) - 1
    repeat = per_success(400) / per_success(1000) - 1
    assert f"the cut ranged from {-reported:.1%} to {-repeat:.1%}" in md
    assert f"- `lever`: reported run {reported:+.1%}; repeat1 {repeat:+.1%}." in md
    assert "Not yet repeated" not in md


def test_unrepeated_headline_says_so_and_has_no_repeat_section(tmp_path):
    with ResultStore(tmp_path / "r.sqlite") as s:
        _save(s, "qa", "baseline", 1000)
        _save(s, "qa", "lever", 600)
        md = build_results_md(collect_rows(s, PriceTable.load()), notes=None)
    assert "**Not yet repeated on every workload.**" in md
    assert "## Repeatability" not in md


def test_repeats_on_some_workloads_only_give_no_pooled_repeat(tmp_path):
    with ResultStore(tmp_path / "r.sqlite") as s:
        for workload in ("qa", "extraction"):
            _save(s, workload, "baseline", 1000)
            _save(s, workload, "baseline@repeat1", 1000)
            _save(s, workload, "lever", 600)
        _save(s, "qa", "lever@repeat1", 600)
        md = build_results_md(collect_rows(s, PriceTable.load()), notes=None)
    assert "| qa | `lever` | 2 |" in md
    assert "Repeated on some workloads only, so no pooled repeat yet: `lever`." in md
    assert "**Not yet repeated on every workload.**" in md


# ---- model comparison ----


def _save_model(s, workload, strategy, model, tokens, passes=(True,) * 4):
    call = CallResult(model, "", "end_turn", Usage(tokens, 10), 0.0, 1.0, False)
    s.save_run(
        workload=workload,
        strategy=strategy,
        model=model,
        tasks_hash="h",
        results=[
            Result(f"t{i}", workload, strategy, "", ok, [call]) for i, ok in enumerate(passes)
        ],
    )


def test_strategy_rows_stay_on_the_reference_model(tmp_path):
    from costlab.results_report import collect_models

    with ResultStore(tmp_path / "r.sqlite") as s:
        _save_model(s, "qa", "baseline", MODEL, 1000)
        _save_model(s, "qa", "lever", MODEL, 600)
        _save_model(s, "qa", "baseline", "claude-opus-5-5", 1000)
        rows = collect_rows(s, PriceTable.load())
        models = collect_models(s, PriceTable.load())
    assert [(r.strategy, r.model) for r in rows["qa"]] == [("baseline", MODEL), ("lever", MODEL)]
    assert [r.model for r in models["qa"]] == [MODEL, "claude-opus-5-5"]


def test_model_section_shows_quality_and_cost_multiple(tmp_path):
    from costlab.results_report import collect_models

    with ResultStore(tmp_path / "r.sqlite") as s:
        for w in ("qa", "extraction"):
            _save_model(s, w, "baseline", MODEL, 1000, passes=(True, True, True, False))
            _save_model(s, w, "lever", MODEL, 600)
            _save_model(s, w, "baseline", "claude-opus-5-5", 1000)
        # A smoke run of a third model is left out.
        _save_model(s, "qa", "baseline", "claude-sonnet-5-5", 1000, passes=(True,))
        models = collect_models(s, PriceTable.load())
        md = build_results_md(collect_rows(s, PriceTable.load()), None, models)
    haiku = 4 * (1000 * 0.10 + 10 * 0.50) / 1e6 / 3
    opus = 4 * (1000 * 4.00 + 10 * 20.00) / 1e6 / 4
    assert "## Which model? (plain baseline, no optimizations)" in md
    assert f"| qa | claude-opus-5-5 | 100.0% | +25.0 pts | ${opus * 1000:.3f} " in md
    assert f"| {opus / haiku:.1f}x |" in md
    assert "claude-sonnet-5-5" not in md
    assert f"- `claude-opus-5-5`: 8/8 passed (100.0%), ${opus * 1000:.3f} per 1k successes" in md


def test_no_model_section_with_one_model(store):
    from costlab.results_report import collect_models

    assert collect_models(store, PriceTable.load()) == {}
    assert "Which model?" not in build_results_md(collect_rows(store, PriceTable.load()), None)
