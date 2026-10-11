"""Fuzz harness for htdate-pure formatter surface (T02, cycle_191/adversary).

Attack surfaces covered:

1. :func:`htdate_pure.format(dt, *, target='imf')` — the principal
   serializer. Accepts naive and UTC-aware datetimes. The ``target``
   keyword is a :class:`typing.Literal` constrained to ``"imf"``;
   passing any other string raises :class:`ValueError`. Passing a
   non-UTC ``tzinfo`` raises :class:`ValueError`.
2. :func:`htdate_pure.to_imf(dt)` — round-trip wrapper for
   :func:`format`. Shares the same exception surface.
3. Pathological non-:class:`datetime` inputs — covered here even
   though the type signature says ``dt: datetime``. The T01 manual
   audit at commit ``48d029c`` found F-ADV-001: passing a non-datetime
   raises ``AttributeError`` rather than the documented ``ValueError``,
   which contradicts the README's exception-safety contract (lines
   195-199). This harness fingerprints that path so any future fix
   surfaces immediately.

Crash semantics
---------------
* ``ValueError`` — DOCUMENTED (target rejection, non-UTC tzinfo).
* ``OverflowError`` — DOCUMENTED for ``datetime`` constructors, but
  the formatter must not raise it on constructed values; if it does,
  we still treat it as a CRASH to catch one-shot exploits early.
* ``AttributeError`` / ``KeyError`` / ``TypeError`` — CRASH (signals
  either F-ADV-001 or a typo in our tables).
* Anything else — CRASH.

Implementation
--------------
Hand-rolled mutation. Each iteration:

* Picks a random ``datetime`` shape from a generator pool that
  exercises tzinfo (None, UTC, +timedelta, -timedelta, fixed-offset
  arithmetic, naive-UTC, plus the legitimate leap-second rebound
  payload).
* Constructs the datetime (catching the documented
  ``ValueError`` / ``OverflowError`` the stdlib raises for out-of-range
  months/days — those are NOT in scope for this harness).
* Calls :func:`format` and verifies the return is a 29-character
  string (``"Sun, 06 Nov 1994 08:49:37 GMT"`` shape) on the success
  path. On the failure path, the *only* acceptable exception is
  ``ValueError``; ``AttributeError`` flips the CRASH counter.

Iteration budget
----------------
``MAX_ITER = 100_000`` per the task spec, overridable via
``HTDATE_FUZZ_ITER``.

Coverage caveats
----------------
ASan/UBSan instrumentation is unavailable in this container.
"""

from __future__ import annotations

import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone, tzinfo

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")))

import htdate_pure  # noqa: E402
from htdate_pure import format as _fmt, to_imf as _to_imf  # noqa: E402

MAX_ITER = int(os.environ.get("HTDATE_FUZZ_ITER", "100000"))


# ---------------------------------------------------------------------------
# tzinfo fixtures
# ---------------------------------------------------------------------------
# Each fixture is a callable returning a fresh tzinfo; we want fresh
# instances so cached ``utcoffset`` results don't accidentally
# immunize subsequent calls.

class _FixedOffset(tzinfo):
    """A minimal fixed-offset tzinfo used to seed non-UTC inputs."""

    __slots__ = ("_minutes",)

    def __init__(self, minutes: int) -> None:
        self._minutes = minutes

    def utcoffset(self, dt):  # noqa: ARG002
        return timedelta(minutes=self._minutes)

    def dst(self, dt):  # noqa: ARG002
        return timedelta(0)

    def tzname(self, dt):  # noqa: ARG002
        total = self._minutes
        sign = "+" if total >= 0 else "-"
        total = abs(total)
        h, m = divmod(total, 60)
        return f"UTC{sign}{h:02d}:{m:02d}"


def _fixed_offset(minutes: int):
    return _FixedOffset(minutes)


