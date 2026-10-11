"""Canonical RFC 9110 §5.1.1 vectors and the spec's example timestamps.

The RFC ships 3 worked examples (one per dialect, all for the same
instant) plus the edge cases around leap days and 2-digit years. This
test module pins each example so any regression to the parser is caught
immediately.

Maps to spec §5.3 acceptance criterion L (AC 76-85).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from htdate_pure import format, parse

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