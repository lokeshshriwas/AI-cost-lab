"""Phase 3 step 2: context trimming (retrieval).

For document Q&A, send only the document that matches the question instead of every document.
Matching is plain word overlap between the question and each document, with no model call.
If no single document wins clearly, all documents are kept, so a weak match never drops the
needed one. Prompts that are not in the multi-document Q&A format are sent unchanged.

Trade-off to measure: fewer input tokens, against the risk of sending the wrong document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from costlab.models import Result, Task
from costlab.runner import single_call

_DOC_HEADER = re.compile(r"Document \d+ \(([^)]*)\):\n\n")
_QUESTION = "\n\nQuestion: "
_WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_STOPWORDS = frozenset(
    "the a an is are was be do does did can could what which who whom when where why how "
    "this that these those of in on at to for from by with and or not no yes it its many much "
    "after before into than any all some must there their our your we you they".split()
)


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2 and w not in _STOPWORDS}


def parse_qa_prompt(text: str):
    """(instruction, [(label, document)], question), or None if the format does not match."""
    if _QUESTION not in text:
        return None
    body, question = text.rsplit(_QUESTION, 1)
    pieces = _DOC_HEADER.split(body)
    # split() gives [instruction, label1, doc1, label2, doc2, ...]
    if len(pieces) < 5:
        return None  # fewer than two documents: nothing to trim
    instruction = pieces[0]
    docs = [(pieces[i], pieces[i + 1].strip()) for i in range(1, len(pieces) - 1, 2)]
    return instruction, docs, question


def trim_prompt(text: str) -> str:
    parsed = parse_qa_prompt(text)
    if parsed is None:
        return text
    instruction, docs, question = parsed
    q = _words(question)
    scores = [len(q & _words(label + " " + doc)) for label, doc in docs]
    best = max(scores)
    if best == 0 or scores.count(best) > 1:
        return text  # no clear winner: keep every document
    label, doc = docs[scores.index(best)]
    return f"{instruction}Document ({label}):\n\n{doc}{_QUESTION}{question}"


@dataclass(frozen=True)
class TrimContext:
    model: str
    max_tokens: int = 1024
    name: str = "trim-context"

    def build(self, task: Task) -> tuple[str, object, dict]:
        return self.model, trim_prompt(task.input), {}

    def run(self, task: Task, client) -> Result:
        model, content, options = self.build(task)
        return single_call(
            task, client, self.name, model, content, max_tokens=self.max_tokens, **options
        )
