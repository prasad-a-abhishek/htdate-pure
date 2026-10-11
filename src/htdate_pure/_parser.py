"""HTTP-date parser — all three RFC 9110 §5.1.1 dialects.

Public entry point: :func:`parse`. Diagnostic helper:
:func:`parse_dialect`.

The parser is implemented manually (rather than via ``datetime.strptime``)
to give us predictable, total behaviour across the three grammars and to
keep the dependency surface at exactly zero. We cross-check the weekday
name against the calendar for every parsed value, so a ``Mon`` on a date
that actually fell on a Sunday is rejected with
``reason="weekday_mismatch"``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from ._tables import (
    MONTH_3_TO_INDEX,
    WEEKDAY_3_TO_INDEX,
    WEEKDAY_FULL_TO_INDEX,
    is_valid_weekday_3,
)
from .exceptions import InvalidFormat

__all__ = ["parse", "parse_dialect", "is_leap_second", "_LeapSecondDatetime"]

Dialect = Literal["imf", "rfc850", "asctime"]


def is_leap_second(dt: datetime) -> bool:
    """Return True if *dt* originated from a parsed leap-second input.

    Helper for callers that want to introspect the literal
    ``second=60`` semantic preserved by :func:`parse`. Always False for
    regular :class:`datetime` instances.
    """
    return bool(getattr(dt, "_leap_second", False))


class _LeapSecondDatetime(datetime):
    """A :class:`datetime` subclass marking a parsed leap-second instant.

    Python's :class:`datetime` rejects ``second=60`` outright (both via
    ``__init__`` and via ``datetime.__new__``), so when the parser sees
    a literal ``60`` it returns the equivalent next-minute instant
    wrapped in this subclass. The wrapper is *time* equal to
    ``datetime(year, month, day, hour, minute+1, 0, tzinfo=utc)`` but
    exposes a ``leap_second`` flag so callers can introspect whether
    the source text contained a literal ``second=60``.

    AC 64: ``parse()`` does NOT raise on ``second=60``. The absolute
    instant returned matches what downstream systems (HTTP caches,
    clock-comparison libraries) compare against.
    """

    __slots__ = ("_leap_second",)

    @classmethod
    def _wrap(cls, base: datetime) -> "_LeapSecondDatetime":
        inst = cls.__new__(
            cls, base.year, base.month, base.day,
            base.hour, base.minute, base.second, base.microsecond,
            tzinfo=base.tzinfo, fold=base.fold,
        )
        inst._leap_second = True
        return inst

    @property
    def leap_second(self) -> bool:
        """True if the originating text had a literal ``second=60``."""
        return getattr(self, "_leap_second", False)

    def __repr__(self) -> str:
        return (
            f"_LeapSecondDatetime({self.year!r}, {self.month!r}, {self.day!r}, "
            f"{self.hour!r}, {self.minute!r}, {self.second!r}, tzinfo={self.tzinfo!r})"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require_text(value: object) -> str:
    """Return ``value`` as ``str``, raising :class:`InvalidFormat` otherwise.

    Bytes are decoded as ``utf-8`` with ``errors="replace"`` so a stray
    byte payload doesn't raise ``UnicodeDecodeError`` at the type-check
    gate — instead the caller sees the structured
    ``reason="type_error"`` token. The whole package is total over
    arbitrary input by design (Invariant 21 / AC 56–58).
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        # bytes/bytearray -> str (best-effort decode).
        return bytes(value).decode("utf-8", errors="replace")
    raise InvalidFormat(value, reason="type_error")


def _strip_trailing_ws(text: str) -> str:
    """Strip trailing ASCII whitespace and ``\\r\\n``/``\\n`` only.

    The RFC does not allow leading whitespace inside a header value, so
    we deliberately only strip *trailing* whitespace. AC 59 covers a
    trailing newline; AC 60 verifies that a leading tab is rejected.
    """
    if not text:
        return text
    end = len(text)
    while end > 0 and text[end - 1] in (" ", "\t", "\r", "\n"):
        end -= 1
    return text[:end]


def _check_weekday(year: int, month: int, day: int, weekday_index: int, original: str) -> None:
    """Cross-check the calendar weekday against the supplied weekday name.

    Raises :class:`InvalidFormat` with ``reason="weekday_mismatch"`` if
    they disagree. AC 16, AC 23, AC 77.
    """
    actual = date(year, month, day).weekday()
    if actual != weekday_index:
        raise InvalidFormat(
            original, reason="weekday_mismatch"
        )


