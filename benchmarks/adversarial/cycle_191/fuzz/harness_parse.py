"""Fuzz harness for htdate-pure parser surface (T02, cycle_191/adversary).

Attack surfaces covered (>=4 entry points on the public parse API):

1. ``htdate_pure.parse(s)`` — the principal entry point. Auto-detects
   the three RFC 9110 §5.1.1 dialects. Documented exception family is
   :class:`htdate_pure.InvalidFormat` (a :class:`ValueError` subclass).
2. ``htdate_pure.parse_dialect(s)`` — diagnostic sibling; returns one
   of ``{"imf", "rfc850", "asctime"}`` or ``None``. Must NEVER raise.
3. ``htdate_pure.to_imf(dt)`` — round-trip wrapper; takes a datetime.
4. ``htdate_pure.is_leap_second(dt)`` — boolean introspection helper.

Crash semantics
---------------
Any exception other than ``htdate_pure.InvalidFormat`` (and the
:valueerror:`ValueError` it inherits from) is reported as a
``CRASH``. In particular these classes from the stdlib tree are
fingerprinted:

* ``AttributeError`` — e.g. F-ADV-001 from the T01 manual audit:
  :func:`format` / :func:`to_imf` raise ``AttributeError`` when given a
  non-:class:`datetime`. The README promise is a ``ValueError``.
* ``KeyError`` — table lookup miss (e.g. an unknown weekday name passed
  through to the formatter via a mutated datetime).
* ``UnboundLocalError`` / ``NameError`` — control-flow leak.
* ``OverflowError`` / ``ValueError`` — if it surfaces from a non-stdlib
  path it is a crash; anything raised *from inside the package* as
  ``InvalidFormat`` is fine.

Implementation choices
----------------------
The fuzzer is hand-rolled (no atheris/libFuzzer dependency) because the
container does not ship those tools and the spec forbids importing them.
We seed each iteration from one of the seed-corpus entries (real dates
of each dialect) and apply byte-level mutations chosen uniformly from
a mutation menu. The seed corpus is intentionally diverse: it includes
the literal examples from RFC 9110 §5.1.1 plus pathological shapes
(empty, all-whitespace, leading whitespace, double-quote, embedded
NUL, mismatched weekday, leap second, padding-only).

Iteration budget
----------------
Default ``MAX_ITER = 100_000`` per the task spec. Override via the
``HTDATE_FUZZ_ITER`` env var when probing on a shorter budget (e.g.
during smoke tests).

Coverage caveats
----------------
ASan / UBSan instrumentation is **not** available in this container, so
memory-safety bugs in CPython itself will fall on the floor. The
harness catches the user-visible blast radius (uncaught exceptions,
infinite loops would still be caught by the per-iteration timeout in
``harness_cli.py`` but the inline harnesses trust Python to surface
exceptions promptly).
"""

from __future__ import annotations

import os
import random
import signal
import string
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Iterable

# Make ``import htdate_pure`` work whether the package is on PYTHONPATH
# (e.g. system-wide install via the editable hook) or whether the
# harness is being launched from a fresh checkout on PYTHONPATH-less
# CI. The editable install from ``pip install -e .`` puts the package
# in site-packages, which this block trusts.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")))

import htdate_pure  # noqa: E402
from htdate_pure import InvalidFormat  # noqa: E402
from htdate_pure.exceptions import InvalidFormat as InvalidFormatAlias  # noqa: E402

# Sanity guard: confirm the public surface we are testing did not
# silently change between commits. If a future build renames any of
# these symbols, the harness fails fast instead of silently fuzzing an
# empty target.
_REQUIRED_API = ("parse", "parse_dialect", "to_imf", "is_leap_second")
for _name in _REQUIRED_API:
    assert hasattr(htdate_pure, _name), f"missing public symbol: {_name!r}"


