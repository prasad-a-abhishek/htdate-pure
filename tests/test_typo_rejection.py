"""Negative-path tests: typos, wrong weekday, wrong month, wrong year-range.

These guard against regressions in the parser's strictness — anything
that looks superficially like a valid HTTP-date but violates one of the
RFC's grammar or semantic rules. Maps to spec §5.3 AC 96 (≥8 tests).
"""

from __future__ import annotations

import pytest

from htdate_pure import InvalidFormat, parse

from conftest import covers


TYPO_INPUTS = [
    # (label, input)
    ("lowercase-day", "sun, 06 Nov 1994 08:49:37 GMT"),
    ("lowercase-month", "Sun, 06 nov 1994 08:49:37 GMT"),
    ("lowercase-tz", "Sun, 06 Nov 1994 08:49:37 gmt"),
    ("month-typo-double-v", "Sun, 06 Novv 1994 08:49:37 GMT"),
    ("month-typo-jam", "Sun, 06 Jam 1994 08:49:37 GMT"),
    ("day-out-of-range", "Sun, 32 Nov 1994 08:49:37 GMT"),
    ("month-zero", "Sun, 06 Foo 1994 08:49:37 GMT"),
    ("hour-24", "Sun, 06 Nov 1994 24:00:00 GMT"),
    ("minute-60", "Sun, 06 Nov 1994 08:60:00 GMT"),
    ("second-99", "Sun, 06 Nov 1994 08:49:99 GMT"),
    ("timezone-utc-literal", "Sun, 06 Nov 1994 08:49:37 UTC"),
    ("timezone-numeric", "Sun, 06 Nov 1994 08:49:37 +0000"),
    ("trailing-junk", "Sun, 06 Nov 1994 08:49:37 GMT extra"),
    ("leading-whitespace", " Sun, 06 Nov 1994 08:49:37 GMT"),
    ("trailing-only-tz", "Sun, 06 Nov 1994 08:49:37"),
    ("rfc850-no-hyphen", "Sunday, 06 Nov 94 08:49:37 GMT"),
    ("rfc850-3-digit-year", "Sunday, 06-Nov-994 08:49:37 GMT"),
    ("asctime-year-in-wrong-place", "Sun Nov  6 1994 08:49:37"),
]


@covers(98, "test_typo_rejection_matrix")
@covers(81, "test_typo_rejection_minutes_seconds_00_59")
@pytest.mark.parametrize("label,text", TYPO_INPUTS, ids=[t[0] for t in TYPO_INPUTS])
def test_typo_rejection_matrix(label, text):
    with pytest.raises(InvalidFormat):
        parse(text)


# ---------------------------------------------------------------------------
# Specific failure reason assertions (so silent regressions in the
# error-token table are caught)
# ---------------------------------------------------------------------------


def test_wrong_weekday_imf_reason():
    """Wrong weekday in an IMF string surfaces reason='weekday_mismatch'."""
    # 1994-11-06 was a Sunday; Monday is wrong.
    with pytest.raises(InvalidFormat) as exc:
        parse("Mon, 06 Nov 1994 08:49:37 GMT")
    assert exc.value.reason == "weekday_mismatch"


def test_wrong_weekday_rfc850_reason():
    with pytest.raises(InvalidFormat) as exc:
        parse("Monday, 06-Nov-94 08:49:37 GMT")
    assert exc.value.reason == "weekday_mismatch"


def test_wrong_weekday_asctime_reason():
    with pytest.raises(InvalidFormat) as exc:
        parse("Mon Nov  6 08:49:37 1994")  # Sunday
    assert exc.value.reason == "weekday_mismatch"


def test_invalid_timezone_literal_reason():
    with pytest.raises(InvalidFormat) as exc:
        parse("Sun, 06 Nov 1994 08:49:37 PST")
    assert exc.value.reason == "invalid_timezone_literal"


def test_no_matching_dialect_reason():
    with pytest.raises(InvalidFormat) as exc:
        parse("totally not a date")
    assert exc.value.reason == "no_matching_dialect"


def test_invalid_format_is_value_error():
    """``InvalidFormat`` subclasses ``ValueError`` (AC 67)."""
    try:
        parse("garbage")
    except ValueError as exc:
        assert isinstance(exc, InvalidFormat)
    else:
        pytest.fail("parse() should have raised")