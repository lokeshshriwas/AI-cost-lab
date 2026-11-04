import json
from pathlib import Path

from costlab.graders import grade_exact_json
from costlab.models import load_tasks

TASKS = Path(__file__).resolve().parent.parent / "workloads" / "extraction" / "tasks.jsonl"

INVOICE_KEYS = {
    "type",
    "invoice_number",
    "vendor",
    "issue_date",
    "due_date",
    "currency",
    "subtotal",
    "tax",
    "total",
}
EMAIL_KEYS = {"type", "sender", "subject", "request", "deadline", "urgent"}


def test_workload_shape():
    tasks = load_tasks(TASKS)
    assert len(tasks) == 50
    assert len({t.id for t in tasks}) == 50
    assert {t.workload for t in tasks} == {"extraction"}
    assert {t.grader for t in tasks} == {"exact_json"}
    assert sum(t.meta["kind"] == "invoice" for t in tasks) == 30
    assert sum(t.meta["kind"] == "email" for t in tasks) == 20


def test_expected_keys_match_kind():
    for t in load_tasks(TASKS):
        want = INVOICE_KEYS if t.meta["kind"] == "invoice" else EMAIL_KEYS
        assert set(t.expected) == want, t.id


def test_invoice_amounts_add_up():
    for t in load_tasks(TASKS):
        if t.meta["kind"] == "invoice":
            e = t.expected
            assert abs(e["subtotal"] + e["tax"] - e["total"]) < 0.005, t.id


def test_expected_answers_pass_their_own_grader():
    for t in load_tasks(TASKS):
        assert grade_exact_json(json.dumps(t.expected), t.expected), t.id
