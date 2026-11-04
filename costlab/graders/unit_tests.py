"""unit_tests grader: the model's corrected code must pass the task's tests.

The reply's last ```python block is taken as the corrected code. It is written to a temp file
together with the tests and run in a fresh interpreter (`python -I`, so the current directory and
user site-packages are not on the path) with a timeout. Exit code 0 means pass.

This is a timeout and a separate process, not a security sandbox. Tasks are ours and the model
is one we pay for; do not point this grader at untrusted code.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

_BLOCK = re.compile(r"```python[ \t]*\n(.*?)```", re.DOTALL)


def extract_code(output: str) -> str | None:
    blocks = _BLOCK.findall(output)
    return blocks[-1] if blocks else None


def grade(output: str, expected_tests: str, timeout: float = 10.0) -> bool:
    """True when the corrected code in `output` passes `expected_tests` in a clean process."""
    code = extract_code(output)
    if code is None:
        return False
    source = code + "\n\n" + expected_tests + "\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "candidate.py"
        path.write_text(source, encoding="utf-8")
        try:
            done = subprocess.run(
                [sys.executable, "-I", str(path)],
                cwd=tmp,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return False
    return done.returncode == 0
