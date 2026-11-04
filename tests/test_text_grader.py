import pytest

from costlab.graders import text

# Gate 2 for normalized_text: pass every accepted answer, fail obviously wrong ones.


@pytest.mark.parametrize(
    "output, expected",
    [
        ("30", "30"),
        ("30.", "30"),
        ("  Thirty  ", ["thirty", "30"]),
        ("FINAL SALE", "final sale"),
        ("15%", "15"),
        ("0800 555 0142", ["0800 555 0142", "08005550142"]),
        ("08005550142", ["0800 555 0142", "08005550142"]),
        ("returns@oakridge.example", "returns oakridge example"),
        ("Monday to Friday", "monday to friday"),
        ("9:00", "9 00"),
        ("189.00", ["189", "189.00"]),
        ("2 °C", "2 °C"),
        ("white or graphite", ["white or graphite", "graphite or white"]),
    ],
)
def test_passes_accepted_answers(output, expected):
    assert text.grade(output, expected) is True


@pytest.mark.parametrize(
    "output, expected",
    [
        ("", "30"),
        ("31", "30"),
        ("The return window is 30 days.", "30"),  # buried in a sentence: not forgiven
        ("no", "yes"),
        ("final sale items", "final sale"),
        ("18900", "189"),
        ("10 °C", "2 °C"),
        ("graphite", ["white or graphite", "white"]),
    ],
)
def test_fails_wrong_answers(output, expected):
    assert text.grade(output, expected) is False


def test_needs_at_least_one_accepted_answer():
    with pytest.raises(ValueError):
        text.grade("x", [])
