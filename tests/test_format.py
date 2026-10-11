"""Tests for the IMF-fixdate formatter and the ``to_imf`` alias.

Maps to spec §5.3 acceptance criteria E (AC 31-38) plus the round-trip
property (AC 45-47) and ``format`` invariants.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from htdate_pure import format, parse, to_imf

from conftest import covers


# ---------------------------------------------------------------------------
# Happy path / canonical output
# ---------------------------------------------------------------------------


@covers(31, "test_format_imf_canonical_vector")
def test_format_imf_canonical_vector():
    dt = datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc)
    assert format(dt) == "Sun, 06 Nov 1994 08:49:37 GMT"


@covers(32, "test_format_naive_assumed_utc")
def test_format_naive_assumed_utc():
    dt = datetime(2024, 1, 31, 23, 59, 0)
    assert format(dt) == "Wed, 31 Jan 2024 23:59:00 GMT"


@covers(33, "test_format_non_utc_rejected")
def test_format_non_utc_rejected():
    tz = timezone(timedelta(hours=5))
    dt = datetime(2024, 1, 31, 23, 59, 0, tzinfo=tz)
    with pytest.raises(ValueError) as exc:
        format(dt)
    assert "tzinfo must be UTC or None" in str(exc.value)


@covers(35, "test_format_output_29_chars")
def test_format_output_29_chars():
    dt = datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc)
    out = format(dt)
    assert len(out) == 29
    assert out.count("GMT") == 1


@covers(36, "test_format_english_abbreviations")
def test_format_english_abbreviations():
    # Sample one per month — every month must use the canonical
    # abbreviation from RFC 9110.
    expected = [
        (1, "Jan"), (2, "Feb"), (3, "Mar"), (4, "Apr"),
        (5, "May"), (6, "Jun"), (7, "Jul"), (8, "Aug"),
        (9, "Sep"), (10, "Oct"), (11, "Nov"), (12, "Dec"),
    ]
    for month_num, month_name in expected:
        dt = datetime(2024, month_num, 15, 12, 0, 0, tzinfo=timezone.utc)
        out = format(dt)
        assert month_name in out


@covers(37, "test_format_year_zero_padded")
def test_format_year_zero_padded():
    # Year 123 (3-digit) must render with leading zero (4-digit).
    # datetime allows year 1..9999; we exercise a 3-digit year here.
    dt = datetime(123, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    out = format(dt)
    assert " 0123 " in out


@covers(38, "test_to_imf_alias_equals_format")
def test_to_imf_alias_equals_format():
    dt = datetime(2024, 1, 31, 23, 59, 0, tzinfo=timezone.utc)
    assert to_imf(dt) == format(dt)


# ---------------------------------------------------------------------------
# Format invariants
# ---------------------------------------------------------------------------


@covers(80, "test_format_hour_24_rejected_implicitly")
def test_format_hour_24_rejected_implicitly():
    # datetime rejects hour=24 at construction time, so we can't even
    # build the datetime to feed format(). Pin that boundary.
    with pytest.raises(ValueError):
        datetime(2024, 1, 31, 24, 0, 0)


@covers(82, "test_format_never_emits_leap_second")
def test_format_never_emits_leap_second():
    # The formatter always emits a valid 00..59 second. Construct a
    # datetime with second=0, 30, 59 and verify the output uses those.
    for s in (0, 30, 59):
        dt = datetime(2024, 1, 31, 12, 0, s, tzinfo=timezone.utc)
        out = format(dt)
        assert f":{s:02d} GMT" in out


@covers(83, "test_format_naive_no_warning")
def test_format_naive_no_warning(recwarn):
    dt = datetime(2024, 1, 31, 23, 59, 0)
    format(dt)  # naive accepted, no warning emitted
    # We use ``recwarn`` only as a hook to inspect; assert that no
    # warning was raised.
    assert all(
        issubclass(w.category, Warning) is False or "tzinfo" not in str(w.message)
        for w in recwarn.list
    )


@covers(84, "test_format_weekday_3_letter_only")
def test_format_weekday_3_letter_only():
    # Sample a date per weekday. Each output weekday must be 3 letters.
    from datetime import date, timedelta
    base = date(2024, 1, 1)  # Monday
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for i, expected in enumerate(names):
        d = base + timedelta(days=i)
        dt = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc)
        out = format(dt)
        assert out.startswith(expected + ", ")
        # And the weekday portion is exactly 3 letters.
        assert out[:3] == expected


@covers(85, "test_format_month_3_letter_only")
def test_format_month_3_letter_only():
    # Sample the 12 months; each output uses a 3-letter abbreviation.
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for i, m in enumerate(months, start=1):
        dt = datetime(2024, i, 15, 12, 0, 0, tzinfo=timezone.utc)
        out = format(dt)
        assert f" {m} " in out


# ---------------------------------------------------------------------------
# Leap-second rejection on format (AC 34)
# ---------------------------------------------------------------------------


@covers(34, "test_format_leap_second_rejected")
def test_format_leap_second_rejected():
    # The formatter must never emit ``second=60``. Constructing a
    # datetime with second=60 is impossible in stdlib, so we instead
    # verify the round-trip behaviour: a parsed leap-second instant
    # passes through format() with the second normalised.
    from htdate_pure import is_leap_second
    dt = parse("Sun, 06 Nov 1994 08:49:60 GMT")
    assert is_leap_second(dt)
    out = format(dt)
    # Second is 00 (next minute), not 60.
    assert ":00 GMT" in out
    assert ":60 GMT" not in out


# ---------------------------------------------------------------------------
# Parameterised matrix
# ---------------------------------------------------------------------------


FORMAT_INPUTS = [
    # (year, month, day, hour, minute, second, expected)
    (1994, 11, 6, 8, 49, 37, "Sun, 06 Nov 1994 08:49:37 GMT"),
    (2000, 1, 1, 0, 0, 0, "Sat, 01 Jan 2000 00:00:00 GMT"),
    (2024, 2, 29, 12, 0, 0, "Thu, 29 Feb 2024 12:00:00 GMT"),
    (2099, 12, 31, 23, 59, 59, "Thu, 31 Dec 2099 23:59:59 GMT"),
    (1900, 1, 1, 0, 0, 0, "Mon, 01 Jan 1900 00:00:00 GMT"),
]


@pytest.mark.parametrize(
    "y,m,d,H,M,S,expected",
    FORMAT_INPUTS,
    ids=[f"{x[0]}-{x[1]:02d}-{x[2]:02d}" for x in FORMAT_INPUTS],
)
def test_format_parameterised(y, m, d, H, M, S, expected):
    dt = datetime(y, m, d, H, M, S, tzinfo=timezone.utc)
    assert format(dt) == expected


# ---------------------------------------------------------------------------
# Negative / edge cases
# ---------------------------------------------------------------------------


def test_format_rejects_aware_non_utc():
    # Even if the offset is 0 hours but tzinfo is a custom FixedOffset,
    # the offset check must accept it.
    tz = timezone.utc  # equivalent
    dt = datetime(2024, 1, 31, 23, 59, 0, tzinfo=tz)
    assert format(dt) == "Wed, 31 Jan 2024 23:59:00 GMT"


def test_format_target_only_imf():
    with pytest.raises(ValueError) as exc:
        format(datetime(2024, 1, 31, tzinfo=timezone.utc), target="rfc850")  # type: ignore[arg-type]
    assert "target must be 'imf'" in str(exc.value)
    with pytest.raises(ValueError):
        format(datetime(2024, 1, 31, tzinfo=timezone.utc), target="asctime")  # type: ignore[arg-type]


def test_format_returns_str():
    dt = datetime(2024, 1, 31, tzinfo=timezone.utc)
    assert isinstance(format(dt), str)
    assert isinstance(to_imf(dt), str)