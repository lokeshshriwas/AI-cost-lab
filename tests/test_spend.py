import json
import os

import pytest

from costlab import PriceTable
from costlab.cli import main
from costlab.spend import format_ledger, ledger


def put(root, name, model, tokens_in, tokens_out, day=None, batch=False, mtime=None):
    path = root / name[:2] / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "model": model,
        "text": "",
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        "latency_s": 1.0,
    }
    if day:
        entry["recorded_at"] = f"{day}T12:00:00+00:00"
    if batch:
        entry["batch"] = True
    path.write_text(json.dumps(entry), encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def prices():
    return PriceTable.load()


def test_every_cache_entry_is_one_paid_call(tmp_path, prices):
    put(tmp_path, "aa01", "claude-haiku-5-5", 100_000, 0, day="2026-11-01")
    put(tmp_path, "aa02", "claude-haiku-5-5", 100_000, 0, day="2026-11-01")
    put(tmp_path, "bb01", "claude-opus-5-5", 0, 1_000_000, day="2026-11-04")
    lines = ledger(prices, tmp_path)
    assert [(x.day, x.model, x.calls) for x in lines] == [
        ("2026-11-01", "claude-haiku-5-5", 2),
        ("2026-11-04", "claude-opus-5-5", 1),
    ]
    assert lines[0].cost_usd == pytest.approx(0.02)
    assert lines[1].cost_usd == pytest.approx(20.00)


def test_batch_answers_are_priced_at_the_batch_rate_on_their_own_line(tmp_path, prices):
    put(tmp_path, "aa01", "claude-sonnet-5-5", 1_000_000, 0, day="2026-11-01")
    put(tmp_path, "aa02", "claude-sonnet-5-5", 1_000_000, 0, day="2026-11-01", batch=True)
    normal, batch = ledger(prices, tmp_path)
    assert (normal.batch, batch.batch) == (False, True)
    assert batch.cost_usd == pytest.approx(normal.cost_usd * 0.5)


def test_old_entries_fall_back_to_file_time(tmp_path, prices):
    # 2026-11-02 12:00 UTC
    put(tmp_path, "aa01", "claude-haiku-5-5", 10, 10, mtime=1793620800)
    assert ledger(prices, tmp_path)[0].day == "2026-11-02"


def test_since_filters_by_day_and_totals_add_up(tmp_path, prices):
    put(tmp_path, "aa01", "claude-haiku-5-5", 100_000, 0, day="2026-10-31")
    put(tmp_path, "aa02", "claude-haiku-5-5", 100_000, 0, day="2026-11-01")
    lines = ledger(prices, tmp_path, since="2026-11-01")
    assert [x.day for x in lines] == ["2026-11-01"]
    text = format_ledger(lines)
    assert "2026-11-01: $0.010000" in text
    assert "Total: $0.010000 over 1 calls" in text


def test_cli_spend(tmp_path, capsys):
    put(tmp_path, "aa01", "claude-haiku-5-5", 100_000, 0, day="2026-11-01")
    assert main(["spend", "--cache", str(tmp_path)]) == 0
    assert "Total: $0.010000 over 1 calls" in capsys.readouterr().out