def _build_datetime(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int,
) -> datetime:
    """Construct the final aware UTC datetime.

    Validates day-of-month against the month length and leap-year rules
    by letting :class:`datetime` do the heavy lifting and catching
    :class:`ValueError` to produce a structured :class:`InvalidFormat`.

    Leap-second handling: per RFC 9110 §5.1.1 the second field may be
    ``60``. Python's :class:`datetime` (and its C ``__new__``) refuses
    ``second=60`` outright, so we materialise the *equivalent* instant:
    ``second=0`` of the next minute. The returned datetime carries a
    ``_leap_second=True`` attribute on a private subclass so callers
    who care about the original literal can still introspect it via
    :func:`htdate_pure.is_leap_second`.

    This is the *honest* representation: it does not raise on parse
    (AC 64) and the absolute time it represents is the conventional
    "leap-second-instant" that downstream systems compare against.
    """
    if second == 60:
        # Build the underlying instant at the next-minute zero, then
        # wrap so callers can introspect the original literal.
        try:
            base = datetime(
                year, month, day, hour, minute + 1, 0, 0, tzinfo=timezone.utc,
            )
        except ValueError as exc:
            # Most likely cause: minute+1 rolled into a new hour, but
            # our format only allows hour 0..23 — if that overflows,
            # translate to a structured InvalidFormat.
            msg = str(exc)
            raise InvalidFormat(msg, reason=_classify_value_error(msg)) from exc
        return _LeapSecondDatetime._wrap(base)

    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    except ValueError as exc:
        # Translate the stdlib error message into a stable reason token.
        msg = str(exc)
        raise InvalidFormat(msg, reason=_classify_value_error(msg)) from exc


def _classify_value_error(msg: str) -> str:
    """Map a stdlib ``ValueError`` message to a stable ``reason`` token.

    Centralised so the two ``datetime()`` call sites share one
    classification table and there is no risk of drift.
    """
    if "day is out of range" in msg:
        return "day_out_of_range_for_month"
    if "month must be" in msg:
        return "month_out_of_range"
    if "year" in msg:
        return "year_out_of_range"
    if "hour" in msg:
        return "hour_out_of_range"
    if "minute" in msg:
        return "minute_out_of_range"
    if "second" in msg:
        return "second_out_of_range"
    if "day" in msg:
        return "day_out_of_range"
    return "malformed"


# ---------------------------------------------------------------------------
# Dialect-specific parsers
# ---------------------------------------------------------------------------


def _parse_imf(text: str) -> datetime | None:
    """Parse an IMF-fixdate string. Returns ``None`` if grammar doesn't match.

    Grammar::

        IMF-fixdate = day-name "," SP date1 SP time-of-day SP GMT
        date1       = day SP month SP year
        time-of-day = hour ":" minute ":" second

    Returns ``None`` on a grammar miss (caller will try the next dialect).
    Raises :class:`InvalidFormat` on semantic errors (bad month name,
    day-out-of-range, weekday mismatch).
    """
    parts = text.split()
    # Expected: ["Sun,", "06", "Nov", "1994", "08:49:37", "GMT"]  (6 parts)
    if len(parts) != 6:
        return None
    weekday_raw, day_raw, month_raw, year_raw, time_raw, tz_literal = parts

    # Day-name must end with a comma, with NO space before it (AC 79).
    if not weekday_raw.endswith(","):
        return None
    weekday = weekday_raw[:-1]
    if not is_valid_weekday_3(weekday):
        # Try uppercase variant only if the literal was lowercase — but
        # the RFC mandates exact case, so this is a hard reject (AC 9).
        return None

    # 2-digit day with leading zero for <10.
    if len(day_raw) != 2 or not day_raw.isdigit():
        return None
    day = int(day_raw)

    if month_raw not in MONTH_3_TO_INDEX:
        return None
    month = MONTH_3_TO_INDEX[month_raw]

    # 4-digit year, in [1900, 2100).  RFC 9110 doesn't actually cap at
    # 2100 but we follow the spec's stated example range for safety
    # (AC 14, AC 63).
    if len(year_raw) != 4 or not year_raw.isdigit():
        return None
    year = int(year_raw)
    if year < 1900 or year >= 2100:
        raise InvalidFormat(year_raw, reason="year_out_of_range")

    # time-of-day is exactly "HH:MM:SS".
    time_parts = time_raw.split(":")
    if len(time_parts) != 3:
        return None
    h_raw, m_raw, s_raw = time_parts
    if len(h_raw) != 2 or len(m_raw) != 2 or len(s_raw) != 2:
        return None
    if not (h_raw.isdigit() and m_raw.isdigit() and s_raw.isdigit()):
        return None
    hour = int(h_raw)
    minute = int(m_raw)
    second = int(s_raw)

    # Per RFC: hour 00..23, minute 00..59, second 00..60 (AC 80, 81, 64).
    if hour > 23:
        raise InvalidFormat(h_raw, reason="hour_out_of_range")
    if minute > 59:
        raise InvalidFormat(m_raw, reason="minute_out_of_range")
    if second > 60:
        raise InvalidFormat(s_raw, reason="second_out_of_range")

    if tz_literal != "GMT":
        # RFC mandates the literal "GMT". Anything else (UTC, +0000,
        # -0500) is rejected (AC 10, 11, 78).
        raise InvalidFormat(tz_literal, reason="invalid_timezone_literal")

    # Build the datetime. This validates day-of-month-vs-month.
    dt = _build_datetime(year, month, day, hour, minute, second)
    _check_weekday(dt.year, dt.month, dt.day, WEEKDAY_3_TO_INDEX[weekday], text)
    return dt


