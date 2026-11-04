import json

import pytest

from costlab.graders import grade_exact_json

EXPECTED = {
    "type": "invoice",
    "invoice_number": "INV-2041",
    "vendor": "Bluepeak Logistics Ltd",
    "issue_date": "2026-03-04",
    "due_date": None,
    "currency": "USD",
    "subtotal": 1200.0,
    "tax": 96.0,
    "total": 1296.0,
}


# Gate 2: the grader must pass every expected answer.
@pytest.mark.parametrize(
    "output",
    [
        json.dumps(EXPECTED),
        json.dumps(EXPECTED, indent=2),
        "```json\n" + json.dumps(EXPECTED, indent=2) + "\n```",
        "```\n" + json.dumps(EXPECTED) + "\n```",
        "  " + json.dumps(EXPECTED) + "\n",
    ],
)
def test_passes_expected_answers(output):
    assert grade_exact_json(output, EXPECTED) is True


def test_whitespace_inside_strings_is_collapsed():
    output = json.dumps({**EXPECTED, "vendor": "Bluepeak   Logistics\nLtd "})
    assert grade_exact_json(output, EXPECTED) is True


def test_numbers_compare_by_value():
    output = json.dumps({**EXPECTED, "total": 1296})
    assert grade_exact_json(output, EXPECTED) is True


# Gate 2: the grader must fail obviously wrong answers.
@pytest.mark.parametrize(
    "output",
    [
        "",
        "not json at all",
        "[]",
        '"just a string"',
        json.dumps({**EXPECTED, "total": 1269.0}),  # digits transposed
        json.dumps({**EXPECTED, "vendor": "Bluepeak logistics Ltd"}),  # case still counts
        json.dumps({**EXPECTED, "due_date": "2026-04-03"}),  # null must stay null
        json.dumps({**EXPECTED, "currency": None}),
        json.dumps({k: v for k, v in EXPECTED.items() if k != "tax"}),  # missing key
        json.dumps({**EXPECTED, "notes": "extra key"}),  # extra key
        json.dumps({**EXPECTED, "total": "1296.00 USD"}),  # wrong type
        json.dumps({"type": "email"}),
        "Here is the JSON: " + json.dumps(EXPECTED),  # prose around it is not forgiven
    ],
)
def test_fails_wrong_answers(output):
    assert grade_exact_json(output, EXPECTED) is False


def test_expected_object_with_null_is_matched_exactly():
    assert grade_exact_json(json.dumps({"a": None}), {"a": None}) is True
    assert grade_exact_json(json.dumps({"a": 0}), {"a": None}) is False
    assert grade_exact_json(json.dumps({"a": False}), {"a": 0}) is False