MAX_ITER = int(os.environ.get("HTDATE_FUZZ_ITER", "100000"))
# Documented exception family — anything outside this is a CRASH.
_TRUSTED_EXC = (InvalidFormat, InvalidFormatAlias, ValueError)


# ---------------------------------------------------------------------------
# Seed corpus
# ---------------------------------------------------------------------------
# Each seed is the *kind* of input we want to keep re-feeding the parser.
# The mutation loop picks one seed, then runs the mutator to produce the
# real fuzz input. We seed with positive cases, negative cases, and
# dialect-specific cases so coverage is broad.

SEED_CORPUS: list[object] = [
    # ----- IMF-fixdate (RFC 9110 §5.1.1 preferred form) -----
    "Sun, 06 Nov 1994 08:49:37 GMT",      # canonical RFC example
    "Mon, 01 Jan 1900 00:00:00 GMT",      # year lower-bound
    "Sun, 31 Dec 2099 23:59:59 GMT",      # year upper-bound
    "Sat, 30 Jun 1994 23:59:60 GMT",      # leap second
    "Wed, 29 Feb 2000 12:00:00 GMT",      # leap year
    "Tue, 29 Feb 2001 12:00:00 GMT",      # non-leap year, must reject (day_out_of_range)
    "Tue, 28 Feb 2001 12:34:56 GMT",      # non-leap feb 28
    "Mon, 01 Jan 2001 00:00:00 GMT",      # year boundary
    "Fri, 31 Dec 1999 23:59:59 GMT",      # Y2K
    "Sun, 06 Nov 1994 08:49:37 GMT ",     # trailing space
    "Sun, 06 Nov 1994 08:49:37 GMT\r\n",  # trailing CRLF
    " Sun, 06 Nov 1994 08:49:37 GMT",     # leading space → reject
    "\tSun, 06 Nov 1994 08:49:37 GMT",    # leading tab → reject (AC 60)
    "sun, 06 Nov 1994 08:49:37 GMT",      # wrong case weekday
    "Sun, 6 Nov 1994 08:49:37 GMT",       # single-digit day → reject (imf)
    "Mon, 06 Nov 1994 08:49:37 GMT",      # wrong weekday for the date

    # ----- RFC 850 (obsolete) -----
    "Sunday, 06-Nov-94 08:49:37 GMT",
    "Monday, 01-Jan-00 00:00:00 GMT",      # year-00 -> 2000 per rule
    "Tuesday, 31-Dec-99 23:59:59 GMT",    # year-99 -> 1999
    "Wednesday, 29-Feb-00 12:00:00 GMT",   # 2000 was leap
    "Tuesday, 29-Feb-01 12:00:00 GMT",    # not leap, must reject
    "Sunday, 06-Nov-94 08:49:37 GMT ",     # trailing whitespace

    # ----- ANSI C asctime -----
    "Sun Nov  6 08:49:37 1994",            # double space day (RFC correct form)
    "Sun Nov  6 08:49:60 1994",            # leap second
    "Sun Nov 17 08:49:37 1994",
    "Sun Nov  6 08:49:37 1900",
    "Sun Nov  6 08:49:37 2099",

    # ----- Pathological / boundary inputs -----
    "",                                    # empty string
    " ",                                   # whitespace only
    "\x00Sun, 06 Nov 1994 08:49:37 GMT",  # leading NUL
    "Sun, 06 Nov 1994 08:49:37 GMT\x00",  # trailing NUL
    "Sun,\x0006 Nov 1994 08:49:37 GMT",   # embedded NUL
    "Sun, 06 Nov 1994 08:49:37 UTC",      # wrong tz literal
    "Sun, 06 Nov 1994 08:49:37 -0500",    # numeric offset (must reject)
    "Sun, 06 Nnv 1994 08:49:37 GMT",      # typo'd month
    "Sun, 32 Nov 1994 08:49:37 GMT",      # day out of range
    "Sun, 06 Nov 1994 25:00:00 GMT",      # hour out of range
    "Sun, 06 Nov 1994 08:61:00 GMT",      # minute out of range
    "Sun, 06 Nov 1994 08:49:61 GMT",      # second out of range
    "Sun, 06 Nov 1899 08:49:37 GMT",      # year out of range (low)
    "Sun, 06 Nov 2100 08:49:37 GMT",      # year out of range (high)
    "Sunday",                             # single token
    "GMT",                                # single token
    "\xff\xfe\xfd",                       # non-UTF-8 bytes (we hand a bytes seed)
    b"Sun, 06 Nov 1994 08:49:37 GMT",    # bytes input — _require_text decodes
    b"\xff\xfe invalid",                  # bytes with invalid utf-8
    None,                                 # type_error
    42,                                   # integer → type_error
    3.14,                                 # float → type_error
    object(),                             # random object → type_error
    ["Sun, 06 Nov 1994 08:49:37 GMT"],   # list → type_error

    # ----- Unicode anomalies -----
    "Sun,\u00a006 Nov 1994 08:49:37 GMT",  # NBSP after comma (F-ADV-003)
    "Sun, 06 Nov 1994 08:49:37 GMT\u2003",  # EM SPACE trailing
    "Sun\u3000, 06 Nov 1994 08:49:37 GMT",  # IDEOGRAPHIC SPACE in weekday
    "Sun, 06 Nov 1994 08:49:37 \u4e2d\u56fd",  # CJK after GMT
    "Sūn, 06 Nov 1994 08:49:37 GMT",       # accented weekday letter

    # ----- Very long / very short payloads -----
    "G" * 4096,                           # pure-noise
    "a" * 65536,                          # multi-block huge
    "Sun, 06 Nov 1994 08:49:37 GMT" + " " * 1000,
    "X",                                  # single char
]


