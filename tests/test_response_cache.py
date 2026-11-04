from pathlib import Path

from costlab import CallResult, PriceTable, Usage
from costlab.models import Task, load_tasks
from costlab.runner import run_strategy
from costlab.strategies.response_cache import ResponseCacheStrategy, prompt_key

MODEL = "claude-haiku-5-5"
ROOT = Path(__file__).resolve().parent.parent / "workloads"


class CountingClient:
    def __init__(self, reply="30"):
        self.reply = reply
        self.calls = []

    def call(self, model, messages, *, max_tokens=1024, **options):
        self.calls.append((model, messages, options))
        return CallResult(model, self.reply, "end_turn", Usage(1_000, 10), 0.0, 0.2, False)


def task(tid, prompt, expected="30"):
    return Task(tid, "qa", prompt, expected, "normalized_text")


def test_repeat_prompt_is_free_and_graded_against_its_own_task():
    client = CountingClient("30")
    strategy = ResponseCacheStrategy(MODEL)
    tasks = [task("a", "How many days?"), task("b", "How  many\ndays?", expected="31")]

    results = run_strategy(tasks, strategy, client, PriceTable.load())

    assert len(client.calls) == 1
    assert strategy.hits == 1
    assert results[1].calls == [] and results[1].cost(PriceTable.load()) == 0.0
    assert [r.passed for r in results] == [True, False]  # same answer, different expected


def test_miss_sends_the_baseline_request_unchanged():
    client = CountingClient()
    ResponseCacheStrategy(MODEL).run(task("a", "Q?"), client)
    assert client.calls == [(MODEL, [{"role": "user", "content": "Q?"}], {})]


def test_errors_are_not_cached():
    class Failing(CountingClient):
        def call(self, *a, **k):
            raise RuntimeError("overloaded")

    strategy = ResponseCacheStrategy(MODEL)
    strategy.run(task("a", "Q?"), Failing())
    assert strategy._seen == {}


def test_key_depends_on_model():
    assert prompt_key("a", "x") != prompt_key("b", "x")


def test_benchmark_tasks_never_repeat():
    # Documents why this strategy saves 0% on the benchmark.
    for name in ("extraction", "qa", "codefix"):
        tasks = load_tasks(ROOT / name / "tasks.jsonl")
        assert len({prompt_key(MODEL, t.input) for t in tasks}) == len(tasks), name
