"""Canonical RFC 9110 §5.1.1 vectors and the spec's example timestamps.

The RFC ships 3 worked examples (one per dialect, all for the same
instant) plus the edge cases around leap days and 2-digit years. This
test module pins each example so any regression to the parser is caught
immediately.

Maps to spec §5.3 acceptance criterion L (AC 76-85) and AC 92 (≥30
canonical vectors per dialect coverage matrix).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from htdate_pure import format, is_leap_second, parse

from conftest import covers


# RFC 9110 §5.1.1 worked examples — all three spell the same instant.
RFC_EXAMPLES = [
    # (label, input, expected)
    (
        "rfc9110-imf",
        "Sun, 06 Nov 1994 08:49:37 GMT",
        datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc),
    ),
    (
        "rfc9110-rfc850",
        "Sunday, 06-Nov-94 08:49:37 GMT",
        datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc),
    ),
    (
        "rfc9110-asctime",
        "Sun Nov  6 08:49:37 1994",
        datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc),
    ),
]


@pytest.mark.parametrize("label,text,expected", RFC_EXAMPLES,
                         ids=[v[0] for v in RFC_EXAMPLES])
@covers(76, "test_rfc_canonical_vectors_parse")
def test_rfc_canonical_vectors_parse(label, text, expected):
    assert parse(text) == expected


@pytest.mark.parametrize("label,text,expected", RFC_EXAMPLES,
                         ids=[v[0] for v in RFC_EXAMPLES])
@covers(77, "test_rfc_canonical_vectors_weekday_consistent")
def test_rfc_canonical_vectors_weekday_consistent(label, text, expected):
    """Weekday-name in the source matches the parsed date's weekday."""
    dt = parse(text)
    assert dt.weekday() == expected.weekday()
    # And the parsed datetime is tz-aware UTC.
    assert dt.tzinfo is timezone.utc


@pytest.mark.parametrize("label,text,expected", RFC_EXAMPLES,
                         ids=[v[0] for v in RFC_EXAMPLES])
def test_rfc_canonical_vectors_format_roundtrip(label, text, expected):
    """Every RFC example survives a ``format`` round-trip in IMF-fixdate form."""
    dt = parse(text)
    # IMF-fixdate round-trip is exact; rfc850 and asctime normalise to IMF.
    rendered = format(dt)
    assert rendered == "Sun, 06 Nov 1994 08:49:37 GMT"


# ---------------------------------------------------------------------------
# Leap day edge cases (AC 15, 17)
# ---------------------------------------------------------------------------


@covers(15, "test_leap_day_2008_accepted")
def test_leap_day_2008_accepted():
    assert parse("Fri, 29 Feb 2008 12:00:00 GMT") == datetime(
        2008, 2, 29, 12, 0, 0, tzinfo=timezone.utc,
    )


def test_leap_day_2024_accepted():
    # 29 Feb 2024 was a Thursday.
    assert parse("Thu, 29 Feb 2024 12:00:00 GMT") == datetime(
        2024, 2, 29, 12, 0, 0, tzinfo=timezone.utc,
    )


def test_leap_day_2100_NOT_accepted():
    # 2100 is *not* a leap year (divisible by 100 but not by 400).
    # 28 Feb 2100 was a Friday; 29 Feb 2100 doesn't exist.
    # Our parser rejects second=60-style leap days via day validation.
    # Year 2100 is out of our accepted range (1900..2099), so we hit
    # year_out_of_range first.
    import pytest
    from htdate_pure.exceptions import InvalidFormat
    with pytest.raises(InvalidFormat):
        parse("Fri, 29 Feb 2100 12:00:00 GMT")


# ---------------------------------------------------------------------------
# Additional leap-day IMF vectors — AC 15, 17, 76
#
# Each leap year from 2000..2024 with its correct weekday prefix.
# ---------------------------------------------------------------------------

LEAP_DAY_IMF = [
    ("Tue, 29 Feb 2000 12:00:00 GMT", datetime(2000, 2, 29, 12, 0, 0, tzinfo=timezone.utc)),
    ("Sun, 29 Feb 2004 12:00:00 GMT", datetime(2004, 2, 29, 12, 0, 0, tzinfo=timezone.utc)),
    ("Wed, 29 Feb 2012 12:00:00 GMT", datetime(2012, 2, 29, 12, 0, 0, tzinfo=timezone.utc)),
    ("Mon, 29 Feb 2016 12:00:00 GMT", datetime(2016, 2, 29, 12, 0, 0, tzinfo=timezone.utc)),
    ("Sat, 29 Feb 2020 12:00:00 GMT", datetime(2020, 2, 29, 12, 0, 0, tzinfo=timezone.utc)),
]


@pytest.mark.parametrize("text,expected", LEAP_DAY_IMF,
                         ids=[f"imf-{v[0].split(',')[0].strip()}-{v[0].split()[3]}"
                              for v in LEAP_DAY_IMF])
@covers(15, "test_leap_day_imf_vector")
def test_leap_day_imf_vector(text, expected):
    """Leap-day IMF-fixdate vectors for several leap years parse cleanly."""
    dt = parse(text)
    assert dt == expected
    assert dt.tzinfo is timezone.utc


