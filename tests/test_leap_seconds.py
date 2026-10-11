"""Tests covering leap-second handling (AC 34, 64-65, 82).

Per RFC 9110 §5.1.1 the second field may be ``60`` to accommodate leap
seconds. Python's :class:`datetime` rejects ``60`` outright, so the
parser returns the equivalent next-minute instant on a private
subclass (see :class:`htdate_pure._parser._LeapSecondDatetime`). The
formatter must never *emit* ``second=60`` (AC 82).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from htdate_pure import format, is_leap_second, parse
from htdate_pure.exceptions import InvalidFormat

from conftest import covers


@covers(64, "test_leap_second_imf_accepted")
def test_leap_second_imf_accepted():
    dt = parse("Sun, 06 Nov 1994 08:49:60 GMT")
    # The returned instant equals 08:50:00 of the same date.
    assert dt == datetime(1994, 11, 6, 8, 50, 0, tzinfo=timezone.utc)
    # And the leap_second flag is set.
    assert is_leap_second(dt)


@covers(64, "test_leap_second_rfc850_accepted")
def test_leap_second_rfc850_accepted():
    dt = parse("Sunday, 06-Nov-94 08:49:60 GMT")
    assert is_leap_second(dt)


@covers(64, "test_leap_second_asctime_accepted")
def test_leap_second_asctime_accepted():
    dt = parse("Sun Nov  6 08:49:60 1994")
    assert is_leap_second(dt)


@covers(65, "test_second_61_imf_rejected")
def test_second_61_imf_rejected():
    with pytest.raises(InvalidFormat) as exc:
        parse("Sun, 06 Nov 1994 08:49:61 GMT")
    assert exc.value.reason == "second_out_of_range"


@covers(65, "test_second_61_rfc850_rejected")
def test_second_61_rfc850_rejected():
    with pytest.raises(InvalidFormat) as exc:
        parse("Sunday, 06-Nov-94 08:49:61 GMT")
    assert exc.value.reason == "second_out_of_range"


@covers(34, "test_format_leap_second_normalises")
def test_format_leap_second_normalises():
    dt = parse("Sun, 06 Nov 1994 08:49:60 GMT")
    out = format(dt)
    # The formatter refuses to emit ``:60 GMT`` — it normalises to 00.
    assert ":00 GMT" in out
    assert ":60 GMT" not in out


@covers(82, "test_format_never_emits_leap_second")
def test_format_never_emits_leap_second():
    # Build a regular datetime; the formatter must use 00..59 only.
    for s in range(60):
        dt = datetime(2024, 1, 31, 12, 0, s, tzinfo=timezone.utc)
        out = format(dt)
        assert f":{s:02d} GMT" in out
        assert ":60 GMT" not in out


def test_is_leap_second_returns_false_for_plain_datetime():
    plain = datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc)
    assert is_leap_second(plain) is False


# Hour-23 / minute-59 boundary test for leap-second roll-over:
# ``08:59:60`` should advance to ``09:00:00`` (next minute, same hour).
def test_leap_second_rolls_into_next_minute():
    dt = parse("Sun, 06 Nov 1994 08:59:60 GMT")
    assert dt.hour == 9
    assert dt.minute == 0
    assert dt.second == 0
    assert is_leap_second(dt)