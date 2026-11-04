from pathlib import Path

from costlab.graders import grade_normalized_text
from costlab.models import load_tasks

ROOT = Path(__file__).resolve().parent.parent / "workloads" / "qa"
TASKS = load_tasks(ROOT / "tasks.jsonl")


def test_workload_shape():
    assert len(TASKS) == 50
    assert len({t.id for t in TASKS}) == 50
    assert {t.grader for t in TASKS} == {"normalized_text"}
    assert sum(t.meta["doc"] == "returns_policy" for t in TASKS) == 25
    assert sum(t.meta["doc"] == "product_sheet" for t in TASKS) == 25


def test_documents_are_in_every_prompt():
    for name in ("returns_policy", "product_sheet"):
        text = (ROOT / "docs" / f"{name}.md").read_text(encoding="utf-8").strip()
        assert all(text in t.input for t in TASKS), name


def test_reference_answers_pass_their_own_grader():
    # Gate 2: every accepted answer passes.
    for t in TASKS:
        accepted = [t.expected] if isinstance(t.expected, str) else t.expected
        for answer in accepted:
            assert grade_normalized_text(answer, t.expected) is True, (t.id, answer)
