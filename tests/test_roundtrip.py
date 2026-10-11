"""Cross-check tests against Python stdlib's ``email.utils``.

The stdlib ``email.utils.parsedate_tz`` / ``email.utils.format_datetime``
cover IMF-fixdate only, and lack dialect detection, but they're a useful
reference for the round-trip property (AC 45-47).

Maps to spec §5.3 acceptance criteria G (AC 45-47).
"""

from __future__ import annotations

import email.utils
from datetime import datetime, timezone

import pytest

from htdate_pure import format, parse

from conftest import covers


CANONICAL_VECTORS = [
    # (imf_fixdate_str, calendar_date)
    ("Sun, 06 Nov 1994 08:49:37 GMT", (1994, 11, 6, 8, 49, 37)),
    ("Mon, 01 Jan 2001 00:00:00 GMT", (2001, 1, 1, 0, 0, 0)),
    ("Thu, 31 Dec 2099 23:59:59 GMT", (2099, 12, 31, 23, 59, 59)),
    ("Wed, 15 Mar 2000 12:30:45 GMT", (2000, 3, 15, 12, 30, 45)),
    ("Thu, 29 Feb 2024 23:59:59 GMT", (2024, 2, 29, 23, 59, 59)),
    ("Fri, 01 Apr 2022 06:00:00 GMT", (2022, 4, 1, 6, 0, 0)),
    ("Sat, 30 Aug 2008 18:45:30 GMT", (2008, 8, 30, 18, 45, 30)),
    ("Fri, 19 Jan 1900 03:14:07 GMT", (1900, 1, 19, 3, 14, 7)),
    ("Sun, 06 Nov 1994 08:49:00 GMT", (1994, 11, 6, 8, 49, 0)),
    ("Tue, 01 Jan 2030 00:00:00 GMT", (2030, 1, 1, 0, 0, 0)),
]


@pytest.mark.parametrize("imf_str,fields", CANONICAL_VECTORS,
                         ids=[v[0] for v in CANONICAL_VECTORS])
@covers(45, "test_roundtrip_against_canonical_vectors")
def test_roundtrip_against_canonical_vectors(imf_str, fields):
    """``format(parse(s)) == s`` for canonical IMF-fixdate inputs."""
    parsed = parse(imf_str)
    assert format(parsed) == imf_str


@pytest.mark.parametrize("imf_str,fields", CANONICAL_VECTORS,
                         ids=[v[0] for v in CANONICAL_VECTORS])
@covers(46, "test_roundtrip_through_format")
def test_roundtrip_through_format(imf_str, fields):
    """``parse(format(dt)) == dt`` for any UTC datetime in 1900..2100."""
    y, m, d, H, M, S = fields
    dt = datetime(y, m, d, H, M, S, tzinfo=timezone.utc)
    rendered = format(dt)
    parsed = parse(rendered)
    assert parsed == dt


@covers(47, "test_roundtrip_idempotent")
def test_roundtrip_idempotent():
    s = "Sun, 06 Nov 1994 08:49:39 GMT"
    once = format(parse(s))
    twice = format(parse(once))
    assert once == twice == s


# ---------------------------------------------------------------------------
# Stdlib cross-check (limited to IMF-fixdate)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("imf_str,fields", CANONICAL_VECTORS,
                         ids=[v[0] for v in CANONICAL_VECTORS])
def test_parsedate_tz_agrees_on_imf(imf_str, fields):
    """``email.utils.parsedate_tz`` returns the same components."""
    y, m, d, H, M, S = fields
    stdlib_tuple = email.utils.parsedate_tz(imf_str)
    assert stdlib_tuple is not None
    # ``parsedate_tz`` returns 10 elements in modern Python: year,
    # month, day, hour, minute, second, weekday, julian, offset, ...
    # (microseconds is index 9 when present; we only care about the
    # first 6 + the offset.)
    sy = stdlib_tuple[0]
    sm = stdlib_tuple[1]
    sd = stdlib_tuple[2]
    sh = stdlib_tuple[3]
    smn = stdlib_tuple[4]
    ss = stdlib_tuple[5]
    # Offset may live at index 8 (10-tuple) or 9 (11-tuple); pick the
    # last element defensively. For a well-formed IMF string it is 0.
    offset = stdlib_tuple[-1]
    assert (sy, sm, sd, sh, smn, ss) == (y, m, d, H, M, S)
    assert offset == 0  # GMT -> 0


def test_format_matches_stdlib_imf_shape():
    """``email.utils.format_datetime`` produces an RFC 2822 date — not
    the same literal as IMF-fixdate (it emits ``+0000`` instead of
    ``GMT``). We only check that the *components* agree."""
    dt = datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc)
    our_out = format(dt)
    # Our output ends in GMT.
    assert our_out.endswith("GMT")
    # The stdlib format_datetime emits RFC 2822 with offset; we don't
    # require equality with stdlib output (different format spec), only
    # that the fields match.
    stdlib_out = email.utils.format_datetime(dt)
    assert "06 Nov 1994 08:49:37" in stdlib_out


# ---------------------------------------------------------------------------
# Round-trip across all three dialects
# ---------------------------------------------------------------------------


ROUNDTRIP_THREE = [
    # (input, expected_after_format_parse)
    ("Sun, 06 Nov 1994 08:49:37 GMT", "Sun, 06 Nov 1994 08:49:37 GMT"),
    ("Sunday, 06-Nov-94 08:49:37 GMT", "Sun, 06 Nov 1994 08:49:37 GMT"),
    # asctime has no timezone, so its parsed instant round-trips
    # through IMF-fixdate with the GMT suffix added.
    ("Sun Nov  6 08:49:37 1994", "Sun, 06 Nov 1994 08:49:37 GMT"),
]


@pytest.mark.parametrize("src,expected", ROUNDTRIP_THREE,
                         ids=[v[0] for v in ROUNDTRIP_THREE])
def test_roundtrip_all_dialects(src, expected):
    parsed = parse(src)
    assert format(parsed) == expected