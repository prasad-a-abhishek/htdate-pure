"""htdate-pure — zero-dependency HTTP-date parser/serializer (RFC 9110 §5.1.1).

Quick start::

    >>> from htdate_pure import parse, parse_dialect, format, to_imf, InvalidFormat
    >>> from datetime import datetime, timezone
    >>> parse("Sun, 06 Nov 1994 08:49:37 GMT")
    datetime.datetime(1994, 11, 6, 8, 49, 37, tzinfo=datetime.timezone.utc)
    >>> parse_dialect("Sunday, 06-Nov-94 08:49:37 GMT")
    'rfc850'
    >>> format(datetime(2024, 1, 31, 23, 59, 0, tzinfo=timezone.utc))
    'Wed, 31 Jan 2024 23:59:00 GMT'
    >>> to_imf(datetime(2024, 1, 31, 23, 59, 0, tzinfo=timezone.utc))
    'Wed, 31 Jan 2024 23:59:00 GMT'

Why this package exists:

* ``email.utils.parsedate_tz`` returns a tuple (or silently ``None`` on
  failure) and has no dialect detection.
* ``httpdate`` on PyPI requires the ``leapseconds>=2023.4.0`` data
  table, which makes it unsuitable for Pyodide, Cloudflare Workers,
  AWS Lambda zip-deploy, and air-gapped CI.
* No existing zero-dep package ships a symmetric ``format(dt) -> str``
  helper that emits the literal ``"GMT"`` timezone marker.

This package is 100% Python standard library, MIT licensed, and
intentionally narrow in scope. See the README for full usage notes,
the limitations section, and the non-goals list.
"""

from __future__ import annotations

from ._format import format, to_imf
from ._parser import parse, parse_dialect
from .exceptions import InvalidFormat

__version__ = "0.1.0"

__all__ = [
    "parse",
    "parse_dialect",
    "format",
    "to_imf",
    "InvalidFormat",
    "__version__",
]