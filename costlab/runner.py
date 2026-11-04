"""Run a strategy over a workload's tasks and grade every reply.

Only the baseline strategy lives here; later optimizations (Phase 3) implement the same
`run(task, client) -> Result` interface.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from costlab.client import CacheMiss, PaidCallNotAllowed
from costlab.graders import grade_exact_json, grade_normalized_text, grade_unit_tests
from costlab.models import Result, Task
from costlab.pricing import PriceTable, Usage


class BudgetExceeded(RuntimeError):
    pass


GRADERS: dict[str, Callable[[str, object], bool]] = {
    "exact_json": grade_exact_json,
    "normalized_text": grade_normalized_text,
    "unit_tests": grade_unit_tests,
}


def grade(task: Task, output: str) -> bool:
    return GRADERS[task.grader](output, task.expected)


class Strategy(Protocol):
    name: str

    def run(self, task: Task, client) -> Result: ...


def single_call(
    task: Task,
    client,
    strategy_name: str,
    model: str,
    content,
    *,
    max_tokens: int,
    **options,
) -> Result:
    """One model call for one task, graded. Shared by every one-call strategy.

    `content` is the user message content: a string, or a list of content blocks.
    """
    try:
        call = client.call(
            model,
            [{"role": "user", "content": content}],
            max_tokens=max_tokens,
            **options,
        )
    except (CacheMiss, PaidCallNotAllowed):
        # Not a task failure: the run cannot continue, so stop loudly.
        raise
    except Exception as e:  # API errors are recorded against the task, not hidden.
        return Result(
            task.id, task.workload, strategy_name, "", False, [], error=f"{type(e).__name__}: {e}"
        )
    return Result(task.id, task.workload, strategy_name, call.text, grade(task, call.text), [call])


@dataclass(frozen=True)
class Baseline:
    """Send the task as-is to one model with no optimization."""

    model: str
    max_tokens: int = 1024
    name: str = "baseline"

    def build(self, task: Task) -> tuple[str, object, dict]:
        # Must stay byte-identical to the recorded baseline requests, or replays miss.
        return self.model, task.input, {}

    def run(self, task: Task, client) -> Result:
        model, content, options = self.build(task)
        return single_call(
            task, client, self.name, model, content, max_tokens=self.max_tokens, **options
        )


def batch_requests(tasks: list[Task], strategy) -> list[dict]:
    """The Messages requests a single-call strategy would send, one per task."""
    if not hasattr(strategy, "build"):
        raise ValueError(
            f"strategy {strategy.name!r} does not make exactly one call per task, "
            "so it cannot run as one batch"
        )
    requests = []
    for task in tasks:
        model, content, options = strategy.build(task)
        requests.append(
            {
                "model": model,
                "messages": [{"role": "user", "content": content}],
                "max_tokens": strategy.max_tokens,
                **options,
            }
        )
    return requests


def worst_case_cost(requests: list[dict], prices: PriceTable, batch: bool = True) -> float:
    """A deliberately high cost bound, for refusing a batch before it is sent.

    A batch cannot be stopped halfway, so --max-cost is checked against this bound instead of
    against spend. Assumes one token per 2 characters of prompt (real text is nearer 4) and that
    every request uses its full max_tokens of output.
    """
    total = 0.0
    for r in requests:
        prompt_chars = len(json.dumps(r["messages"], ensure_ascii=False))
        usage = Usage(input_tokens=prompt_chars // 2 + 1, output_tokens=r["max_tokens"])
        total += prices.cost(r["model"], usage, batch=batch)
    return total


def run_batch(
    tasks: list[Task],
    strategy,
    client,
    prices: PriceTable,
    max_cost: float | None = None,
    poll_s: float = 30.0,
) -> list[Result]:
    """Run a single-call strategy as one Message Batches request (50% price, slower)."""
    requests = batch_requests(tasks, strategy)
    bound = worst_case_cost(requests, prices)
    if max_cost is not None and bound > max_cost:
        raise BudgetExceeded(
            f"worst-case batch cost ${bound:.4f} is over --max-cost ${max_cost:.2f}; "
            "nothing was sent"
        )
    name = f"{strategy.name}+batch"
    results = []
    for task, item in zip(tasks, client.call_batch(requests, poll_s=poll_s), strict=True):
        if isinstance(item, Exception):
            results.append(
                Result(
                    task.id,
                    task.workload,
                    name,
                    "",
                    False,
                    [],
                    error=f"{type(item).__name__}: {item}",
                )
            )
        else:
            results.append(
                Result(task.id, task.workload, name, item.text, grade(task, item.text), [item])
            )
    return results


def run_strategy(
    tasks: list[Task],
    strategy: Strategy,
    client,
    prices: PriceTable,
    max_cost: float | None = None,
) -> list[Result]:
    """Run every task in order. Stops with BudgetExceeded once spend passes `max_cost`."""
    results: list[Result] = []
    spent = 0.0
    for task in tasks:
        if max_cost is not None and spent >= max_cost:
            raise BudgetExceeded(
                f"spent ${spent:.4f} after {len(results)} of {len(tasks)} tasks; "
                f"--max-cost is ${max_cost:.2f}"
            )
        result = strategy.run(task, client)
        spent += result.cost(prices)
        results.append(result)
    return results
