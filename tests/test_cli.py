"""Tests for the ``htdate-parse`` and ``htdate-format`` console scripts.

Maps to spec §5.3 acceptance criteria H (AC 48-55).
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from datetime import datetime, timezone

import pytest

from htdate_pure.cli import (
    EXIT_INPUT_ERROR,
    EXIT_OK,
    EXIT_USAGE,
    build_format_parser,
    build_parse_parser,
    main_format,
    main_parse,
)

from conftest import covers


# ---------------------------------------------------------------------------
# htdate-parse
# ---------------------------------------------------------------------------


@covers(48, "test_cli_parse_canonical")
def test_cli_parse_canonical(capsys):
    rc = main_parse(["Sun, 06 Nov 1994 08:49:37 GMT"])
    assert rc == EXIT_OK
    out = capsys.readouterr().out
    assert out == "1994-11-06T08:49:37+00:00\n"


@covers(49, "test_cli_parse_dialect_flag")
def test_cli_parse_dialect_flag(capsys):
    rc = main_parse(["--dialect", "Sun, 06 Nov 1994 08:49:37 GMT"])
    assert rc == EXIT_OK
    out = capsys.readouterr().out
    assert out == "imf\n"

    rc = main_parse(["--dialect", "Sunday, 06-Nov-94 08:49:37 GMT"])
    assert rc == EXIT_OK
    assert capsys.readouterr().out == "rfc850\n"

    rc = main_parse(["--dialect", "Sun Nov  6 08:49:37 1994"])
    assert rc == EXIT_OK
    assert capsys.readouterr().out == "asctime\n"


@covers(50, "test_cli_parse_garbage_exit_code")
def test_cli_parse_garbage_exit_code(capsys):
    rc = main_parse(["garbage"])
    assert rc == EXIT_INPUT_ERROR
    err = capsys.readouterr().err
    assert "no_matching_dialect" in err
    assert "garbage" in err


@covers(50, "test_cli_parse_empty_arg_uses_stdin_pipe")
def test_cli_parse_empty_arg_uses_stdin_pipe(capsys, monkeypatch):
    fake_stdin = io.StringIO("Sun, 06 Nov 1994 08:49:37 GMT\n")
    monkeypatch.setattr(sys, "stdin", fake_stdin)
    rc = main_parse([])
    assert rc == EXIT_OK
    out = capsys.readouterr().out
    assert out == "1994-11-06T08:49:37+00:00\n"


def test_cli_parse_tty_no_arg_uses_usage_error(monkeypatch):
    class FakeTTY(io.StringIO):
        def isatty(self) -> bool:
            return True
    monkeypatch.setattr(sys, "stdin", FakeTTY())
    rc = main_parse([])
    assert rc == EXIT_USAGE


@covers(50, "test_cli_parse_typo_exits_2")
def test_cli_parse_typo_exits_2(capsys):
    rc = main_parse(["Sun , 06 Nov 1994 08:49:37 GMT"])
    assert rc == EXIT_INPUT_ERROR


def test_cli_parse_version_flag(capsys):
    rc = main_parse(["--version"])
    # main_parse swallows SystemExit and returns its code as the rc.
    assert rc == 0
    assert "htdate-pure" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# htdate-format
# ---------------------------------------------------------------------------


@covers(51, "test_cli_format_now")
def test_cli_format_now(capsys):
    rc = main_format(["--now"])
    assert rc == EXIT_OK
    out = capsys.readouterr().out.strip()
    assert out.endswith(" GMT")
    assert len(out) == 29
    now = datetime.now(timezone.utc)
    expected_weekday = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][now.weekday()]
    assert out.startswith(expected_weekday)


@covers(52, "test_cli_format_d_with_offset")
def test_cli_format_d_with_offset(capsys):
    rc = main_format(["-d", "2024-01-31T23:59:00+00:00"])
    assert rc == EXIT_OK
    assert capsys.readouterr().out.strip() == "Wed, 31 Jan 2024 23:59:00 GMT"


@covers(53, "test_cli_format_d_naive_assume_utc")
def test_cli_format_d_naive_assume_utc(capsys):
    rc = main_format(["-d", "2024-01-31T23:59:00", "--assume-utc"])
    assert rc == EXIT_OK
    assert capsys.readouterr().out.strip() == "Wed, 31 Jan 2024 23:59:00 GMT"


def test_cli_format_d_naive_without_assume_utc_errors(capsys):
    rc = main_format(["-d", "2024-01-31T23:59:00"])
    assert rc != 0


@covers(54, "test_cli_format_no_args_usage_error")
def test_cli_format_no_args_usage_error(capsys):
    rc = main_format([])
    assert rc == EXIT_USAGE
    err = capsys.readouterr().err
    assert "one of" in err or "required" in err.lower()


@covers(55, "test_cli_format_d_with_non_utc_rejected")
def test_cli_format_d_with_non_utc_rejected(capsys):
    rc = main_format(["-d", "2024-01-31T23:59:00+05:00"])
    assert rc == EXIT_INPUT_ERROR
    err = capsys.readouterr().err
    assert "tzinfo" in err or "UTC" in err


def test_cli_format_unix(capsys):
    rc = main_format(["-u", "1700000000"])
    assert rc == EXIT_OK


def test_cli_format_unix_invalid(capsys):
    # Non-numeric unix value: argparse rejects at parse-time with exit
    # code 2. main_format swallows SystemExit and returns that code.
    rc = main_format(["-u", "not-a-number"])
    assert rc == 2


def test_cli_format_mutex_flags(capsys):
    rc = main_format(["--now", "-d", "2024-01-31T23:59:00+00:00"])
    assert rc == EXIT_USAGE


def test_cli_format_version_flag(capsys):
    rc = main_format(["--version"])
    assert rc == 0
    assert "htdate-pure" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Console-script smoke (only when installed, not in CI without install)
# ---------------------------------------------------------------------------


def _scripts_installed() -> bool:
    """Return True if the console scripts are on PATH."""
    from shutil import which
    return which("htdate-parse") is not None and which("htdate-format") is not None


@pytest.mark.skipif(
    not _scripts_installed(),
    reason="console scripts not installed in this environment",
)
def test_console_script_htdate_parse_runs():
    proc = subprocess.run(
        ["htdate-parse", "Sun, 06 Nov 1994 08:49:37 GMT"],
        capture_output=True, text=True, timeout=10,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "1994-11-06T08:49:37+00:00"


@pytest.mark.skipif(
    not _scripts_installed(),
    reason="console scripts not installed in this environment",
)
def test_console_script_htdate_format_runs():
    proc = subprocess.run(
        ["htdate-format", "-d", "2024-01-31T23:59:00+00:00"],
        capture_output=True, text=True, timeout=10,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "Wed, 31 Jan 2024 23:59:00 GMT"


# ---------------------------------------------------------------------------
# Parser builders
# ---------------------------------------------------------------------------


def test_parse_parser_has_version_flag():
    p = build_parse_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["--version"])


def test_format_parser_has_version_flag():
    p = build_format_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["--version"])