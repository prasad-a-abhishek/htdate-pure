"""CLI entry points for htdate-pure.

Two console scripts are registered in ``pyproject.toml``:

* ``htdate-parse``  — parse an HTTP-date header (stdin or argv).
* ``htdate-format`` — emit an IMF-fixdate string for ``--now``, ``-d``,
  or ``-u``.

Exit codes follow the standard convention:

* ``0`` — success
* ``2`` — parse / format error (InputException)
* ``64`` — usage error (CommandLineError, matches ``sysexits.h`` EX_USAGE)

Reading from stdin is supported on both CLIs so callers can do
``echo 'Sun, 06 Nov 1994 16:00:00 GMT' | htdate-parse``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from . import __version__, format, parse, parse_dialect
from .exceptions import InvalidFormat

__all__ = [
    "main_parse",
    "main_format",
    "build_parse_parser",
    "build_format_parser",
]


# Exit codes — kept as module-level constants so tests can pin behaviour.
EXIT_OK = 0
EXIT_INPUT_ERROR = 2   # parse / format error
EXIT_USAGE = 64        # usage error


# ---------------------------------------------------------------------------
# Argument parser builders
# ---------------------------------------------------------------------------


def build_parse_parser() -> argparse.ArgumentParser:
    """Build the ``htdate-parse`` argument parser.

    Exposed so tests can introspect the parser without invoking
    ``main_parse``.
    """
    p = argparse.ArgumentParser(
        prog="htdate-parse",
        description=(
            "Parse an HTTP-date header (RFC 9110 §5.1.1) and emit an "
            "ISO-8601 timestamp. Reads from argv or stdin."
        ),
    )
    p.add_argument(
        "header",
        nargs="?",
        default=None,
        help="HTTP-date header value (e.g. 'Sun, 06 Nov 1994 16:00:00 GMT'). "
             "If omitted, read from stdin.",
    )
    p.add_argument(
        "--dialect",
        action="store_true",
        help="Print the detected dialect ('imf', 'rfc850', 'asctime') instead of the parsed timestamp.",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"htdate-pure {__version__}",
    )
    return p


def build_format_parser() -> argparse.ArgumentParser:
    """Build the ``htdate-format`` argument parser."""
    p = argparse.ArgumentParser(
        prog="htdate-format",
        description=(
            "Emit an IMF-fixdate HTTP-date string. Use --now for current "
            "time, -d for an explicit ISO-8601 input, or -u for a Unix "
            "epoch timestamp."
        ),
    )
    p.add_argument(
        "-d", "--datetime",
        dest="datetime_str",
        default=None,
        help="ISO-8601 datetime to format (e.g. '2024-01-31T23:59:00+00:00').",
    )
    p.add_argument(
        "-u", "--unix",
        dest="unix",
        type=int,
        default=None,
        help="Unix epoch timestamp (seconds since 1970-01-01 UTC).",
    )
    p.add_argument(
        "--now",
        action="store_true",
        help="Emit the current UTC time as IMF-fixdate.",
    )
    p.add_argument(
        "--assume-utc",
        action="store_true",
        help="When formatting a naive -d input, treat it as UTC.",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"htdate-pure {__version__}",
    )
    return p


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_stdin_or_argv(arg_value: str | None) -> str:
    """Return ``arg_value`` if given, else read one line from stdin.

    If stdin is a TTY (no pipe) and no arg was supplied, we treat that
    as a usage error rather than blocking on stdin. This matches
    GNU/POSIX conventions for ``cat``-style readers.
    """
    if arg_value is not None:
        return arg_value
    if sys.stdin.isatty():
        raise SystemExit(EXIT_USAGE)  # no arg, no stdin -> usage error
    data = sys.stdin.read()
    # Accept a trailing newline gracefully.
    if data.endswith("\n"):
        data = data[:-1]
    if data.endswith("\r"):
        data = data[:-1]
    return data


def _parse_iso8601(text: str, *, assume_utc: bool) -> datetime:
    """Parse an ISO-8601 datetime for the ``htdate-format -d`` flag.

    Supports the common Python ``datetime.fromisoformat`` shapes plus
    a trailing ``Z``. Naive inputs require ``assume_utc=True``; the
    rest are passed through with whatever offset the user supplied.
    """
    s = text.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as exc:
        raise SystemExit(
            f"{__file__}: invalid ISO-8601 input: {text!r}: {exc}"
        ) from exc
    if dt.tzinfo is None and not assume_utc:
        raise SystemExit(
            f"{__file__}: naive ISO-8601 input requires --assume-utc (got {text!r})"
        )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def main_parse(argv: list[str] | None = None) -> int:
    """Entry point for the ``htdate-parse`` console script.

    Returns the exit code (so tests can assert against it) rather than
    calling :func:`sys.exit` directly except in the documented stdin /
    usage paths.
    """
    parser = build_parse_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse already called sys.exit on usage error; surface the
        # code so the calling harness can observe it.
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE

    try:
        header = _read_stdin_or_argv(args.header)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE

    if args.dialect:
        d = parse_dialect(header)
        if d is None:
            print(
                f"InvalidFormat: {header!r}: no_matching_dialect",
                file=sys.stderr,
            )
            return EXIT_INPUT_ERROR
        print(d)
        return EXIT_OK

    try:
        dt = parse(header)
    except InvalidFormat as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INPUT_ERROR

    # ISO-8601 with explicit UTC offset (AC 48).
    print(dt.isoformat())
    return EXIT_OK


def main_format(argv: list[str] | None = None) -> int:
    """Entry point for the ``htdate-format`` console script."""
    parser = build_format_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE

    sources = sum(bool(x) for x in (args.now, args.datetime_str, args.unix is not None))
    if sources == 0:
        parser.print_usage(sys.stderr)
        print(
            f"{parser.prog}: error: one of --now / -d / -u is required",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if sources > 1:
        parser.print_usage(sys.stderr)
        print(
            f"{parser.prog}: error: --now / -d / -u are mutually exclusive",
            file=sys.stderr,
        )
        return EXIT_USAGE

    try:
        if args.now:
            dt = datetime.now(timezone.utc)
        elif args.datetime_str is not None:
            dt = _parse_iso8601(args.datetime_str, assume_utc=args.assume_utc)
        else:
            # args.unix is not None
            dt = datetime.fromtimestamp(int(args.unix), tz=timezone.utc)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
    except (ValueError, OverflowError, OSError) as exc:
        print(f"{parser.prog}: invalid input: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    try:
        out = format(dt)
    except ValueError as exc:
        print(f"{parser.prog}: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    print(out)
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover — dispatched via console_scripts
    # Pick the entry point based on argv[0].
    if sys.argv and "format" in sys.argv[0]:
        raise SystemExit(main_format())
    raise SystemExit(main_parse())