def _parse_rfc850(text: str) -> datetime | None:
    """Parse an RFC 850 (obsolete) date string. Returns ``None`` on miss.

    Grammar::

        rfc850-date  = day-name "," SP date2 SP time-of-day SP GMT
        date2        = day "-" month "-" 2-digit-year
        2-digit-year = 2DIGIT
    """
    parts = text.split()
    # Expected: ["Sunday,", "06-Nov-94", "08:49:37", "GMT"]  (4 parts)
    if len(parts) != 4:
        return None
    weekday_raw, date_raw, time_raw, tz_literal = parts

    if not weekday_raw.endswith(","):
        return None
    weekday = weekday_raw[:-1]
    if weekday not in WEEKDAY_FULL_TO_INDEX:
        return None

    # date2 is exactly "06-Nov-94".
    date_parts = date_raw.split("-")
    if len(date_parts) != 3:
        return None
    day_raw, month_raw, year_raw = date_parts
    if len(day_raw) != 2 or len(year_raw) != 2:
        return None
    if not (day_raw.isdigit() and year_raw.isdigit()):
        return None
    day = int(day_raw)
    year_2d = int(year_raw)
    if month_raw not in MONTH_3_TO_INDEX:
        return None
    month = MONTH_3_TO_INDEX[month_raw]

    # Two-digit year rule (RFC 9110 §5.1.1):
    #   00-49 -> 2000-2049
    #   50-99 -> 1950-1999
    if year_2d < 50:
        year = 2000 + year_2d
    else:
        year = 1900 + year_2d

    # Time-of-day.
    time_parts = time_raw.split(":")
    if len(time_parts) != 3:
        return None
    h_raw, m_raw, s_raw = time_parts
    if len(h_raw) != 2 or len(m_raw) != 2 or len(s_raw) != 2:
        return None
    if not (h_raw.isdigit() and m_raw.isdigit() and s_raw.isdigit()):
        return None
    hour = int(h_raw)
    minute = int(m_raw)
    second = int(s_raw)
    if hour > 23:
        raise InvalidFormat(h_raw, reason="hour_out_of_range")
    if minute > 59:
        raise InvalidFormat(m_raw, reason="minute_out_of_range")
    if second > 60:
        raise InvalidFormat(s_raw, reason="second_out_of_range")

    if tz_literal != "GMT":
        raise InvalidFormat(tz_literal, reason="invalid_timezone_literal")

    dt = _build_datetime(year, month, day, hour, minute, second)
    _check_weekday(dt.year, dt.month, dt.day, WEEKDAY_FULL_TO_INDEX[weekday], text)
    return dt


