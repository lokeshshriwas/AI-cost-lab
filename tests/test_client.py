from types import SimpleNamespace

import pytest

from costlab import CacheMiss, ModelClient, PaidCallNotAllowed, PriceTable, ResponseCache

MESSAGES = [{"role": "user", "content": "Say hi"}]


class FakeSDK:
    """Stands in for anthropic.Anthropic(); counts how often the 'API' is hit."""

    def __init__(self):
        self.calls = 0
        self.messages = self

    def create(self, **request):
        self.calls += 1
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="hi")],
            stop_reason="end_turn",
            usage=SimpleNamespace(
                input_tokens=1_000,
                output_tokens=500,
                cache_creation_input_tokens=None,
                cache_read_input_tokens=None,
            ),
        )


@pytest.fixture
def fake():
    return FakeSDK()


def make_client(tmp_path, fake, mode="record"):
    return ModelClient(ResponseCache(tmp_path), PriceTable.load(), mode=mode, sdk_client=fake)


def test_paid_call_blocked_without_flag(tmp_path, fake, monkeypatch):
    monkeypatch.delenv("COSTLAB_ALLOW_PAID", raising=False)
    with pytest.raises(PaidCallNotAllowed):
        make_client(tmp_path, fake).call("claude-haiku-5-5", MESSAGES)
    assert fake.calls == 0


def test_replay_mode_never_calls_the_api(tmp_path, fake, monkeypatch):
    monkeypatch.setenv("COSTLAB_ALLOW_PAID", "1")
    with pytest.raises(CacheMiss):
        make_client(tmp_path, fake, mode="replay").call("claude-haiku-5-5", MESSAGES)
    assert fake.calls == 0


def test_second_identical_call_is_served_from_cache(tmp_path, fake, monkeypatch):
    monkeypatch.setenv("COSTLAB_ALLOW_PAID", "1")
    client = make_client(tmp_path, fake)

    first = client.call("claude-haiku-5-5", MESSAGES)
    second = client.call("claude-haiku-5-5", MESSAGES)

    assert fake.calls == 1
    assert (first.from_cache, second.from_cache) == (False, True)
    assert second.text == "hi"
    assert second.cost_usd == first.cost_usd == pytest.approx((1_000 * 0.10 + 500 * 0.50) / 1e6)


def test_recorded_response_replays_without_flag(tmp_path, fake, monkeypatch):
    monkeypatch.setenv("COSTLAB_ALLOW_PAID", "1")
    make_client(tmp_path, fake).call("claude-haiku-5-5", MESSAGES)

    monkeypatch.delenv("COSTLAB_ALLOW_PAID")
    replayed = make_client(tmp_path, fake, mode="replay").call("claude-haiku-5-5", MESSAGES)
    assert replayed.from_cache and fake.calls == 1


def test_different_options_are_different_cache_entries(tmp_path, fake, monkeypatch):
    monkeypatch.setenv("COSTLAB_ALLOW_PAID", "1")
    client = make_client(tmp_path, fake)
    client.call("claude-haiku-5-5", MESSAGES, output_config={"effort": "low"})
    client.call("claude-haiku-5-5", MESSAGES, output_config={"effort": "high"})
    assert fake.calls == 2
