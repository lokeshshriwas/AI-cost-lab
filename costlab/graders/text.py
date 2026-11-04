"""normalized_text grader: a short answer passes if it equals an accepted answer after normalizing.

Normalizing: lowercase, turn punctuation and symbols into spaces, and collapse runs of whitespace.
So "15%" == "15", "9:00" == "9 00", and "9.2 kg" == "9 2 kg". Digits and letters are kept, so
list every spelling you accept explicitly (for example "0800 555 0142" and "08005550142").
The prompt asks the model for a short answer only; this grader does not look for an answer
buried inside a longer sentence.
"""

from __future__ import annotations

import re
import unicodedata

_PUNCT = re.compile(r"[\W_]+", re.UNICODE)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = _PUNCT.sub(" ", text)
    return " ".join(text.split())


def grade(output: str, expected: str | list[str]) -> bool:
    """True when the normalized output equals one of the accepted answers."""
    accepted = [expected] if isinstance(expected, str) else list(expected)
    if not accepted:
        raise ValueError("no accepted answers given")
    got = normalize(output)
    return any(got == normalize(a) for a in accepted)
