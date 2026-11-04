"""Phase 3 step 3: output limits.

Claude Haiku 5.5 thinks by default (adaptive thinking, effort `medium`), and thinking tokens are
billed as output. Lowering effort to `low` cuts that spend. `max_tokens` stays the same: it is
a hard cap the model cannot see, so lowering it only truncates answers.
"""

from __future__ import annotations

from dataclasses import dataclass

from costlab.models import Result, Task
from costlab.runner import single_call


@dataclass(frozen=True)
class LowEffort:
    model: str
    effort: str = "low"
    max_tokens: int = 1024
    name: str = "low-effort"

    def build(self, task: Task) -> tuple[str, object, dict]:
        return self.model, task.input, {"output_config": {"effort": self.effort}}

    def run(self, task: Task, client) -> Result:
        model, content, options = self.build(task)
        return single_call(
            task, client, self.name, model, content, max_tokens=self.max_tokens, **options
        )