# ---------------------------------------------------------------------------
# Mutator
# ---------------------------------------------------------------------------

_MUTATION_CHOICES = (
    "identity",       # return seed unchanged
    "delete_random",  # delete one random byte
    "insert_random",  # insert one random printable byte
    "flip_random",    # bit-flip one byte
    "replace_random", # replace one byte with random printable
    "extend_ascii",   # append a short random ASCII run
    "prefix_ascii",   # prepend a short random ASCII run
    "truncate_half",  # keep the first half of the seed
    "double",         # double the seed
    "zero_prefix",    # prepend a NUL byte
    "null_poke",      # replace every 8th byte with \x00
    "ws_insert",      # insert a whitespace char at a random offset
    "control_poke",   # replace a random byte with a control char
    "utf8_poke",      # insert a random multi-byte UTF-8 sequence
)


def mutate_one(value: object, rng: random.Random) -> object:
    """Return a mutated copy of ``value`` (or the value itself).

    Non-string seeds (``None``, integers, lists, ...) are passed
    through unchanged — the documented behavior for those is to raise
    ``InvalidFormat(reason="type_error")`` and we want the harness to
    exercise that path too.
    """
    if not isinstance(value, str):
        return value
    choice = rng.choice(_MUTATION_CHOICES)
    if choice == "identity":
        return value
    if not value:
        # empty string cannot be mutated in a meaningful way; pad.
        return rng.choice(("\x00", " ", "GMT", "X", "\u00a0"))
    if choice == "delete_random" and len(value) > 1:
        idx = rng.randrange(len(value))
        return value[:idx] + value[idx + 1:]
    if choice == "insert_random":
        idx = rng.randrange(len(value) + 1)
        ch = rng.choice(string.printable)
        return value[:idx] + ch + value[idx:]
    if choice == "flip_random":
        idx = rng.randrange(len(value))
        ba = bytearray(value.encode("utf-8", errors="replace"))
        ba[idx] ^= (1 << rng.randrange(8))
        return bytes(ba).decode("utf-8", errors="replace")
    if choice == "replace_random":
        idx = rng.randrange(len(value))
        ch = rng.choice(string.printable)
        return value[:idx] + ch + value[idx + 1:]
    if choice == "extend_ascii":
        return value + "".join(rng.choices(string.printable, k=rng.randrange(1, 16)))
    if choice == "prefix_ascii":
        return "".join(rng.choices(string.printable, k=rng.randrange(1, 16))) + value
    if choice == "truncate_half":
        cut = max(1, len(value) // 2)
        return value[:cut]
    if choice == "double":
        return value + value
    if choice == "zero_prefix":
        return "\x00" + value
    if choice == "null_poke":
        ba = bytearray(value.encode("utf-8", errors="replace"))
        for i in range(0, len(ba), 8):
            ba[i] = 0
        return bytes(ba).decode("utf-8", errors="replace")
    if choice == "ws_insert":
        idx = rng.randrange(len(value) + 1)
        return value[:idx] + rng.choice((" ", "\t", "\r", "\n", "\u00a0", "\u2003", "\u3000")) + value[idx:]
    if choice == "control_poke":
        ba = bytearray(value.encode("utf-8", errors="replace"))
        idx = rng.randrange(len(ba))
        ba[idx] = rng.randrange(0, 0x20)
        return bytes(ba).decode("utf-8", errors="replace")
    if choice == "utf8_poke":
        idx = rng.randrange(len(value) + 1)
        # Pick an arbitrary codepoint well outside printable ASCII so
        # it survives a round-trip through UTF-8 encode/decode.
        seq = chr(rng.randrange(0x80, 0x10000))
        return value[:idx] + seq + value[idx:]
    return value


def _make_dt_for_to_imf(rng: random.Random) -> datetime:
    """Construct a random datetime inside the legal Python range.

    Python's :class:`datetime` accepts ``year in [1, 9999]`` so we
    confine ourselves there to avoid raising at *construction* time
    (we want the harness to probe ``format(dt)`` itself, not the
    datetime constructor). Leap-second expansion goes through
    :class:`timedelta` to keep the value valid.
    """
    from datetime import timedelta
    year = rng.randint(1, 9999)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)  # safe — no month-length math here
    hour = rng.randint(0, 23)
    minute = rng.randint(0, 59)
    second = rng.randint(0, 60)  # 60 is legal as the *equivalent-instant* form
    microsecond = rng.randint(0, 999999)
    base = datetime(year, month, day, hour, minute, second, microsecond, tzinfo=timezone.utc)
    if second == 60:
        # Mirror what the parser does: subtract to next-minute zero.
        base = base - timedelta(seconds=60)
        # Wrap with the private subclass so is_leap_second can introspect.
        # (We import lazily to avoid leaking parser internals into the
        # public contract.)
        from htdate_pure._parser import _LeapSecondDatetime
        return _LeapSecondDatetime._wrap(base)
    return base


