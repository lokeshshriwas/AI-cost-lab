import pytest

from costlab.pricing import PriceTable, Usage


@pytest.fixture
def prices():
    return PriceTable.load()


def test_all_planned_models_have_prices(prices):
    assert {"claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"} <= set(prices.models())


def test_plain_input_and_output(prices):
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert prices.cost("claude-sonnet-5-5", usage) == pytest.approx(2.00 + 10.00)


def test_cache_tokens_use_their_own_rates(prices):
    usage = Usage(cache_creation_input_tokens=1_000_000, cache_read_input_tokens=1_000_000)
    assert prices.cost("claude-opus-5-5", usage) == pytest.approx(5.00 + 0.20)


def test_haiku_long_prompt_switches_every_rate(prices):
    short = Usage(input_tokens=100_000, output_tokens=1_000)
    long = Usage(input_tokens=100_001, output_tokens=1_000)
    assert prices.cost("claude-haiku-5-5", short) == pytest.approx(
        (100_000 * 0.10 + 1_000 * 0.50) / 1e6
    )
    assert prices.cost("claude-haiku-5-5", long) == pytest.approx(
        (100_001 * 0.50 + 1_000 * 2.50) / 1e6
    )


def test_long_prompt_counts_cached_tokens(prices):
    # 60K uncached + 50K read from cache = 110K prompt, over the 100K threshold.
    usage = Usage(input_tokens=60_000, cache_read_input_tokens=50_000)
    assert prices.cost("claude-haiku-5-5", usage) == pytest.approx(
        (60_000 * 0.50 + 50_000 * 0.05) / 1e6
    )


def test_unknown_model_is_a_clear_error(prices):
    with pytest.raises(KeyError, match="prices.yaml"):
        prices.cost("claude-made-up", Usage(input_tokens=1))