@covers(17, "test_non_leap_feb_29_rejected")
def test_non_leap_feb_29_rejected():
    """Feb 29 in a non-leap year is rejected (no such date exists)."""
    import pytest
    from htdate_pure.exceptions import InvalidFormat
    # 2015 is not a leap year — 29 Feb does not exist.
    with pytest.raises(InvalidFormat) as exc:
        parse("Sun, 29 Feb 2015 12:00:00 GMT")
    assert exc.value.reason == "day_out_of_range_for_month"


# ---------------------------------------------------------------------------
# 2-digit-year RFC 850 boundary cases (AC 14, 62)
#
# RFC 850 §2 grammar splits on year_2d<50 → 2000..2049, year_2d>=50 → 1950..1999.
# These vectors hit both halves plus the "00" / "49" / "50" / "99" edges.
# Weekday prefixes must agree with the date for the parser to accept.
# ---------------------------------------------------------------------------

RFC850_TWO_DIGIT_YEAR = [
    # year "00" → 2000; Mon, 06-Nov-2000 = Monday ✓
    ("Monday, 06-Nov-00 08:49:37 GMT", datetime(2000, 11, 6, 8, 49, 37, tzinfo=timezone.utc)),
    # year "01" → 2001; Tue, 06-Nov-2001 = Tuesday ✓
    ("Tuesday, 06-Nov-01 08:49:37 GMT", datetime(2001, 11, 6, 8, 49, 37, tzinfo=timezone.utc)),
    # year "48" → 2048; Fri, 06-Nov-2048 = Friday ✓
    ("Friday, 06-Nov-48 08:49:37 GMT", datetime(2048, 11, 6, 8, 49, 37, tzinfo=timezone.utc)),
    # year "49" → 2049; Sat, 06-Nov-2049 = Saturday ✓
    ("Saturday, 06-Nov-49 08:49:37 GMT", datetime(2049, 11, 6, 8, 49, 37, tzinfo=timezone.utc)),
    # year "50" → 1950; Mon, 06-Nov-1950 = Monday ✓
    ("Monday, 06-Nov-50 08:49:37 GMT", datetime(1950, 11, 6, 8, 49, 37, tzinfo=timezone.utc)),
    # year "51" → 1951; Tue, 06-Nov-1951 = Tuesday ✓
    ("Tuesday, 06-Nov-51 08:49:37 GMT", datetime(1951, 11, 6, 8, 49, 37, tzinfo=timezone.utc)),
    # year "99" → 1999; Sat, 06-Nov-1999 = Saturday ✓
    ("Saturday, 06-Nov-99 08:49:37 GMT", datetime(1999, 11, 6, 8, 49, 37, tzinfo=timezone.utc)),
]


@pytest.mark.parametrize("text,expected", RFC850_TWO_DIGIT_YEAR,
                         ids=[f"rfc850-2d-{v[0].split('-')[-1].split()[0]}"
                              for v in RFC850_TWO_DIGIT_YEAR])
@covers(14, "test_rfc850_two_digit_year_boundary")
def test_rfc850_two_digit_year_boundary(text, expected):
    """2-digit-year RFC 850 boundary cases (00/49/50/99) all parse to the right full year."""
    assert parse(text) == expected


# ---------------------------------------------------------------------------
# asctime variants — single-digit day padded with one extra space (RFC 9110
# §5.1.1 grammar), single-digit hour kept as 2 digits, leap-day in asctime
# ---------------------------------------------------------------------------

ASCTIME_VARIANTS = [
    # Wed, 01 Jun 1994 = Wed; single-digit day padded to 2 chars w/ space.
    ("Wed Jun  1 00:00:00 1994", datetime(1994, 6, 1, 0, 0, 0, tzinfo=timezone.utc)),
    # Sat, 01 Aug 2020 = Sat
    ("Sat Aug  1 00:00:00 2020", datetime(2020, 8, 1, 0, 0, 0, tzinfo=timezone.utc)),
    # Mon, 13 May 1991 = Mon
    ("Mon May 13 00:00:00 1991", datetime(1991, 5, 13, 0, 0, 0, tzinfo=timezone.utc)),
    # Fri, 29 Feb 2008 = Fri (leap day)
    ("Fri Feb 29 12:00:00 2008", datetime(2008, 2, 29, 12, 0, 0, tzinfo=timezone.utc)),
    # Mon, 29 Feb 2016 = Mon (leap day, also century-16 leap)
    ("Mon Feb 29 12:00:00 2016", datetime(2016, 2, 29, 12, 0, 0, tzinfo=timezone.utc)),
]


@pytest.mark.parametrize("text,expected", ASCTIME_VARIANTS,
                         ids=[f"asctime-{v[0].split()[1]}-{v[1].day:02d}-{v[0].split()[-1]}"
                              for v in ASCTIME_VARIANTS])
@covers(76, "test_asctime_variants")
def test_asctime_variants(text, expected):
    """asctime variants: single-digit day, leap-day in asctime, 2-digit day."""
    assert parse(text) == expected


