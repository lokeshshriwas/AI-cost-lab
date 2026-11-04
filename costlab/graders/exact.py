"""exact_json grader: the model's reply must be a JSON object equal to the expected one.

Rules (kept deliberately strict so a grader pass means something):
- The reply must parse as JSON, and the top level must be an object.
- Every expected key must be present, and no extra keys are allowed.
- Strings must match after trimming and collapsing runs of whitespace. Nothing else is changed:
  case and punctuation still count.
- Numbers compare by value (1200 == 1200.0). Booleans and null compare exactly.
- Code fences (```json ... ```) around the reply are stripped; nothing else is forgiven.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def _strip_fence(text: str) -> str:
    match = _FENCE.match(text)
    return match.group(1) if match else text


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, bool):
        # Python has False == 0 and True == 1; tag booleans so they never match numbers.
        return ("bool", value)
    if value is None:
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    return value


def grade(output: str, expected: Any) -> bool:
    """Return True when `output` is the expected JSON object, under the rules above."""
    try:
        parsed = json.loads(_strip_fence(output))
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(parsed, dict):
        return False
    return _normalize(parsed) == _normalize(expected)