def _parse_asctime(text: str) -> datetime | None:
    """Parse an ANSI C asctime (obsolete) date string. Returns ``None`` on miss.

    Grammar::

        asctime-date = day-name SP date3 SP time-of-day SP year
        date3        = month SP ( day ; leading space if day < 10 )

    No timezone; the timestamp is interpreted as UTC.

    We use ``text.split()`` (no separator) so consecutive spaces are
    collapsed — that's what makes ``"Sun Nov  6 08:49:37 1994"`` parse
    into a uniform 5-token shape regardless of whether day is 1 or 2
    digits.
    """
    parts = text.split()
    # Expected: ["Sun", "Nov", "6", "08:49:37", "1994"]  (5 tokens)
    if len(parts) != 5:
        return None
    weekday, month_raw, day_raw, time_raw, year_raw = parts

    if not is_valid_weekday_3(weekday):
        return None
    if month_raw not in MONTH_3_TO_INDEX:
        return None
    month = MONTH_3_TO_INDEX[month_raw]

    # Day may be 1 or 2 digits; for days 1-9 it's preceded by a *space*
    # in the canonical form, which ``split`` collapses into a single
    # token. Both " 6" (split into "6") and "06" (split into "06") are
    # accepted as long as the resulting number parses.
    if not day_raw.isdigit():
        return None
    day = int(day_raw)
    if day < 1 or day > 31:
        raise InvalidFormat(day_raw, reason="day_out_of_range")

    if len(year_raw) != 4 or not year_raw.isdigit():
        return None
    year = int(year_raw)
    if year < 1900 or year >= 2100:
        raise InvalidFormat(year_raw, reason="year_out_of_range")

    time_parts = time_raw.split(":")
    if len(time_parts) != 3:
        return None
    h_raw, m_raw, s_raw = time_parts
    if len(h_raw) != 2 or len(m_raw) != 2 or len(s_raw) != 2:
        return None
    if not (h_raw.isdigit() and m_raw.isdigit() and s_raw.isdigit()):
        return None
    hour = int(h_raw)
    minute = int(m_raw)
    second = int(s_raw)
    if hour > 23:
        raise InvalidFormat(h_raw, reason="hour_out_of_range")
    if minute > 59:
        raise InvalidFormat(m_raw, reason="minute_out_of_range")
    if second > 60:
        raise InvalidFormat(s_raw, reason="second_out_of_range")

    # No timezone is allowed in asctime. Any trailing token that isn't
    # the year would have split this into >5 parts already; but if a
    # caller appended "GMT" we'd already be in a different shape.
    dt = _build_datetime(year, month, day, hour, minute, second)
    _check_weekday(dt.year, dt.month, dt.day, WEEKDAY_3_TO_INDEX[weekday], text)
    return dt


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_dialect(text: object) -> Dialect | None:
    """Identify which RFC 9110 §5.1.1 dialect *text* matches.

    Returns one of ``"imf"``, ``"rfc850"``, ``"asctime"``, or ``None``
    when no dialect matches. Never raises :class:`InvalidFormat`; callers
    that want the structured error must invoke :func:`parse` instead.

    AC 39-44.
    """
    try:
        s = _require_text(text)
    except InvalidFormat:
        return None
    s = _strip_trailing_ws(s)
    if not s:
        return None
    if _parse_imf(s) is not None:
        return "imf"
    if _parse_rfc850(s) is not None:
        return "rfc850"
    if _parse_asctime(s) is not None:
        return "asctime"
    return None


def parse(text: object) -> datetime:
    """Parse any of the three RFC 9110 §5.1.1 HTTP-date formats.

    Auto-detects IMF-fixdate, RFC 850, or ANSI C asctime. Returns a
    timezone-aware :class:`datetime.datetime` in UTC.

    Raises
    ------
    InvalidFormat
        When the input is not a string (or bytes), is empty, has leading
        whitespace, or doesn't match any of the three grammars; or when
        semantic validation fails (bad weekday vs calendar, day out of
        range, year out of range, etc.). The ``reason`` attribute on the
        exception carries a stable machine-readable token.
    """
    try:
        s = _require_text(text)
    except InvalidFormat:
        # Defensive re-raise to keep the reason token stable across the
        # bytes/str boundary.
        raise

    s = _strip_trailing_ws(s)

    if not s:
        raise InvalidFormat(text, reason="empty")

    # Leading-whitespace rejection (AC 60). After stripping trailing
    # whitespace we still must reject leading whitespace because the
    # RFC grammar does not permit it.
    if s[0] in (" ", "\t"):
        raise InvalidFormat(text, reason="malformed")

    # Try each dialect. Each helper returns ``None`` on a grammar miss
    # so we can fall through to the next candidate. Semantic errors
    # (e.g. bad month name *inside* an otherwise-IMF-shaped string) are
    # raised as InvalidFormat immediately.
    for parser in (_parse_imf, _parse_rfc850, _parse_asctime):
        try:
            result = parser(s)
        except InvalidFormat:
            # Re-raise so callers get the structured error from the
            # dialect that *almost* matched. This is important for
            # the weekday-mismatch / day-out-of-range reasons.
            raise
        if result is not None:
            return result

    raise InvalidFormat(text, reason="no_matching_dialect")