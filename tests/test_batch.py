from types import SimpleNamespace

import pytest

from costlab import CacheMiss, ModelClient, PaidCallNotAllowed, PriceTable, ResponseCache, Usage
from costlab.cli import main
from costlab.client import BatchRequestFailed
from costlab.models import Task
from costlab.runner import Baseline, BudgetExceeded, batch_requests, run_batch, worst_case_cost
from costlab.store import ResultStore
from costlab.strategies import Cascade, LowEffort, ResponseCacheStrategy

MODEL = "claude-haiku-5-5"


def message(text, tokens_in=1_000, tokens_out=100):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason="end_turn",
        usage=SimpleNamespace(
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            cache_creation_input_tokens=None,
            cache_read_input_tokens=None,
        ),
    )


class FakeBatches:
    """Stands in for sdk.messages.batches. Answers with the prompt's last word, or fails."""

    def __init__(self, fail_ids=(), polls_before_end=1):
        self.created = []
        self.fail_ids = set(fail_ids)
        self.polls_left = polls_before_end

    def create(self, requests):
        self.created.append(requests)
        self.requests = requests
        return SimpleNamespace(id="batch_1", processing_status="in_progress")

    def retrieve(self, batch_id):
        self.polls_left -= 1
        status = "ended" if self.polls_left <= 0 else "in_progress"
        return SimpleNamespace(id=batch_id, processing_status=status)

    def results(self, batch_id):
        for r in self.requests:
            prompt = r["params"]["messages"][0]["content"]
            if prompt in self.fail_ids:
                yield SimpleNamespace(
                    custom_id=r["custom_id"], result=SimpleNamespace(type="errored")
                )
            else:
                yield SimpleNamespace(
                    custom_id=r["custom_id"],
                    result=SimpleNamespace(type="succeeded", message=message(prompt.split()[-1])),
                )


class FakeSDK:
    def __init__(self, batches):
        self.messages = SimpleNamespace(batches=batches, create=self._create)
        self.single_calls = 0

    def _create(self, **request):
        self.single_calls += 1
        return message("single")


def request(prompt):
    return {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 64}


@pytest.fixture
def paid(monkeypatch):
    monkeypatch.setenv("COSTLAB_ALLOW_PAID", "1")


def make_client(tmp_path, batches, mode="record"):
    return ModelClient(
        ResponseCache(tmp_path / "cache"), PriceTable.load(), mode=mode, sdk_client=FakeSDK(batches)
    )


def test_batch_results_come_back_in_request_order_at_half_price(tmp_path, paid):
    batches = FakeBatches()
    client = make_client(tmp_path, batches)

    out = client.call_batch([request("say alpha"), request("say beta")], poll_s=0)

    assert [r.text for r in out] == ["alpha", "beta"]
    assert all(r.batch and not r.from_cache for r in out)
    prices = PriceTable.load()
    assert out[0].cost_usd == pytest.approx(prices.cost(MODEL, Usage(1_000, 100)) * 0.5)


def test_batch_answers_are_cached_and_replay_for_free(tmp_path, paid):
    batches = FakeBatches()
    make_client(tmp_path, batches).call_batch([request("say alpha")], poll_s=0)

    replay = make_client(tmp_path, FakeBatches(), mode="replay")
    out = replay.call_batch([request("say alpha")], poll_s=0)
    assert out[0].from_cache and out[0].batch and out[0].text == "alpha"


def test_batch_and_normal_answers_never_replay_each_other(tmp_path, paid):
    batches = FakeBatches()
    client = make_client(tmp_path, batches)
    client.call_batch([request("say alpha")], poll_s=0)

    # A normal call of the same prompt is a different request: it must not reuse the batch answer.
    single = client.call(MODEL, request("say alpha")["messages"], max_tokens=64)
    assert single.text == "single" and single.batch is False


def test_only_missing_requests_are_sent_and_duplicates_collapse(tmp_path, paid):
    batches = FakeBatches()
    client = make_client(tmp_path, batches)
    client.call_batch([request("say alpha")], poll_s=0)

    out = client.call_batch(
        [request("say alpha"), request("say beta"), request("say beta")], poll_s=0
    )
    assert [r.text for r in out] == ["alpha", "beta", "beta"]
    assert len(batches.created[-1]) == 1  # only "beta", once


