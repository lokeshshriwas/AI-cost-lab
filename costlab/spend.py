"""What was actually paid, from the response cache (quality gate 5).

Every file in cache/ is one real API answer, paid for exactly once: replays never write a new
file. That includes batch answers recovered with `import_batch`, which the results database
shows as replayed. So totalling the cache by day gives the bill to check against the Console's
Cost page, independent of how runs were stitched together.

Not counted: failed requests (no answer is stored; the API does not bill them) and anything
sent outside ModelClient (only `phase0/exit_check.py`).
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from costlab.cache import DEFAULT_CACHE_DIR
from costlab.pricing import PriceTable, Usage


@dataclass(frozen=True)
class SpendLine:
    day: str  # UTC date, YYYY-MM-DD
    model: str
    batch: bool
    calls: int
    cost_usd: float


def _day(entry: dict, path: Path) -> str:
    stamp = entry.get("recorded_at")
    if stamp:
        return stamp[:10]
    # Entries cached before recorded_at existed: the file's modified time, in UTC. Accurate in
    # the checkout that made the calls; a fresh clone resets it, so the day is then unreliable.
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).date().isoformat()


def ledger(
    prices: PriceTable, cache_root: Path | str = DEFAULT_CACHE_DIR, since: str | None = None
) -> list[SpendLine]:
    totals: dict[tuple[str, str, bool], list[float]] = defaultdict(lambda: [0, 0.0])
    for path in Path(cache_root).glob("*/*.json"):
        entry = json.loads(path.read_text(encoding="utf-8"))
        day = _day(entry, path)
        if since is not None and day < since:
            continue
        batch = bool(entry.get("batch", False))
        cost = prices.cost(entry["model"], Usage(**entry["usage"]), batch=batch)
        line = totals[(day, entry["model"], batch)]
        line[0] += 1
        line[1] += cost
    return [
        SpendLine(day, model, batch, int(calls), cost)
        for (day, model, batch), (calls, cost) in sorted(totals.items())
    ]


def format_ledger(lines: list[SpendLine]) -> str:
    out = [
        "| Day (UTC) | Model | Batch | Calls | Cost (USD) |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for line in lines:
        out.append(
            f"| {line.day} | {line.model} | {'yes' if line.batch else 'no'} "
            f"| {line.calls} | {line.cost_usd:.6f} |"
        )
    by_day: dict[str, float] = defaultdict(float)
    for line in lines:
        by_day[line.day] += line.cost_usd
    out.append("")
    for day, cost in sorted(by_day.items()):
        out.append(f"{day}: ${cost:.6f}")
    out.append(f"Total: ${sum(by_day.values()):.6f} over {sum(x.calls for x in lines)} calls")
    return "\n".join(out)
