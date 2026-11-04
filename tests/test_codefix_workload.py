import re
from pathlib import Path

import pytest

from costlab.graders import grade_unit_tests
from costlab.graders.unit_tests import extract_code
from costlab.models import load_tasks

TASKS = Path(__file__).resolve().parent.parent / "workloads" / "codefix" / "tasks.jsonl"
TASK_LIST = load_tasks(TASKS)


def buggy_code(task):
    # The buggy function sits in the prompt after "Buggy code:".
    block = task.input.split("Buggy code:", 1)[1]
    return re.search(r"```python\n(.*?)```", block, re.DOTALL).group(1)


def test_workload_shape():
    assert len(TASK_LIST) == 30
    assert {t.grader for t in TASK_LIST} == {"unit_tests"}


@pytest.mark.parametrize("task", TASK_LIST, ids=lambda t: t.id)
def test_reference_fix_passes(task):
    # Gate 2: a correct answer must pass.
    reply = "```python\n" + task.meta["reference_fix"] + "```"
    assert grade_unit_tests(reply, task.expected) is True


@pytest.mark.parametrize("task", TASK_LIST, ids=lambda t: t.id)
def test_buggy_code_fails(task):
    # Gate 2: the unfixed code must fail.
    reply = "```python\n" + buggy_code(task) + "```"
    assert grade_unit_tests(reply, task.expected) is False


def test_no_code_block_fails():
    assert grade_unit_tests("Sorry, I cannot help.", "assert True") is False


def test_timeout_fails():
    reply = "```python\nwhile True:\n    pass\n```"
    assert grade_unit_tests(reply, "assert True", timeout=1.0) is False


def test_extract_uses_last_block():
    reply = "```python\nx = 1\n```\nBetter:\n```python\nx = 2\n```"
    assert extract_code(reply) == "x = 2\n"
