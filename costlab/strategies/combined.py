"""Phase 3 step 7: combined strategy.

Chosen from the Phase 3 full runs (2026-11-01, Claude Haiku 5.5):
- prompt caching: -81% cost on qa, quality held; no effect where the shared prefix is under
  the 512-token minimum (extraction, codefix).
- low effort: -14% extraction, -20% codefix, -4% qa, quality held.
- trim-context is left out: a trimmed qa prompt drops under the caching minimum, so it would
  cancel caching, which saves more (-81% vs -46%).
- cascade is left out: +151% cost on qa for +2 points, and no effect elsewhere.

It makes one call per task, so it can also run as a batch (`--batch`) for a further 50% off.
"""

from __future__ import annotations

from dataclasses import dataclass

from costlab.models import Result, Task
from costlab.runner import single_call
from costlab.strategies.caching import cached_content


@dataclass(frozen=True)
class Combined:
    model: str
    effort: str = "low"
    max_tokens: int = 1024
    name: str = "caching+low-effort"

    def build(self, task: Task) -> tuple[str, object, dict]:
        return self.model, cached_content(task.input), {"output_config": {"effort": self.effort}}

    def run(self, task: Task, client) -> Result:
        model, content, options = self.build(task)
        return single_call(
            task, client, self.name, model, content, max_tokens=self.max_tokens, **options
        )
