import json
from types import SimpleNamespace

import pytest

from costlab import CacheMiss, ModelClient, PriceTable, ResponseCache
from costlab.cli import main
from costlab.estimate import approx_tokens, estimate, format_estimates
from costlab.spend import ledger


@pytest.fixture
def prices():
    return PriceTable.load()


class CountingSDK:
    """Stands in for anthropic.Anthropic(): count_tokens only, counting how often it is hit."""

    def __init__(self, tokens=1_000):
        self.tokens = tokens
        self.calls = 0
        self.messages = self

    def count_tokens(self, **request):
        self.calls += 1
        return SimpleNamespace(input_tokens=self.tokens)

    def create(self, **request):
        raise AssertionError("estimate must never send a billed request")


# ---- estimate ----


def test_exact_counts_price_each_model_and_sort_cheapest_first(prices):
    results = estimate(
        "hi", ["claude-opus-5-5", "claude-haiku-5-5"], prices, 500, lambda m, t: 1_000
    )
    assert [e.model for e in results] == ["claude-haiku-5-5", "claude-opus-5-5"]
    haiku = results[0]
    assert haiku.exact and haiku.input_tokens == 1_000 and haiku.output_tokens == 500
    assert haiku.cost_usd == pytest.approx((1_000 * 0.10 + 500 * 0.50) / 1e6)
    assert haiku.batch_cost_usd == pytest.approx(haiku.cost_usd * 0.5)


def test_offline_approximation_is_labeled(prices):
    (e,) = estimate("x" * 401, ["claude-haiku-5-5"], prices, 0)
    assert e.input_tokens == approx_tokens("x" * 401) == 161
    assert not e.exact
    text = format_estimates([e])
    assert "161 ~" in text and "approximated offline" in text


def test_long_haiku_prompt_uses_the_long_context_rate(prices):
    (e,) = estimate("p", ["claude-haiku-5-5"], prices, 0, lambda m, t: 150_000)
    assert e.cost_usd == pytest.approx(150_000 * 0.50 / 1e6)


# ---- ModelClient.count_tokens ----


def test_count_tokens_is_free_and_cached(tmp_path, monkeypatch):
    monkeypatch.delenv("COSTLAB_ALLOW_PAID", raising=False)  # free: no paid flag needed
    sdk = CountingSDK(1_234)
    client = ModelClient(ResponseCache(tmp_path), PriceTable.load(), sdk_client=sdk)
    messages = [{"role": "user", "content": "hello"}]
    assert client.count_tokens("claude-haiku-5-5", messages) == 1_234
    assert client.count_tokens("claude-haiku-5-5", messages) == 1_234
    assert sdk.calls == 1


def test_count_tokens_replay_mode_never_calls(tmp_path):
    sdk = CountingSDK()
    client = ModelClient(ResponseCache(tmp_path), PriceTable.load(), mode="replay", sdk_client=sdk)
    with pytest.raises(CacheMiss):
        client.count_tokens("claude-haiku-5-5", [{"role": "user", "content": "x"}])
    assert sdk.calls == 0


def test_cached_counts_are_not_counted_as_spend(tmp_path, prices):
    client = ModelClient(ResponseCache(tmp_path), prices, sdk_client=CountingSDK())
    client.count_tokens("claude-haiku-5-5", [{"role": "user", "content": "x"}])
    assert ledger(prices, tmp_path) == []


# ---- CLI ----


def test_cli_estimate_offline_json(tmp_path, capsys):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("y" * 4_000, encoding="utf-8")
    code = main(["estimate", str(prompt), "--offline", "--json", "--model", "claude-haiku-5-5"])
    assert code == 0
    (row,) = json.loads(capsys.readouterr().out)
    assert row["model"] == "claude-haiku-5-5"
    assert row["input_tokens"] == 1_600 and row["output_tokens"] == 500
    assert row["exact"] is False


def test_cli_estimate_unknown_model(tmp_path, capsys):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("hi", encoding="utf-8")
    assert main(["estimate", str(prompt), "--offline", "--model", "made-up"]) == 2
    assert "prices.yaml" in capsys.readouterr().err


def test_cli_estimate_without_api_suggests_offline(tmp_path, capsys, monkeypatch):
    class Broken:
        def __init__(self, *a, **k):
            pass

        def count_tokens(self, *a, **k):
            raise ConnectionError("no network")

    monkeypatch.setattr("costlab.cli.ModelClient", Broken)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("hi", encoding="utf-8")
    assert main(["estimate", str(prompt)]) == 2
    assert "--offline" in capsys.readouterr().err
