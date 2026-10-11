"""Tests for pre-1970 timestamps.

RFC 9110 doesn't specify a minimum year for the format, but the spec
opts for ``1900..2099``. The 1900 cutoff is loose — well-formed
HTTP-date strings from the early 20th century can still be parsed.
This module pins the behaviour for a few representative years.

Maps to spec §5.3 AC 97 (≥3 tests).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from htdate_pure import format, parse

from conftest import covers


@covers(97, "test_pre_1970_1900")
def test_pre_1970_1900():
    assert parse("Fri, 19 Jan 1900 03:14:07 GMT") == datetime(
        1900, 1, 19, 3, 14, 7, tzinfo=timezone.utc,
    )


@covers(97, "test_pre_1970_1950")
def test_pre_1970_1950():
    # 6 Nov 1950 was a Monday.
    assert parse("Monday, 06-Nov-50 08:49:37 GMT") == datetime(
        1950, 11, 6, 8, 49, 37, tzinfo=timezone.utc,
    )


@covers(97, "test_pre_1970_1960")
def test_pre_1970_1960():
    # 1 Jan 1960 was a Friday.
    assert parse("Friday, 01-Jan-60 00:00:00 GMT") == datetime(
        1960, 1, 1, 0, 0, 0, tzinfo=timezone.utc,
    )


@covers(97, "test_pre_1970_format_roundtrip")
def test_pre_1970_format_roundtrip():
    parsed = parse("Fri, 19 Jan 1900 03:14:07 GMT")
    rendered = format(parsed)
    assert rendered == "Fri, 19 Jan 1900 03:14:07 GMT"


def test_pre_1970_year_1899_rejected():
    """Year 1899 is below our 1900 minimum and rejected."""
    import pytest
    from htdate_pure.exceptions import InvalidFormat
    with pytest.raises(InvalidFormat) as exc:
        parse("Sun, 06 Nov 1899 08:49:37 GMT")
    assert exc.value.reason == "year_out_of_range"


def test_pre_1970_year_1900_asctime():
    """asctime with a year <1970 parses too."""
    # 1994 format aside; we use 1994 here because the test data
    # happens to match the *instant*. For a real pre-1970 asctime
    # example, exercise 1960.
    # 1 Jan 1960 was a Friday.
    assert parse("Fri Jan  1 00:00:00 1960") == datetime(
        1960, 1, 1, 0, 0, 0, tzinfo=timezone.utc,
    )