def _weird_tzinfo(rng: random.Random):
    """Build a tzinfo with bizarre utcoffset arithmetic.

    We deliberately deviate from the standard fixed-offset rules:
    - a tzinfo that returns ``None`` from utcoffset (treated as UTC)
    - a tzinfo whose offset is a non-integer number of seconds
    - a tzinfo that returns a zero offset but tzname != "UTC"
    """
    choice = rng.choice((
        "none_utcoffset",
        "fractional_seconds",
        "zero_but_named",
        "enormous_offset",
    ))
    if choice == "none_utcoffset":
        class _NoneOffset(tzinfo):
            def utcoffset(self, dt):  # noqa: ARG002
                return None
            def dst(self, dt):  # noqa: ARG002
                return timedelta(0)
            def tzname(self, dt):  # noqa: ARG002
                return "Z"
        return _NoneOffset()
    if choice == "fractional_seconds":
        # 0.5-second offset. _validate_tzinfo uses total_seconds().
        class _Half(tzinfo):
            def utcoffset(self, dt):  # noqa: ARG002
                return timedelta(microseconds=500_000)
            def dst(self, dt):  # noqa: ARG002
                return timedelta(0)
        return _Half()
    if choice == "zero_but_named":
        class _ZeroNamed(tzinfo):
            def utcoffset(self, dt):  # noqa: ARG002
                return timedelta(0)
            def dst(self, dt):  # noqa: ARG002
                return timedelta(0)
            def tzname(self, dt):  # noqa: ARG002
                return "Europe/Paris"
        return _ZeroNamed()
    # enormous_offset: 25h forward. _validate_tzinfo rejects it.
    class _Enormous(tzinfo):
        def utcoffset(self, dt):  # noqa: ARG002
            return timedelta(hours=25)
        def dst(self, dt):  # noqa: ARG002
            return timedelta(0)
    return _Enormous()


# ---------------------------------------------------------------------------
# Datetime generator pool
# ---------------------------------------------------------------------------

def _gen_legal_aware_dt(rng: random.Random) -> datetime:
    """Datetime inside the legal range, timezone-aware, UTC or None."""
    year = rng.randint(1, 9999)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)  # avoids month-length math
    hour = rng.randint(0, 23)
    minute = rng.randint(0, 59)
    # second may be 0..60 — Python permits 60 when constructed via
    # timedelta math; we simulate that here:
    second = rng.choice((0, rng.randint(0, 60)))
    microsecond = rng.randint(0, 999999)
    tz_choice = rng.choice(("utc", "none", "weird_zero"))
    tz = (
        timezone.utc
        if tz_choice == "utc"
        else None
        if tz_choice == "none"
        else _weird_tzinfo(rng)
    )
    return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=tz)


def _gen_non_utc_dt(rng: random.Random) -> datetime:
    """Datetime with a *non-UTC* offset — must be rejected by format()."""
    offset_minutes = rng.choice((-720, -480, -300, -60, 60, 300, 480, 720, 840))
    # 14h+ / 12h- are valid Python offsets; some are extreme but legal.
    year = rng.randint(1, 9999)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    hour = rng.randint(0, 23)
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    return datetime(year, month, day, hour, minute, second, tzinfo=_fixed_offset(offset_minutes))


def _gen_leap_second_dt(rng: random.Random) -> datetime:
    """Mirror the parser's leap-second payload: a datetime at second=0 of
    the NEXT minute, but flagged with ``leap_second=True``. RFC 9110
    §5.1.1 allows ``second=60``; our formatter renders the equivalent
    instant which happens to look like the next minute."""
    from htdate_pure._parser import _LeapSecondDatetime

    year = rng.randint(1994, 2099)  # leap-second years live in IERS range
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    hour = rng.randint(0, 23)
    minute = rng.randint(0, 58)  # base moment; we add 60 to roll over
    base = datetime(year, month, day, hour, minute, 0, tzinfo=timezone.utc)
    rolled = base + timedelta(seconds=60)
    return _LeapSecondDatetime._wrap(rolled)


# ---------------------------------------------------------------------------
# Crash classification
# ---------------------------------------------------------------------------

class _Crash(Exception):
    def __init__(self, op: str, exc: BaseException, payload) -> None:
        self.op = op
        self.exc = exc
        self.payload = payload


def _call_format(dt: datetime, *, target):
    """Call :func:`format` with crash classification.

    The DOCUMENTED exception is :class:`ValueError` for non-UTC tzinfo
    or for non-``"imf"`` target strings. Anything else is a CRASH.
    """
    try:
        out = _fmt(dt, target=target)
    except ValueError:
        return  # documented
    except BaseException as exc:  # noqa: BLE001
        raise _Crash("format", exc, (dt, target)) from exc
    # Successful path — verify the output shape. The only legal
    # output is the 29-character IMF-fixdate form.
    if not isinstance(out, str):
        raise _Crash(
            "format",
            TypeError(f"expected str, got {type(out).__name__}"),
            (dt, target),
        )
    if len(out) != 29 or not out.endswith(" GMT"):
        raise _Crash(
            "format",
            ValueError(f"unexpected output shape: {out!r}"),
            (dt, target),
        )


