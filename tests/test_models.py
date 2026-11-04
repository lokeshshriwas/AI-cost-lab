import json

import pytest

from costlab import CallResult, PriceTable, Usage
from costlab.models import Result, TaskFileError, load_tasks, summarize, tasks_hash


@pytest.fixture
def prices():
    return PriceTable.load()


def call(model="claude-haiku-5-5", tokens_in=1_000, tokens_out=1_000, latency=1.0):
    return CallResult(
        model=model,
        text="",
        stop_reason="end_turn",
        usage=Usage(input_tokens=tokens_in, output_tokens=tokens_out),
        cost_usd=0.0,  # deliberately wrong: Result must recompute from tokens
        latency_s=latency,
        from_cache=False,
    )


def result(passed, *calls):
    return Result("t", "extraction", "baseline", "out", passed, list(calls))


def write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


TASK = {
    "id": "a1",
    "workload": "extraction",
    "input": "x",
    "expected": {"k": 1},
    "grader": "exact_json",
}


# --- Result and summary -------------------------------------------------------


def test_result_cost_adds_every_call_at_its_own_model_price(prices):
    r = result(True, call("claude-haiku-5-5"), call("claude-opus-5-5"))
    haiku = (1_000 * 0.10 + 1_000 * 0.50) / 1e6
    opus = (1_000 * 4.00 + 1_000 * 20.00) / 1e6
    assert r.cost(prices) == pytest.approx(haiku + opus)


def test_result_latency_is_sum_of_calls():
    assert result(True, call(latency=1.5), call(latency=2.0)).latency_s == pytest.approx(3.5)


def test_cost_per_success_divides_total_cost_by_passes_only(prices):
    one_call = (1_000 * 0.10 + 1_000 * 0.50) / 1e6
    s = summarize([result(True, call()), result(False, call()), result(True, call())], prices)
    assert (s.tasks, s.passed) == (3, 2)
    assert s.pass_rate == pytest.approx(2 / 3)
    # Failed tasks still cost money, so they raise the cost per success.
    assert s.cost_per_success_usd == pytest.approx(3 * one_call / 2)


def test_no_passes_means_no_cost_per_success(prices):
    assert summarize([result(False, call())], prices).cost_per_success_usd is None


def test_median_latency(prices):
    rs = [result(True, call(latency=x)) for x in (1.0, 5.0, 2.0)]
    assert summarize(rs, prices).median_latency_s == 2.0


def test_empty_run_summarizes_to_zeros(prices):
    s = summarize([], prices)
    assert (s.tasks, s.pass_rate, s.total_cost_usd, s.cost_per_success_usd) == (0, 0.0, 0, None)


# --- Task files ----------------------------------------------------------------


def test_load_tasks_reads_rows_and_skips_blank_lines(tmp_path):
    path = tmp_path / "tasks.jsonl"
    path.write_text(json.dumps(TASK) + "\n\n" + json.dumps({**TASK, "id": "a2"}) + "\n")
    tasks = load_tasks(path)
    assert [t.id for t in tasks] == ["a1", "a2"]
    assert tasks[0].expected == {"k": 1} and tasks[0].meta == {}


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([{k: v for k, v in TASK.items() if k != "expected"}], "missing expected"),
        ([{**TASK, "grader": "vibes"}], "unknown grader"),
        ([TASK, TASK], "duplicate id"),
        ([], "no tasks"),
    ],
)
def test_bad_task_files_fail_loudly(tmp_path, rows, message):
    with pytest.raises(TaskFileError, match=message):
        load_tasks(write_jsonl(tmp_path / "tasks.jsonl", rows))


def test_invalid_json_names_the_line(tmp_path):
    path = tmp_path / "tasks.jsonl"
    path.write_text(json.dumps(TASK) + "\n{not json\n")
    with pytest.raises(TaskFileError, match="tasks.jsonl:2"):
        load_tasks(path)


def test_tasks_hash_ignores_line_endings_but_not_content(tmp_path):
    unix, windows, changed = tmp_path / "u", tmp_path / "w", tmp_path / "c"
    unix.write_bytes(b'{"id":"a"}\n')
    windows.write_bytes(b'{"id":"a"}\r\n')
    changed.write_bytes(b'{"id":"b"}\n')
    assert tasks_hash(unix) == tasks_hash(windows)
    assert tasks_hash(unix) != tasks_hash(changed)
