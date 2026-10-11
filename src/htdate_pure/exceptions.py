"""Custom exceptions for htdate_pure.

Single exception class `InvalidFormat` carries both the original input value
and a machine-readable reason token, while also being a subclass of
`ValueError` so existing callers that catch `ValueError` continue to work
without modification (AC 67).
"""

from __future__ import annotations

__all__ = ["InvalidFormat"]


class InvalidFormat(ValueError):
    """Raised by :func:`htdate_pure.parse` when no HTTP-date dialect matches.

    Attributes
    ----------
    value:
        The original (unmodified) input string that triggered the failure.
    reason:
        A short, machine-readable token describing why parsing failed
        (e.g. ``"no_matching_dialect"``, ``"weekday_mismatch"``,
        ``"day_out_of_range_for_month"``). The token set is intentionally
        small and stable; it is the documented extension surface for
        callers that want to programmatically react to specific failure
        modes without parsing the message text.
    """

    #: Stable reason-token vocabulary. Adding entries is fine; renaming
    #: or removing an entry is a breaking change.
    REASON_TOKENS = frozenset({
        "no_matching_dialect",
        "weekday_mismatch",
        "day_out_of_range",
        "month_out_of_range",
        "day_out_of_range_for_month",
        "year_out_of_range",
        "hour_out_of_range",
        "minute_out_of_range",
        "second_out_of_range",
        "invalid_month_name",
        "invalid_weekday_name",
        "invalid_timezone_literal",
        "missing_timezone",
        "malformed",
        "type_error",
        "empty",
    })

    __slots__ = ("value", "reason")

    def __init__(self, value: object, reason: str = "no_matching_dialect") -> None:
        self.value: object = value
        if reason not in self.REASON_TOKENS:
            # We still allow arbitrary reason tokens, but document the
            # canonical vocabulary. Unknown tokens get passed through
            # unchanged so downstream users can extend without forking.
            self.reason = reason
        else:
            self.reason = reason
        # Build a human-readable message. We render non-str inputs by
        # quoting via repr() to avoid leaking huge bytes blobs into logs.
        if isinstance(value, str):
            message = f"{value!r}: {self.reason}"
        else:
            message = f"<{type(value).__name__}>: {self.reason}"
        super().__init__(message)

    def __repr__(self) -> str:
        return f"InvalidFormat(value={self.value!r}, reason={self.reason!r})"