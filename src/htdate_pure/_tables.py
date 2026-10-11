"""Static lookup tables for HTTP-date parsing/formatting.

Centralised here so the parser, formatter, and tests can all share one
source of truth for the weekday and month abbreviation grammars.
"""

from __future__ import annotations

__all__ = [
    "WEEKDAY_3_TO_INDEX",
    "WEEKDAY_FULL_TO_INDEX",
    "WEEKDAY_INDEX_TO_3",
    "MONTH_3_TO_INDEX",
    "MONTH_INDEX_TO_3",
]


# RFC 9110 §5.1.1 day-name grammar. Keys are the exact 3-letter spellings
# from the RFC's day-name rule; the index matches
# ``datetime.date(year, month, day).weekday()`` (Mon=0, Sun=6).
WEEKDAY_3_TO_INDEX: dict[str, int] = {
    "Mon": 0,
    "Tue": 1,
    "Wed": 2,
    "Thu": 3,
    "Fri": 4,
    "Sat": 5,
    "Sun": 6,
}

# RFC 850 uses the *full* day names with a trailing comma, e.g. ``Sunday``.
WEEKDAY_FULL_TO_INDEX: dict[str, int] = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}

WEEKDAY_INDEX_TO_3: list[str] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# RFC 9110 §5.1.1 month-name grammar.
MONTH_3_TO_INDEX: dict[str, int] = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

MONTH_INDEX_TO_3: list[str] = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def is_valid_weekday_3(name: str) -> bool:
    """Return True if *name* is an RFC 9110 3-letter weekday abbreviation.

    Used as a fast pre-check before the cross-validation step in
    :func:`htdate_pure._parser.parse`. Defined here as a tiny helper so
    tests can pin its behaviour cheaply.
    """
    return name in WEEKDAY_3_TO_INDEX


def is_valid_month_3(name: str) -> bool:
    """Return True if *name* is an RFC 9110 3-letter month abbreviation."""
    return name in MONTH_3_TO_INDEX