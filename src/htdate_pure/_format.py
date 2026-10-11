"""IMF-fixdate formatter (the only output format RFC 9110 §5.1.1 allows).

RFC 9110 §5.1.1 explicitly forbids emitting the obsolete two formats
(rfc850-date and asctime-date); the canonical output is always
IMF-fixdate. This module implements that single output shape and the
tzinfo validation that goes with it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from ._tables import WEEKDAY_INDEX_TO_3, MONTH_INDEX_TO_3

__all__ = ["format", "to_imf"]


# Only one target format exists today. The ``Literal`` parameter is
# pinned to ``"imf"`` so callers get a ``TypeError`` at the call site
# if they pass an obsolete target name (e.g. ``target="rfc850"``).
Target = Literal["imf"]


def _validate_tzinfo(dt: datetime) -> None:
    """Reject datetimes with a non-UTC tzinfo.

    We accept naive datetimes (treated as UTC) and any ``datetime``
    whose ``utcoffset()`` returns ``timedelta(0)``. Anything else is a
    programming error and we raise :class:`ValueError` so callers don't
    silently produce a non-GMT header (AC 33).
    """
    if dt.tzinfo is None:
        return  # naive -> UTC, documented
    offset = dt.utcoffset()
    if offset is None:
        return
    if offset.total_seconds() != 0:
        offset_str = _format_offset(offset)
        raise ValueError(
            f"tzinfo must be UTC or None (got {offset_str})"
        )


def _format_offset(offset) -> str:
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    h, rem = divmod(total, 3600)
    m, _ = divmod(rem, 60)
    return f"{sign}{h:02d}:{m:02d}"


def format(dt: datetime, *, target: Target = "imf") -> str:
    """Format a :class:`datetime` as an RFC 9110 IMF-fixdate string.

    Always emits IMF-fixdate (the only format a generator is permitted
    to emit per RFC 9110 §5.1.1). The ``target`` keyword is reserved
    for future expansion and currently only accepts ``"imf"``; passing
    any other value raises :class:`ValueError`.

    Parameters
    ----------
    dt:
        The datetime to format. May be naive (interpreted as UTC) or
        timezone-aware with ``tzinfo`` pinned to UTC. Any other
        ``tzinfo`` raises :class:`ValueError` (AC 33).
    target:
        Reserved for forward compatibility; only ``"imf"`` is accepted.

    Returns
    -------
    str
        Exactly 29 characters in IMF-fixdate form, e.g.
        ``"Sun, 06 Nov 1994 08:49:37 GMT"``.

    Raises
    ------
    ValueError
        If ``dt.tzinfo`` is set to anything other than UTC, or if
        ``target`` is not ``"imf"``.
    """
    if target != "imf":
        raise ValueError(
            f"target must be 'imf' (got {target!r}); "
            "RFC 9110 §5.1.1 forbids emitting obsolete formats"
        )
    _validate_tzinfo(dt)

    weekday_name = WEEKDAY_INDEX_TO_3[dt.weekday()]
    month_name = MONTH_INDEX_TO_3[dt.month]
    # ``dt.year`` is the calendar year. RFC 9110 expects 4-digit year,
    # zero-padded (AC 37). Years outside 0000-9999 are accepted by
    # datetime but we still emit them in 4-digit form via format spec.
    return (
        f"{weekday_name}, "
        f"{dt.day:02d} {month_name} {dt.year:04d} "
        f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} GMT"
    )


def to_imf(dt: datetime) -> str:
    """Convenience alias for :func:`format`.

    Provided so callers writing canonical HTTP-date jargon
    (``to_imf``) don't have to import the generic ``format`` name.
    """
    return format(dt)