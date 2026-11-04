"""Phase 3 step 5: application response cache.

If a prompt was already answered in this run, reuse that answer instead of calling the model.
Prompts are compared after collapsing whitespace, so trivially reformatted repeats also hit.
A hit costs nothing and makes no call; it is still graded against its own task.

This is different from the record/replay cache in `costlab/cache.py`, which exists so the
benchmark can be re-run for free. This strategy models what a production app saves when real
users repeat requests. Savings depend entirely on how often traffic repeats: the benchmark's
tasks are all distinct, so the expected saving here is 0%, and the report says why.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from costlab.models import Result, Task
from costlab.runner import Baseline, grade


def prompt_key(model: str, prompt: str) -> str:
    normalized = " ".join(prompt.split())
    return hashlib.sha256(f"{model}\n{normalized}".encode()).hexdigest()


@dataclass
class ResponseCacheStrategy:
    model: str
    max_tokens: int = 1024
    name: str = "response-cache"
    hits: int = 0
    _seen: dict[str, str] = field(default_factory=dict, repr=False)

    def run(self, task: Task, client) -> Result:
        key = prompt_key(self.model, task.input)
        if key in self._seen:
            self.hits += 1
            output = self._seen[key]
            return Result(task.id, task.workload, self.name, output, grade(task, output), [])
        # A miss is exactly a baseline call, so recorded baseline replies replay for free.
        result = Baseline(self.model, self.max_tokens, name=self.name).run(task, client)
        if result.error is None:
            self._seen[key] = result.output
        return result
