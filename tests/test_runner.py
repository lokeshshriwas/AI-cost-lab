import json

import pytest

from costlab import CallResult, PriceTable, ResponseCache, Usage
from costlab.cache import ResponseCache as Cache
from costlab.cli import main
from costlab.client import CacheMiss, ModelClient
from costlab.models import load_tasks, summarize, tasks_hash
from costlab.report import build_table
from costlab.runner import Baseline, BudgetExceeded, grade, run_strategy
from costlab.store import ResultStore

MODEL = "claude-haiku-5-5"


@pytest.fixture
def prices():
    return PriceTable.load()


def write_tasks(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def extraction_rows():
    return [
        {
            "id": "t1",
            "workload": "extraction",
            "input": "doc one",
            "grader": "exact_json",
            "expected": {"total": 5},
        },
        {
            "id": "t2",
            "workload": "extraction",
            "input": "doc two",
            "grader": "exact_json",
            "expected": {"total": 7},
        },
    ]


class FakeClient:
    """Answers from a dict keyed by the task input. Never touches the API."""

    def __init__(self, replies, fail_on=()):
        self.replies = replies
        self.fail_on = set(fail_on)

    def call(self, model, messages, *, max_tokens=1024, **_):
        text = messages[0]["content"]
        if text in self.fail_on:
            raise RuntimeError("rate limited")
        return CallResult(
            model=model,
            text=self.replies[text],
            stop_reason="end_turn",
            usage=Usage(input_tokens=1_000_000, output_tokens=100_000),  # $0.20 for haiku
            cost_usd=0.0,
            latency_s=0.5,
            from_cache=False,
        )


def test_grade_dispatches_on_grader_name():
    task = type("T", (), {"grader": "normalized_text", "expected": "30"})()
    assert grade(task, "30") is True
    assert grade(task, "31") is False


def test_baseline_grades_each_reply(tmp_path, prices):
    path = write_tasks(tmp_path / "tasks.jsonl", extraction_rows())
    tasks = load_tasks(path)
    client = FakeClient({"doc one": '{"total": 5}', "doc two": '{"total": 8}'})

    results = run_strategy(tasks, Baseline(MODEL), client, prices)

    assert [r.passed for r in results] == [True, False]
    assert all(r.strategy == "baseline" for r in results)


def test_api_error_is_recorded_against_the_task(tmp_path, prices):
    path = write_tasks(tmp_path / "tasks.jsonl", extraction_rows())
    tasks = load_tasks(path)
    client = FakeClient({"doc two": '{"total": 7}'}, fail_on={"doc one"})

    results = run_strategy(tasks, Baseline(MODEL), client, prices)

    assert results[0].passed is False
    assert "RuntimeError" in results[0].error
    assert results[1].passed is True


def test_cache_miss_stops_the_run(tmp_path, prices):
    # Replay mode with an empty cache: a miss must stop everything, not count as a failure.
    path = write_tasks(tmp_path / "tasks.jsonl", extraction_rows())
    tasks = load_tasks(path)
    client = ModelClient(ResponseCache(tmp_path / "cache"), prices, mode="replay")

    with pytest.raises(CacheMiss):
        run_strategy(tasks, Baseline(MODEL), client, prices)


def test_budget_stops_the_run(tmp_path, prices):
    path = write_tasks(tmp_path / "tasks.jsonl", extraction_rows())
    tasks = load_tasks(path)
    client = FakeClient({"doc one": "{}", "doc two": "{}"})

    with pytest.raises(BudgetExceeded):
        run_strategy(tasks, Baseline(MODEL), client, prices, max_cost=0.10)


def test_store_round_trip_and_summary(tmp_path, prices):
    path = write_tasks(tmp_path / "tasks.jsonl", extraction_rows())
    tasks = load_tasks(path)
    client = FakeClient({"doc one": '{"total": 5}', "doc two": '{"total": 8}'})
    results = run_strategy(tasks, Baseline(MODEL), client, prices)

    with ResultStore(tmp_path / "r.sqlite") as store:
        run_id = store.save_run(
            workload="extraction",
            strategy="baseline",
            model=MODEL,
            tasks_hash=tasks_hash(path),
            results=results,
        )
        loaded = store.load_results(run_id)

    assert [(r.task_id, r.passed, r.output) for r in loaded] == [
        ("t1", True, '{"total": 5}'),
        ("t2", False, '{"total": 8}'),
    ]
    # Cost is recomputed from tokens on read, so it matches the live run exactly.
    assert summarize(loaded, prices).total_cost_usd == pytest.approx(
        summarize(results, prices).total_cost_usd
    )


def test_latest_run_wins_in_the_table(tmp_path, prices):
    path = write_tasks(tmp_path / "tasks.jsonl", extraction_rows())
    tasks = load_tasks(path)
    failing = FakeClient({"doc one": "{}", "doc two": "{}"})
    passing = FakeClient({"doc one": '{"total": 5}', "doc two": '{"total": 7}'})

    with ResultStore(tmp_path / "r.sqlite") as store:
        for client in (failing, passing):
            store.save_run(
                workload="extraction",
                strategy="baseline",
                model=MODEL,
                tasks_hash=tasks_hash(path),
                results=run_strategy(tasks, Baseline(MODEL), client, prices),
            )
        table = build_table(store, prices)

    assert table.count("| extraction |") == 1  # one line per (workload, strategy, model)
    assert "| 100.0% |" in table
    assert "$" in table


def test_cli_table_on_empty_db(tmp_path, capsys):
    assert main(["table", "--db", str(tmp_path / "empty.sqlite")]) == 0
    assert "no runs yet" in capsys.readouterr().out


def test_cli_run_in_replay_mode_with_empty_cache_saves_nothing(tmp_path, capsys, monkeypatch):
    # The real CLI with an empty cache: must stop with exit code 2 and write no run.
    tasks = write_tasks(tmp_path / "tasks.jsonl", extraction_rows())
    monkeypatch.setattr("costlab.cli.ResponseCache", lambda: Cache(tmp_path / "cache"))
    db = tmp_path / "r.sqlite"

    code = main(["run", "extraction", "--model", MODEL, "--tasks", str(tasks), "--db", str(db)])

    assert code == 2
    assert "nothing was saved" in capsys.readouterr().err
    with ResultStore(db) as store:
        assert store.latest_runs() == []


def test_cli_limit_runs_only_first_n_tasks(tmp_path, monkeypatch):
    tasks = write_tasks(tmp_path / "tasks.jsonl", extraction_rows())
    seen = []

    class Recorder(FakeClient):
        def call(self, model, messages, **kw):
            seen.append(messages[0]["content"])
            return super().call(model, messages, **kw)

    monkeypatch.setattr("costlab.cli.ResponseCache", lambda: Cache(tmp_path / "cache"))
    monkeypatch.setattr(
        "costlab.cli.ModelClient", lambda *a, **k: Recorder({"doc one": "{}", "doc two": "{}"})
    )
    db = tmp_path / "r.sqlite"

    assert (
        main(
            [
                "run",
                "extraction",
                "--model",
                MODEL,
                "--tasks",
                str(tasks),
                "--db",
                str(db),
                "--limit",
                "1",
            ]
        )
        == 0
    )
    assert seen == ["doc one"]


class FlakyClient(FakeClient):
    """Answers "doc one" and fails "doc two" like a dropped connection."""

    def call(self, model, messages, **kw):
        if messages[0]["content"] == "doc two":
            raise ConnectionError("Connection error.")
        return super().call(model, messages, **kw)


def _run_flaky(tmp_path, monkeypatch, *extra):
    tasks = write_tasks(tmp_path / "tasks.jsonl", extraction_rows())
    monkeypatch.setattr("costlab.cli.ResponseCache", lambda: Cache(tmp_path / "cache"))
    monkeypatch.setattr(
        "costlab.cli.ModelClient", lambda *a, **k: FlakyClient({"doc one": "{}", "doc two": "{}"})
    )
    db = tmp_path / "r.sqlite"
    code = main(
        ["run", "extraction", "--model", MODEL, "--tasks", str(tasks), "--db", str(db), *extra]
    )
    with ResultStore(db) as store:
        return code, store.latest_runs()


def test_cli_does_not_save_a_run_with_api_errors(tmp_path, capsys, monkeypatch):
    code, runs = _run_flaky(tmp_path, monkeypatch)
    assert code == 3
    assert runs == []
    err = capsys.readouterr().err
    assert "1 of 2 tasks got no answer from the API" in err
    assert "ConnectionError: Connection error." in err


def test_cli_allow_errors_saves_them_as_failures(tmp_path, monkeypatch):
    code, runs = _run_flaky(tmp_path, monkeypatch, "--allow-errors")
    assert code == 0
    assert [r["task_count"] for r in runs] == [2]
