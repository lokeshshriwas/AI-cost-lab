"""Phase 3 step 4: model cascade.

Ask the cheap model first. If a validator rejects its reply, ask the strong model and use that
reply instead. Cost counts both calls.

The validator never sees the expected answer; it only uses what is in the prompt:
- exact_json: the reply must be a JSON object with exactly the keys the prompt lists.
- normalized_text: the reply must look like a short answer (at most 4 words, not a sentence).
- unit_tests: the code must pass the tests shown in the prompt.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from costlab.graders.exact import _strip_fence
from costlab.graders.unit_tests import grade as run_tests
from costlab.models import Result, Task
from costlab.runner import single_call

_KEYS = re.compile(r"Use exactly these keys: ([^\n]+?)\.\n")
_TESTS = re.compile(r"Tests:\n```python\n(.*?)```", re.DOTALL)


def looks_valid(task: Task, output: str) -> bool:
    if not output.strip():
        return False
    if task.grader == "exact_json":
        try:
            parsed = json.loads(_strip_fence(output))
        except json.JSONDecodeError:
            return False
        match = _KEYS.search(task.input)
        if not isinstance(parsed, dict) or match is None:
            return False
        wanted = {k.strip() for k in match.group(1).split(",")}
        return set(parsed) == wanted
    if task.grader == "normalized_text":
        answer = output.strip()
        return len(answer.split()) <= 4 and not answer.endswith(".") and "(" not in answer
    if task.grader == "unit_tests":
        match = _TESTS.search(task.input)
        return match is not None and run_tests(output, match.group(1))
    return True


@dataclass(frozen=True)
class Cascade:
    model: str  # the cheap model, tried first
    strong_model: str = "claude-sonnet-5-5"
    max_tokens: int = 1024
    name: str = "cascade"

    def run(self, task: Task, client) -> Result:
        first = single_call(
            task, client, self.name, self.model, task.input, max_tokens=self.max_tokens
        )
        if first.error is None and looks_valid(task, first.output):
            return first
        second = single_call(
            task, client, self.name, self.strong_model, task.input, max_tokens=self.max_tokens
        )
        return Result(
            task.id,
            task.workload,
            self.name,
            second.output,
            second.passed,
            first.calls + second.calls,
            second.error,
        )