def _call_to_imf(value):
    """Call :func:`to_imf` with crash classification.

    The README explicitly documents that :func:`to_imf` accepts the
    same datetime shape as :func:`format`. Per F-ADV-001 it currently
    raises ``AttributeError`` for non-datetime inputs; we treat that
    as a CRASH so a future fix surfaces immediately.
    """
    try:
        out = _to_imf(value)
    except ValueError:
        return  # documented
    except BaseException as exc:  # noqa: BLE001
        raise _Crash("to_imf", exc, value) from exc
    if not isinstance(out, str):
        raise _Crash(
            "to_imf",
            TypeError(f"expected str, got {type(out).__name__}"),
            value,
        )


def fuzz(iterations: int = MAX_ITER, seed: int = 0) -> None:
    """Run the formatter-surface fuzz loop.

    Each iteration picks one of:

    * legal_aware_dt   — datetime with UTC / None / zero-offset tzinfo
                         + format(..., target='imf'). Should succeed.
    * non_utc_dt       — datetime with a non-zero offset + format().
                         Should raise ``ValueError``.
    * leap_second_dt   — _LeapSecondDatetime + format(). Should succeed.
    * bad_target_str   — format(dt, target='rfc850'). Should raise
                         ``ValueError``.
    * type_juggling    — to_imf of a non-datetime. Per F-ADV-001 this
                         currently crashes via ``AttributeError``.

    The loop terminates on the first CRASH.
    """
    rng = random.Random(seed or int.from_bytes(os.urandom(8), "big"))

    # ----- Smoke phase.
    try:
        dt = datetime(2024, 1, 31, 23, 59, 0, tzinfo=timezone.utc)
        out = _fmt(dt)
        assert out == "Wed, 31 Jan 2024 23:59:00 GMT", out
        out2 = _to_imf(dt)
        assert out2 == out
        # Naive datetime is documented to be accepted (treated as UTC).
        naive = datetime(2024, 1, 31, 23, 59, 0)
        assert _fmt(naive) == "Wed, 31 Jan 2024 23:59:00 GMT"
    except BaseException as exc:
        sys.stderr.write(f"FATAL: smoke failed: {type(exc).__name__}: {exc}\n")
        raise

    start = time.monotonic()

    for i in range(iterations):
        op = i % 5
        try:
            if op == 0:
                # Legal aware DT → success expected.
                _call_format(_gen_legal_aware_dt(rng), target="imf")
            elif op == 1:
                # Non-UTC DT → ValueError expected.
                _call_format(_gen_non_utc_dt(rng), target="imf")
            elif op == 2:
                # Leap-second DT → success expected.
                _call_format(_gen_leap_second_dt(rng), target="imf")
            elif op == 3:
                # Bad target → ValueError expected.
                dt = _gen_legal_aware_dt(rng)
                bad_target = rng.choice(("rfc850", "asctime", "iso8601", "ISO", "IMF", "Imf", "", "imf "))
                _call_format(dt, target=bad_target)
            else:
                # Type juggling — feed a non-datetime into to_imf().
                junk = rng.choice((
                    None, 42, 3.14, "Sun, 06 Nov 1994 08:49:37 GMT",
                    b"Sun, 06 Nov 1994 08:49:37 GMT", [dt], {"x": 1},
                    object(), lambda: None,
                ))
                _call_to_imf(junk)
        except _Crash as crash:
            elapsed = time.monotonic() - start
            sys.stderr.write(
                "\n"
                + "=" * 78 + "\n"
                + f"CRASH at iteration {i} ({elapsed:.2f}s into fuzz)\n"
                + f"  op:        {crash.op}\n"
                + f"  exception: {type(crash.exc).__name__}: {crash.exc}\n"
                + f"  payload:   {crash.payload!r}\n"
                + "=" * 78 + "\n"
            )
            sys.exit(1)

    elapsed = time.monotonic() - start
    print(f"OK: {iterations} iters ({elapsed:.2f}s) — no crashes across "
          f"5 formatter surface paths")


if __name__ == "__main__":
    fuzz()
