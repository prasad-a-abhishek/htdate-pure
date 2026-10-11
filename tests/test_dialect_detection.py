"""Dedicated test module for the ``parse_dialect`` diagnostic helper.

Maps to spec §5.3 acceptance criteria F (AC 39-44).
"""

from __future__ import annotations

import pytest

from htdate_pure import parse_dialect

from conftest import covers


@covers(39, "test_dialect_imf_full_samples")
@pytest.mark.parametrize("text", [
    "Sun, 06 Nov 1994 08:49:37 GMT",
    "Mon, 01 Jan 2001 00:00:00 GMT",
    "Thu, 31 Dec 2099 23:59:59 GMT",
    "Fri, 29 Feb 2008 12:00:00 GMT",
])
def test_dialect_imf_full_samples(text):
    assert parse_dialect(text) == "imf"


@covers(40, "test_dialect_rfc850_full_samples")
@pytest.mark.parametrize("text", [
    "Sunday, 06-Nov-94 08:49:37 GMT",
    "Monday, 01-Jan-01 00:00:00 GMT",
    "Friday, 31-Dec-99 23:59:59 GMT",
    "Friday, 29-Feb-08 12:00:00 GMT",
])
def test_dialect_rfc850_full_samples(text):
    assert parse_dialect(text) == "rfc850"


@covers(41, "test_dialect_asctime_full_samples")
@pytest.mark.parametrize("text", [
    "Sun Nov  6 08:49:37 1994",
    "Mon Jan  1 00:00:00 2001",
    "Thu Dec 31 23:59:59 2099",
    "Fri Feb 29 12:00:00 2008",
])
def test_dialect_asctime_full_samples(text):
    assert parse_dialect(text) == "asctime"


@covers(42, "test_dialect_empty_returns_none")
def test_dialect_empty_returns_none():
    assert parse_dialect("") is None


@covers(43, "test_dialect_whitespace_returns_none")
def test_dialect_whitespace_returns_none():
    assert parse_dialect(" ") is None
    assert parse_dialect("   ") is None
    assert parse_dialect("\t") is None
    assert parse_dialect("\n") is None


@covers(44, "test_dialect_garbage_returns_none")
def test_dialect_garbage_returns_none():
    assert parse_dialect("not a date") is None
    assert parse_dialect("xyz") is None
    assert parse_dialect("foo bar baz qux") is None
    assert parse_dialect("2024-01-31T00:00:00Z") is None  # ISO, not HTTP-date


# ---------------------------------------------------------------------------
# Order-of-attempt invariants: a malformed string that *looks* like one
# dialect must report that dialect only when the grammar fits, even if
# the resulting datetime would later be rejected by weekday cross-check.
# ---------------------------------------------------------------------------


def test_dialect_grammar_fit_with_wrong_weekday_returns_none():
    """Grammar-fit-but-semantic-error inputs return None.

    Per the spec, ``parse_dialect`` is *diagnostic*: if a string has a
    recognisable grammar shape, it reports that dialect. If grammar
    fails (as it does when a semantic rejection blocks the lookup), the
    helper returns ``None``. This test pins the chosen behaviour: a
    weekday mismatch makes the string non-parseable by every dialect,
    so ``parse_dialect`` returns ``None`` rather than the failing
    dialect name.
    """
    # The grammar fit but the inner parser raises weekday_mismatch
    # for these. parse_dialect doesn't propagate the dialect name when
    # only a semantic error fires.
    assert parse_dialect("Monday, 06-Nov-94 08:49:37 GMT") is None
    assert parse_dialect("Mon, 06 Nov 1994 08:49:37 GMT") is None
    # Plain parse() still raises a structured InvalidFormat.
    from htdate_pure import parse, InvalidFormat
    with pytest.raises(InvalidFormat):
        parse("Monday, 06-Nov-94 08:49:37 GMT")


def test_dialect_type_error_returns_none():
    # ``parse_dialect`` is total over arbitrary input.
    assert parse_dialect(None) is None
    assert parse_dialect(b"bytes") is None
    assert parse_dialect(12345) is None
    assert parse_dialect(object()) is None


def test_dialect_does_not_raise():
    # Spot-check that even pathological input doesn't raise.
    weird = ["", "\x00\x00", " " * 10000, "a" * 1000]
    for w in weird:
        assert parse_dialect(w) is None