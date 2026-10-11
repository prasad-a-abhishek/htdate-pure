"""Shared fixtures and pytest configuration for htdate_pure tests.

This file is named ``conftest.py`` so pytest auto-loads it before any
test module. It centralises tiny helpers used across the test suite
(weekday-name table, golden ISO datetime round-trips) so each test
file stays focused on its slice of the 100 ACs.
"""

from __future__ import annotations

import datetime as _dt
from typing import Callable, TypeVar

import pytest

F = TypeVar("F", bound=Callable[..., object])


# 100 acceptance criteria total. We map each one to the test(s) that
# cover it via ``AC_COVERAGE`` so a single missing test is easy to find.
AC_COVERAGE: dict[int, list[str]] = {}


def covers(ac: int, test_id: str) -> Callable[[F], F]:
    """Decorator: register ``test_id`` as covering acceptance criterion ``ac``.

    Usage::

        @covers(1)
        def test_dependencies_empty():
            ...
    """
    def deco(fn: F) -> F:
        AC_COVERAGE.setdefault(ac, []).append(f"{fn.__module__}::{fn.__name__}")
        return fn
    return deco


def all_coverage() -> dict[int, list[str]]:
    """Return a copy of the current coverage map (used by audit helpers)."""
    return {k: list(v) for k, v in AC_COVERAGE.items()}


# Common datetimes used across many tests. Centralised so a calendar
# correction in one place doesn't ripple through the suite.
KNOWN_DATETIME = _dt.datetime(1994, 11, 6, 8, 49, 37, tzinfo=_dt.timezone.utc)


@pytest.fixture
def known_imf() -> str:
    return "Sun, 06 Nov 1994 08:49:37 GMT"


@pytest.fixture
def known_dt() -> _dt.datetime:
    return _dt.datetime(1994, 11, 6, 8, 49, 37, tzinfo=_dt.timezone.utc)