def test_failed_requests_come_back_as_errors_and_are_not_cached(tmp_path, paid):
    batches = FakeBatches(fail_ids={"say beta"})
    client = make_client(tmp_path, batches)

    out = client.call_batch([request("say alpha"), request("say beta")], poll_s=0)
    assert out[0].text == "alpha"
    assert isinstance(out[1], BatchRequestFailed) and "errored" in str(out[1])

    with pytest.raises(CacheMiss):
        make_client(tmp_path, FakeBatches(), mode="replay").call_batch(
            [request("say beta")], poll_s=0
        )


def test_replay_miss_and_paid_guard_send_nothing(tmp_path, monkeypatch):
    batches = FakeBatches()
    with pytest.raises(CacheMiss):
        make_client(tmp_path, batches, mode="replay").call_batch([request("x")], poll_s=0)
    monkeypatch.delenv("COSTLAB_ALLOW_PAID", raising=False)
    with pytest.raises(PaidCallNotAllowed):
        make_client(tmp_path, batches).call_batch([request("x")], poll_s=0)
    assert batches.created == []


def test_batch_times_out(tmp_path, paid):
    client = make_client(tmp_path, FakeBatches(polls_before_end=10**9))
    with pytest.raises(TimeoutError):
        client.call_batch([request("x")], poll_s=0, timeout_s=0)


# ---- runner ----


def tasks():
    return [
        Task("a", "qa", "answer alpha", "alpha", "normalized_text"),
        Task("b", "qa", "answer beta", "nope", "normalized_text"),
    ]


def test_batch_requests_match_the_normal_requests():
    # Same body as the normal path, so the only differences are price and turnaround.
    reqs = batch_requests(tasks(), LowEffort(MODEL))
    assert reqs[0] == {
        "model": MODEL,
        "messages": [{"role": "user", "content": "answer alpha"}],
        "max_tokens": 1024,
        "output_config": {"effort": "low"},
    }


def test_multi_call_strategies_cannot_batch():
    for strategy in (Cascade(MODEL), ResponseCacheStrategy(MODEL)):
        with pytest.raises(ValueError):
            batch_requests(tasks(), strategy)


def test_run_batch_grades_and_names_the_run(tmp_path, paid):
    client = make_client(tmp_path, FakeBatches(fail_ids={"answer beta"}))
    results = run_batch(tasks(), Baseline(MODEL), client, PriceTable.load(), poll_s=0)

    assert [r.passed for r in results] == [True, False]
    assert results[1].error.startswith("BatchRequestFailed")
    assert {r.strategy for r in results} == {"baseline+batch"}


def test_worst_case_guard_refuses_before_sending(tmp_path, paid):
    batches = FakeBatches()
    client = make_client(tmp_path, batches)
    reqs = batch_requests(tasks(), Baseline(MODEL))
    bound = worst_case_cost(reqs, PriceTable.load())
    assert bound > 0
    with pytest.raises(BudgetExceeded):
        run_batch(tasks(), Baseline(MODEL), client, PriceTable.load(), max_cost=bound / 2, poll_s=0)
    assert batches.created == []


def test_store_keeps_the_batch_flag(tmp_path, paid):
    client = make_client(tmp_path, FakeBatches())
    results = run_batch(tasks(), Baseline(MODEL), client, PriceTable.load(), poll_s=0)
    with ResultStore(tmp_path / "r.sqlite") as store:
        run_id = store.save_run(
            workload="qa", strategy="baseline+batch", model=MODEL, tasks_hash="h", results=results
        )
        loaded = store.load_results(run_id)
    prices = PriceTable.load()
    assert loaded[0].calls[0].batch is True
    assert loaded[0].cost(prices) == pytest.approx(results[0].cost(prices))


def test_cli_rejects_batch_for_cascade(tmp_path, capsys):
    tasks_file = tmp_path / "t.jsonl"
    tasks_file.write_text(
        '{"id": "a", "workload": "qa", "input": "q", "expected": "x", '
        '"grader": "normalized_text"}\n',
        encoding="utf-8",
    )
    code = main(
        [
            "run",
            "qa",
            "--model",
            MODEL,
            "--strategy",
            "cascade",
            "--batch",
            "--tasks",
            str(tasks_file),
            "--db",
            str(tmp_path / "r.sqlite"),
        ]
    )
    assert code == 2
    assert "cannot run as one batch" in capsys.readouterr().err


