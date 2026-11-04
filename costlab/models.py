"""Tasks, results and the summary numbers the report is built from."""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from costlab.client import CallResult
from costlab.pricing import PriceTable

GRADERS = ("exact_json", "normalized_text", "unit_tests")


class TaskFileError(ValueError):
    pass


@dataclass(frozen=True)
class Task:
    id: str
    workload: str
    input: str
    expected: Any
    grader: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    task_id: str
    workload: str
    strategy: str
    output: str
    passed: bool
    # Every model call made for this task. A cascade makes more than one.
    calls: list[CallResult] = field(default_factory=list)
    error: str | None = None

    def cost(self, prices: PriceTable) -> float:
        # Recomputed from tokens, so a price change never needs a re-run.
        return sum(prices.cost(c.model, c.usage, batch=c.batch) for c in self.calls)

    @property
    def latency_s(self) -> float:
        return sum(c.latency_s for c in self.calls)


@dataclass(frozen=True)
class Summary:
    tasks: int
    passed: int
    total_cost_usd: float
    median_latency_s: float

    @property
    def pass_rate(self) -> float:
        return self.passed / self.tasks if self.tasks else 0.0

    @property
    def cost_per_success_usd(self) -> float | None:
        # The headline metric. None when nothing passed: there is no fair number to show.
        return self.total_cost_usd / self.passed if self.passed else None


def summarize(results: list[Result], prices: PriceTable) -> Summary:
    return Summary(
        tasks=len(results),
        passed=sum(r.passed for r in results),
        total_cost_usd=sum(r.cost(prices) for r in results),
        median_latency_s=statistics.median(r.latency_s for r in results) if results else 0.0,
    )


def load_tasks(path: Path | str) -> list[Task]:
    """Read a workload's tasks.jsonl: one JSON object per line."""
    path = Path(path)
    tasks: list[Task] = []
    seen: set[str] = set()
    required = ("id", "workload", "input", "expected", "grader")

    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        where = f"{path.name}:{line_no}"
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise TaskFileError(f"{where}: invalid JSON ({e.msg})") from None

        missing = [k for k in required if k not in row]
        if missing:
            raise TaskFileError(f"{where}: missing {', '.join(missing)}")
        if row["grader"] not in GRADERS:
            raise TaskFileError(f"{where}: unknown grader {row['grader']!r}")
        if row["id"] in seen:
            raise TaskFileError(f"{where}: duplicate id {row['id']!r}")
        seen.add(row["id"])

        tasks.append(
            Task(
                id=row["id"],
                workload=row["workload"],
                input=row["input"],
                expected=row["expected"],
                grader=row["grader"],
                meta=row.get("meta", {}),
            )
        )

    if not tasks:
        raise TaskFileError(f"{path.name}: no tasks")
    return tasks


def tasks_hash(path: Path | str) -> str:
    """Fingerprint of a task file. Quality gate 1: baseline and strategy must share it."""
    # Normalize line endings so the hash matches on Windows and in CI.
    text = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
