"""Phase 3 step 1: prompt caching.

The task prompt is split at a marker into a stable prefix (instructions and documents) and the
part that changes per task (the question or document). The prefix goes in its own content block
with `cache_control`, so later tasks read it from Anthropic's cache at 0.1x the input price
(the first write costs 1.25x). The text the model sees is unchanged.

Prefixes under the model's minimum (512 tokens on Claude Haiku 5.5) silently do not cache: no
error and no write cost, just `cache_creation_input_tokens == 0`. That is the expected result
on the extraction and codefix workloads, whose shared headers are short.
"""

from __future__ import annotations

from dataclasses import dataclass

from costlab.models import Result, Task
from costlab.runner import single_call

# Where the per-task part starts, per workload prompt format. The first marker found wins.
MARKERS = (
    "\n\nQuestion: ",  # qa: instructions + documents | question
    "\nInvoice:\n",  # extraction (invoice): instructions | invoice
    "\nEmail:\n",  # extraction (email): instructions | email
    "\n\nTests:\n",  # codefix: instructions | tests + buggy code
)


def split_prefix(text: str, markers: tuple[str, ...] = MARKERS) -> tuple[str, str] | None:
    """(stable prefix, per-task rest), or None if no marker is found."""
    for marker in markers:
        idx = text.find(marker)
        if idx > 0:
            return text[:idx], text[idx:]
    return None


def cached_content(text: str, markers: tuple[str, ...] = MARKERS):
    """User message content with a cache breakpoint after the stable prefix."""
    parts = split_prefix(text, markers)
    if parts is None:
        return text
    prefix, rest = parts
    return [
        {"type": "text", "text": prefix, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": rest},
    ]


@dataclass(frozen=True)
class PromptCaching:
    model: str
    max_tokens: int = 1024
    name: str = "prompt-caching"

    def build(self, task: Task) -> tuple[str, object, dict]:
        return self.model, cached_content(task.input), {}

    def run(self, task: Task, client) -> Result:
        model, content, options = self.build(task)
        return single_call(
            task, client, self.name, model, content, max_tokens=self.max_tokens, **options
        )