# ---- recovering a batch whose run was interrupted ----


class ListingBatches(FakeBatches):
    def list(self, limit):
        return iter(
            [
                SimpleNamespace(
                    id="batch_1",
                    processing_status="ended",
                    created_at="2026-11-01",
                    request_counts=SimpleNamespace(succeeded=2, processing=0, errored=0),
                )
            ]
        )


def test_recent_batches_lists_without_spending(tmp_path):
    client = make_client(tmp_path, ListingBatches())
    assert client.recent_batches() == [
        {
            "id": "batch_1",
            "status": "ended",
            "created_at": "2026-11-01",
            "succeeded": 2,
            "processing": 0,
            "errored": 0,
        }
    ]


def test_import_batch_caches_results_so_a_rerun_is_free(tmp_path):
    reqs = [request("say alpha"), request("say beta")]
    batches = FakeBatches(polls_before_end=0)
    client = make_client(tmp_path, batches)
    # Simulate the interrupted run: the batch was created, but nobody collected it.
    keys = [client.cache.key({**r, "_batch": True}) for r in reqs]
    batches.create([{"custom_id": k, "params": r} for k, r in zip(keys, reqs, strict=True)])

    assert client.import_batch("batch_1", reqs) == 2

    replay = make_client(tmp_path, FakeBatches(), mode="replay")
    out = replay.call_batch(reqs, poll_s=0)
    assert [r.text for r in out] == ["alpha", "beta"] and all(r.batch for r in out)


def test_import_batch_refuses_an_unfinished_batch(tmp_path):
    client = make_client(tmp_path, FakeBatches(polls_before_end=5))
    with pytest.raises(RuntimeError):
        client.import_batch("batch_1", [request("x")])


# ---- repeat tag (quality gate 4) ----


def test_repeat_tag_makes_fresh_calls_without_touching_untagged_answers(tmp_path, paid):
    plain = make_client(tmp_path, FakeBatches())
    tagged = ModelClient(
        ResponseCache(tmp_path / "cache"),
        PriceTable.load(),
        mode="record",
        sdk_client=plain._sdk,
        cache_tag="repeat1",
    )
    plain.call(MODEL, request("say alpha")["messages"], max_tokens=64)
    assert plain._sdk.single_calls == 1

    tagged.call(MODEL, request("say alpha")["messages"], max_tokens=64)
    assert plain._sdk.single_calls == 2  # tagged run did not reuse the untagged answer

    # Both answers stay recorded: each replays under its own tag, with no new calls.
    plain.call(MODEL, request("say alpha")["messages"], max_tokens=64)
    tagged.call(MODEL, request("say alpha")["messages"], max_tokens=64)
    assert plain._sdk.single_calls == 2


def test_untagged_key_is_unchanged():
    # Existing recorded answers must stay valid: no tag means the old key exactly.
    cache = ResponseCache()
    client = ModelClient(cache, PriceTable.load(), mode="replay")
    req = {"model": MODEL, "messages": [{"role": "user", "content": "x"}], "max_tokens": 64}
    assert client._key(req) == cache.key(req)


def test_cli_saves_tagged_runs_as_a_separate_row(tmp_path, monkeypatch):
    from tests.test_strategies import CapturingClient

    seen = {}

    def fake_client(*a, **k):
        seen.update(k)
        return CapturingClient(lambda m, p: "x")

    monkeypatch.setattr("costlab.cli.ModelClient", fake_client)
    tasks_file = tmp_path / "t.jsonl"
    tasks_file.write_text(
        '{"id": "a", "workload": "qa", "input": "q", "expected": "x", '
        '"grader": "normalized_text"}\n',
        encoding="utf-8",
    )
    db = tmp_path / "r.sqlite"
    args = ["run", "qa", "--model", MODEL, "--tasks", str(tasks_file), "--db", str(db)]
    assert main([*args, "--repeat-tag", "repeat1"]) == 0
    assert seen["cache_tag"] == "repeat1"
    with ResultStore(db) as store:
        assert [r["strategy"] for r in store.latest_runs()] == ["baseline@repeat1"]