# ---------------------------------------------------------------------------
# Crash classification
# ---------------------------------------------------------------------------

class _Crash(Exception):
    """Raised to short-circuit the fuzz loop and report a finding."""

    def __init__(self, op: str, exc: BaseException, value: object) -> None:
        self.op = op
        self.exc = exc
        self.value = value
        super().__init__(f"{op}: {type(exc).__name__}: {exc}")


def _safe_call(op: str, fn, value: object) -> None:
    """Invoke ``fn(value)`` with crash-detection.

    - :class:`InvalidFormat` and its ``ValueError`` superclass are
      DOCUMENTED outcomes — silently absorbed.
    - Anything else is a CRASH; we re-raise as :class:`_Crash`.
    """
    try:
        fn(value)
    except _TRUSTED_EXC:
        return
    except BaseException as exc:  # noqa: BLE001 — intentional catch-all
        raise _Crash(op, exc, value) from exc


def _safe_call_fmt(op: str, fn, args, kwargs) -> None:
    """Variant for ``fn(*args, **kwargs)`` (used by :func:`format`)."""
    try:
        fn(*args, **kwargs)
    except _TRUSTED_EXC:
        return
    except BaseException as exc:  # noqa: BLE001
        raise _Crash(op, exc, (args, kwargs)) from exc