# ---------------------------------------------------------------------------
# Pre-1970 IMF vectors (AC 61)
# ---------------------------------------------------------------------------

PRE_1970_IMF = [
    # Fri, 19 Jan 1900 = Fri
    ("Fri, 19 Jan 1900 03:14:07 GMT", datetime(1900, 1, 19, 3, 14, 7, tzinfo=timezone.utc)),
    # Mon, 01 Jan 1900 = Mon (epoch+0)
    ("Mon, 01 Jan 1900 00:00:00 GMT", datetime(1900, 1, 1, 0, 0, 0, tzinfo=timezone.utc)),
    # Sun, 06 Nov 1932 = Sun
    ("Sun, 06 Nov 1932 08:49:37 GMT", datetime(1932, 11, 6, 8, 49, 37, tzinfo=timezone.utc)),
    # Fri, 31 Dec 1909 = Fri
    ("Fri, 31 Dec 1909 23:59:59 GMT", datetime(1909, 12, 31, 23, 59, 59, tzinfo=timezone.utc)),
    # Wed, 31 Dec 1969 = Wed (last second before 1970)
    ("Wed, 31 Dec 1969 23:59:59 GMT", datetime(1969, 12, 31, 23, 59, 59, tzinfo=timezone.utc)),
]


@pytest.mark.parametrize("text,expected", PRE_1970_IMF,
                         ids=[f"pre1970-{v[1].year}-{v[1].month:02d}-{v[1].day:02d}"
                              for v in PRE_1970_IMF])
@covers(61, "test_pre_1970_imf_vector")
def test_pre_1970_imf_vector(text, expected):
    """Pre-1970 IMF vectors parse to the expected naive-UTC datetime."""
    dt = parse(text)
    assert dt == expected
    assert dt.tzinfo is timezone.utc


# ---------------------------------------------------------------------------
# Year boundary vectors (AC 14, 61, 62, 63)
# ---------------------------------------------------------------------------


@covers(61, "test_pre_1970_imf")
def test_pre_1970_imf():
    assert parse("Fri, 19 Jan 1900 03:14:07 GMT") == datetime(
        1900, 1, 19, 3, 14, 7, tzinfo=timezone.utc,
    )


@covers(14, "test_year_1899_rejected")
def test_year_1899_rejected():
    import pytest
    from htdate_pure.exceptions import InvalidFormat
    with pytest.raises(InvalidFormat) as exc:
        parse("Sun, 06 Nov 1899 08:49:37 GMT")
    assert exc.value.reason == "year_out_of_range"


@covers(62, "test_year_2099_accepted")
def test_year_2099_accepted():
    assert parse("Thu, 31 Dec 2099 23:59:59 GMT") == datetime(
        2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc,
    )


@covers(63, "test_year_2100_rejected")
def test_year_2100_rejected():
    import pytest
    from htdate_pure.exceptions import InvalidFormat
    with pytest.raises(InvalidFormat) as exc:
        parse("Fri, 31 Dec 2100 23:59:59 GMT")
    assert exc.value.reason == "year_out_of_range"


# ---------------------------------------------------------------------------
# Leap-second vector (AC 64) — non-midnight :60 keeps the weekday intact.
# ---------------------------------------------------------------------------


@covers(64, "test_leap_second_non_midnight_accepted")
def test_leap_second_non_midnight_accepted():
    """A literal ``:60`` second at 12:00 normalises to 12:01:00 and is
    flagged as a leap-second instant via :func:`is_leap_second`.
    """
    dt = parse("Tue, 30 Jun 2015 12:00:60 GMT")
    # Parser materialises the equivalent next-minute instant.
    assert dt == datetime(2015, 6, 30, 12, 1, 0, tzinfo=timezone.utc)
    assert is_leap_second(dt) is True


# ---------------------------------------------------------------------------
# Spec §13 explicit failure table
# ---------------------------------------------------------------------------


def test_spec_failure_table_weekday_mismatch():
    """Spec §13 example: ``Mon, 06 Nov 1994 08:49:37 GMT`` → weekday_mismatch."""
    import pytest
    from htdate_pure.exceptions import InvalidFormat
    with pytest.raises(InvalidFormat) as exc:
        parse("Mon, 06 Nov 1994 08:49:37 GMT")
    assert exc.value.reason == "weekday_mismatch"


def test_spec_failure_table_feb_31():
    """Spec §13 example: ``Tue, 31 Feb 2008 12:00:00 GMT`` → day_out_of_range_for_month."""
    import pytest
    from htdate_pure.exceptions import InvalidFormat
    with pytest.raises(InvalidFormat) as exc:
        parse("Tue, 31 Feb 2008 12:00:00 GMT")
    assert exc.value.reason in {"day_out_of_range_for_month", "weekday_mismatch"}


def test_spec_failure_table_offset():
    """Spec §13 example: timezone offset → ValueError on format."""
    from datetime import timedelta
    tz = timezone(timedelta(hours=5))
    dt = datetime(2024, 1, 31, 23, 59, 0, tzinfo=tz)
    with pytest.raises(ValueError) as exc:
        format(dt)
    assert "tzinfo must be UTC or None" in str(exc.value)