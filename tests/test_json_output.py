"""`--json` on table, compare and spend: real numbers (not formatted strings), null for n/a."""

import json

import pytest

from costlab import CallResult, Usage
from costlab.cli import main
from costlab.models import Result
from costlab.store import ResultStore

MODEL = "claude-haiku-5-5"


def _save(store, workload, strategy, passes, tokens, tasks_hash="h"):
    call = CallResult(MODEL, "", "end_turn", Usage(tokens, 10), 0.0, 1.0, False)
    store.save_run(
        workload=workload,
        strategy=strategy,
        model=MODEL,
        tasks_hash=tasks_hash,
        results=[
            Result(f"t{i}", workload, strategy, "", ok, [call]) for i, ok in enumerate(passes)
        ],
    )


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "r.sqlite"
    with ResultStore(path) as s:
        _save(s, "qa", "baseline", [True] * 4, 1000)
        _save(s, "qa", "lever", [True, True, True, False], 500)
        _save(s, "qa", "smoke", [True], 10)  # partial run
        _save(s, "extraction", "lever", [False] * 2, 100)  # no baseline, nothing passed
    return path


def run_json(capsys, *argv):
    assert main([*argv, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def test_table_json_has_numbers(db, capsys):
    rows = {(r["workload"], r["strategy"]): r for r in run_json(capsys, "table", "--db", str(db))}
    base = rows[("qa", "baseline")]
    assert base["tasks"] == 4 and base["passed"] == 4 and base["pass_rate"] == 1.0
    assert base["total_cost_usd"] == pytest.approx(4 * (1000 * 0.10 + 10 * 0.50) / 1e6)
    assert base["errors"] == 0 and base["tasks_hash"] == "h"
    assert rows[("extraction", "lever")]["cost_per_success_usd"] is None


def test_compare_json_changes_are_fractions_and_null_when_unfair(db, capsys):
    rows = {(r["workload"], r["strategy"]): r for r in run_json(capsys, "compare", "--db", str(db))}
    base, lever = rows[("qa", "baseline")], rows[("qa", "lever")]
    assert base["is_baseline"] and base["quality_change_pts"] is None
    assert lever["quality_change_pts"] == pytest.approx(-25.0)
    per_task = lambda t: (t * 0.10 + 10 * 0.50) / 1e6  # noqa: E731
    assert lever["cost_change"] == pytest.approx(per_task(500) / per_task(1000) - 1)
    assert lever["per_success_change"] == pytest.approx(
        (4 * per_task(500) / 3) / per_task(1000) - 1
    )
    smoke = rows[("qa", "smoke")]
    assert smoke["per_success_change"] is None and smoke["notes"] == ["partial run (1 of 4)"]
    orphan = rows[("extraction", "lever")]
    assert not orphan["has_baseline"] and orphan["notes"] == ["no baseline run"]


def test_json_on_an_empty_database_is_an_empty_list(tmp_path, capsys):
    db = str(tmp_path / "empty.sqlite")
    assert run_json(capsys, "table", "--db", db) == []
    assert run_json(capsys, "compare", "--db", db) == []


def test_spend_json(tmp_path, capsys):
    path = tmp_path / "cache" / "aa" / "aa01.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "model": MODEL,
                "text": "",
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 100_000,
                    "output_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
                "latency_s": 1.0,
                "recorded_at": "2026-11-04T10:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (line,) = run_json(capsys, "spend", "--cache", str(tmp_path / "cache"))
    assert line == {
        "day": "2026-11-04",
        "model": MODEL,
        "batch": False,
        "calls": 1,
        "cost_usd": pytest.approx(0.01),
    }


# ---- rebuild ----


@pytest.mark.parametrize(
    ("strategy", "expected"),
    [
        ("baseline", ["--strategy", "baseline"]),
        ("caching+low-effort", ["--strategy", "caching+low-effort"]),
        ("caching+low-effort+batch", ["--batch", "--strategy", "caching+low-effort"]),
        (
            "caching+low-effort+batch@repeat2",
            ["--batch", "--strategy", "caching+low-effort", "--repeat-tag", "repeat2"],
        ),
        ("baseline@repeat1", ["--strategy", "baseline", "--repeat-tag", "repeat1"]),
    ],
)
def test_replay_argv_round_trips_saved_names(strategy, expected):
    from costlab.cli import replay_argv

    argv = replay_argv("qa", strategy, MODEL)
    assert argv[:6] == ["run", "qa", "--model", MODEL, "--mode", "replay"]
    assert argv[6:] == expected


def test_rebuild_refuses_a_database_that_has_runs(db, tmp_path, capsys):
    manifest = tmp_path / "runs.json"
    manifest.write_text("[]", encoding="utf-8")
    assert main(["rebuild", "--manifest", str(manifest), "--db", str(db)]) == 2
    assert "already has runs" in capsys.readouterr().err


def test_rebuild_replays_each_manifest_run(tmp_path, monkeypatch, capsys):
    import costlab.cli as cli

    seen = []
    real_main = cli.main

    def fake_main(argv):
        if argv[0] == "run":
            seen.append(argv)
            return 0
        return real_main(argv)

    monkeypatch.setattr(cli, "main", fake_main)
    manifest = tmp_path / "runs.json"
    manifest.write_text(
        json.dumps([{"workload": "qa", "strategy": "baseline@repeat1", "model": MODEL}]),
        encoding="utf-8",
    )
    db = str(tmp_path / "new.sqlite")
    assert real_main(["rebuild", "--manifest", str(manifest), "--db", db]) == 0
    assert seen == [[*cli.replay_argv("qa", "baseline@repeat1", MODEL), "--db", db]]
    assert "rebuilt 1 of 1 runs" in capsys.readouterr().out