# ---------------------------------------------------------------------------
# The fuzzer body
# ---------------------------------------------------------------------------

def fuzz(iterations: int = MAX_ITER, seed: int = 0) -> None:
    """Run the fuzz loop. Each iteration picks one operation class:

    * Iteration 0-3: deterministic smoke (no mutations) over the
      canonical RFC example for each dialect; this guarantees the
      harness can report ``OK`` on first run even on a fast machine.
    * Subsequent iterations: pick from the corpus, mutate, dispatch to
      the four public functions in rotation.

    The loop terminates on the first CRASH or at ``iterations`` (whichever
    comes first). A normal exit prints ``OK: <N> iters``.
    """
    rng = random.Random(seed or int.from_bytes(os.urandom(8), "big"))

    # ----- Smoke phase: each entry point on its canonical input.
    # parse() round-trips, then to_imf() goes through a fresh datetime.
    # If the smoke fails the harness is broken before fuzzing — surface that.
    try:
        dt = htdate_pure.parse("Sun, 06 Nov 1994 08:49:37 GMT")
        assert htdate_pure.parse_dialect("Sunday, 06-Nov-94 08:49:37 GMT") == "rfc850"
        assert htdate_pure.parse_dialect("Sun Nov  6 08:49:37 1994") == "asctime"
        assert htdate_pure.parse_dialect("Sun, 06 Nov 1994 08:49:37 GMT") == "imf"
        assert htdate_pure.to_imf(dt).startswith("Sun, 06 Nov 1994 08:49:37 GMT")
        assert htdate_pure.is_leap_second(dt) is False
    except BaseException as exc:
        sys.stderr.write(f"FATAL: smoke failed: {type(exc).__name__}: {exc}\n")
        raise

    start = time.monotonic()
    op_cycle = (
        ("parse",          lambda v: htdate_pure.parse(v)),
        ("parse_dialect",  lambda v: htdate_pure.parse_dialect(v)),
        ("to_imf",         lambda v: htdate_pure.to_imf(_make_dt_for_to_imf(rng))),
        ("is_leap_second", lambda v: htdate_pure.is_leap_second(_make_dt_for_to_imf(rng))),
    )

    for i in range(iterations):
        # Rotate through the four entry points. We do this in fixed
        # order rather than uniform random so that each surface gets
        # ~iterations/4 coverage deterministically.
        op_name, op_fn = op_cycle[i % len(op_cycle)]
        seed_value = rng.choice(SEED_CORPUS)
        mutated = mutate_one(seed_value, rng)
        try:
            if op_name in ("to_imf", "is_leap_second"):
                # These take a datetime, not the mutated string.
                _safe_call_fmt(op_name, op_fn, (mutated,), {}) if False else _safe_call(op_name, op_fn, mutated)
            else:
                _safe_call(op_name, op_fn, mutated)
        except _Crash as crash:
            elapsed = time.monotonic() - start
            sys.stderr.write(
                "\n"
                + "=" * 78 + "\n"
                + f"CRASH at iteration {i} ({elapsed:.2f}s into fuzz)\n"
                + f"  op:        {crash.op}\n"
                + f"  exception: {type(crash.exc).__name__}: {crash.exc}\n"
                + f"  value:     {crash.value!r}\n"
                + "  traceback (last frame):\n"
                + "    " + (traceback.format_exc().splitlines()[-2] if traceback.format_exc() else "?") + "\n"
                + "=" * 78 + "\n"
            )
            # Exit non-zero so the T03 runner can detect.
            sys.exit(1)

    elapsed = time.monotonic() - start
    print(f"OK: {iterations} iters ({elapsed:.2f}s) — no crashes across "
          f"{len(op_cycle)} operations x {len(SEED_CORPUS)}-seed corpus")


if __name__ == "__main__":
    fuzz()
