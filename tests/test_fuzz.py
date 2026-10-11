"""Fuzz corpus seeds and the smallest possible fuzz harness.

Maps to spec §5.3 acceptance criteria M (AC 99 — fuzz corpus seeds,
AC 100 — Makefile targets).
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

import pytest

from htdate_pure import InvalidFormat, format, parse, parse_dialect

from conftest import covers


# ---------------------------------------------------------------------------
# Fuzz corpus seeds (AC 99)
# ---------------------------------------------------------------------------


# Positive seeds — at least 3 per dialect plus canonical vectors. Spec
# AC 99 requires a minimum of 20 positive seeds. We keep a curated
# selection plus extra edges (leap day, midnight, year boundaries).
FUZZ_CORPUS_POSITIVE = [
    # IMF-fixdate (5)
    "Sun, 06 Nov 1994 08:49:37 GMT",
    "Mon, 01 Jan 2001 00:00:00 GMT",
    "Thu, 31 Dec 2099 23:59:59 GMT",
    "Fri, 29 Feb 2008 12:00:00 GMT",
    "Wed, 15 Mar 2000 12:30:45 GMT",
    # RFC 850 (5)
    "Sunday, 06-Nov-94 08:49:37 GMT",
    "Monday, 01-Jan-01 00:00:00 GMT",
    "Friday, 31-Dec-99 23:59:59 GMT",
    "Friday, 29-Feb-08 12:00:00 GMT",
    "Wednesday, 15-Mar-00 12:30:45 GMT",
    # asctime (5)
    "Sun Nov  6 08:49:37 1994",
    "Mon Jan  1 00:00:00 2001",
    "Thu Dec 31 23:59:59 2099",
    "Fri Feb 29 12:00:00 2008",
    "Wed Mar 15 12:30:45 2000",
    # Boundaries and edges (6 — covers leap-day, midnight, etc.)
    "Sun, 06 Nov 1994 00:00:00 GMT",          # midnight
    "Sat, 31 Dec 2005 23:59:59 GMT",          # year boundary
    "Mon, 29 Feb 2016 12:00:00 GMT",          # leap day in a leap year
    "Mon, 01 Jan 1900 00:00:00 GMT",          # century edge (Mon)
    "Sun, 06 Nov 1994 12:00:00 GMT",          # noon
    "Thu, 01 Jan 2099 00:00:00 GMT",          # near cap
]


# Negative seeds — these should raise InvalidFormat (never crash).
FUZZ_CORPUS_NEGATIVE = [
    "",
    " ",
    "\x00",
    "\t",
    "garbage",
    "not a date",
    "Sun, 06 Nov 1994",
    "Sun , 06 Nov 1994 08:49:37 GMT",
    "Sun, 06 Nov 1994 08:49:37",
    "Sun, 06 Nov 1994 08:49:37 UTC",
    "Sun, 06 Nov 1994 08:49:37 +0000",
    "Sun, 06 Novv 1994 08:49:37 GMT",
    "Sunday 06-Nov-94 08:49:37 GMT",
    "Sunday, 06-Nov-94 08:49:37",
    "Sun Nov  6 1994 08:49:37",
    "Sun Nov  6 08:49:37 PST",
    "Sun, 32 Nov 1994 08:49:37 GMT",
    "Sun, 06 Nov 1899 08:49:37 GMT",
    "Sun, 06 Nov 1994 24:00:00 GMT",
    "Sun, 06 Nov 1994 08:60:00 GMT",
    "Sun, 06 Nov 1994 08:49:99 GMT",
    "a" * 1000,
    "0" * 4096,
]


@covers(99, "test_fuzz_corpus_positive_total")
def test_fuzz_corpus_positive_total():
    assert len(FUZZ_CORPUS_POSITIVE) >= 20  # 12 listed; spec floor is 20.


@covers(99, "test_fuzz_corpus_negative_total")
def test_fuzz_corpus_negative_total():
    # Negative corpus has its own minimum floor (8 per spec).
    assert len(FUZZ_CORPUS_NEGATIVE) >= 8


@covers(99, "test_fuzz_corpus_positive_parses")
@pytest.mark.parametrize("text", FUZZ_CORPUS_POSITIVE)
def test_fuzz_corpus_positive_parses(text):
    """Every positive corpus seed parses cleanly."""
    dt = parse(text)
    assert dt.tzinfo is timezone.utc


@covers(99, "test_fuzz_corpus_negative_raises")
@pytest.mark.parametrize("text", FUZZ_CORPUS_NEGATIVE)
def test_fuzz_corpus_negative_raises(text):
    """Every negative corpus seed raises InvalidFormat (never an unrelated error)."""
    with pytest.raises(InvalidFormat):
        parse(text)


# ---------------------------------------------------------------------------
# Mini fuzz harness — random mutations of positive seeds. We don't ship
# Atheris here (would require a CPython-instrumented build), but the
# random-mutation fuzz exercises the same surface area.
# ---------------------------------------------------------------------------


def _mutate(text: str, rng: random.Random, n_mutations: int) -> str:
    """Apply *n_mutations* random byte-level mutations to *text*."""
    if not text:
        return text
    chars = list(text)
    for _ in range(n_mutations):
        op = rng.choice(["flip", "insert", "delete", "swap", "duplicate"])
        if op == "flip" and chars:
            i = rng.randrange(len(chars))
            chars[i] = chr((ord(chars[i]) + rng.choice([-1, 1])) & 0x7F)
        elif op == "insert":
            i = rng.randrange(len(chars) + 1)
            chars.insert(i, rng.choice(" \t\nabcXYZ012"))
        elif op == "delete" and chars:
            i = rng.randrange(len(chars))
            del chars[i]
        elif op == "swap" and len(chars) >= 2:
            i = rng.randrange(len(chars) - 1)
            chars[i], chars[i + 1] = chars[i + 1], chars[i]
        elif op == "duplicate" and chars:
            i = rng.randrange(len(chars))
            chars.insert(i, chars[i])
    return "".join(chars)


@covers(99, "test_fuzz_random_mutation_does_not_crash")
def test_fuzz_random_mutation_does_not_crash():
    """Random mutations never raise an unhandled exception.

    Either parse() returns a datetime, or it raises InvalidFormat.
    No AttributeError, TypeError, UnicodeDecodeError, etc.
    """
    rng = random.Random(0xC0FFEE)  # deterministic seed
    for seed in FUZZ_CORPUS_POSITIVE:
        for _ in range(10):
            mutant = _mutate(seed, rng, n_mutations=3)
            try:
                dt = parse(mutant)
                # If it parsed, it must be tz-aware UTC.
                assert dt.tzinfo is timezone.utc
            except InvalidFormat:
                pass  # structured error is fine
            # Any other exception type is a failure.


@covers(98, "test_fuzz_surfaces_documented")
def test_fuzz_surfaces_documented():
    """Spec §11 fuzz surfaces are all callable & total over junk input."""
    from htdate_pure import format as _format
    # Surface 1: parse()
    for s in ("garbage", "", "\x00", None, b"bytes", 12345, []):
        try:
            parse(s)  # type: ignore[arg-type]
        except InvalidFormat:
            pass
        except (TypeError, AttributeError, UnicodeDecodeError) as exc:
            pytest.fail(f"parse({s!r}) raised unstructured: {exc!r}")
    # Surface 2: format()
    for dt in (None, "garbage", [], {}, 12345):
        try:
            _format(dt)  # type: ignore[arg-type]
        except (ValueError, TypeError, AttributeError):
            pass
    # Surface 3: parse_dialect()
    for s in ("garbage", "", None, b"bytes", 12345, []):
        result = parse_dialect(s)  # type: ignore[arg-type]
        assert result is None or result in {"imf", "rfc850", "asctime"}
    # Surface 4: InvalidFormat exception (must be a ValueError subclass)
    assert issubclass(InvalidFormat, ValueError)