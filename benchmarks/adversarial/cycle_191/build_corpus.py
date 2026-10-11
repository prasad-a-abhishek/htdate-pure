"""Build seed corpus for cycle_191/adversary T03.

For each harness we materialize ≥20 distinct JSON seed files at
benchmarks/adversarial/cycle_191/corpus/<harness>_seeds/seed_<NNN>.json

The harnesses themselves also carry an internal SEED_CORPUS, but the
T03 spec asks for an explicit on-disk corpus so the mutation run is
reproducible from the committed JSON and so the orchestrator's
downstream card (T04 triage) can re-run a minimized crash file from
disk without re-running the entire 100K iteration loop.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone

ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "corpus",
)


def _write(harness: str, idx: int, payload) -> str:
    sub = os.path.join(ROOT, f"{harness}_seeds")
    os.makedirs(sub, exist_ok=True)
    path = os.path.join(sub, f"seed_{idx:03d}.json")
    # Store a normalized representation. Strings → str; bytes → base64
    # so JSON serialization round-trips without forcing utf-8 lossy decode.
    if isinstance(payload, (bytes, bytearray)):
        body = {"_encoding": "base64", "input": base64.b64encode(bytes(payload)).decode("ascii")}
    elif isinstance(payload, str):
        body = {"_encoding": "str", "input": payload}
    elif isinstance(payload, datetime):
        # Naive datetimes need no tz info; aware datetimes beyond
        # ±24h offsets fail isoformat() — fall back to (year, tzinfo.__repr__)
        try:
            iso = payload.isoformat()
        except ValueError:
            iso = None
        body = {
            "_encoding": "datetime",
            "iso": iso,
            "tz_utc": payload.tzinfo is timezone.utc,
            "tz_naive": payload.tzinfo is None,
            "leap_second": payload.second == 60,
        }
        if iso is None:
            body["tz_repr"] = repr(payload.tzinfo)
    elif isinstance(payload, list) and all(isinstance(x, str) for x in payload):
        body = {"_encoding": "argv", "argv": payload}
    elif isinstance(payload, (int, float, type(None))):
        body = {"_encoding": "raw", "input": payload}
    else:
        # Object() / arbitrary class instances → tag with type, no payload
        body = {"_encoding": "raw", "input": f"<{type(payload).__name__}>"}
    with open(path, "w") as f:
        json.dump(body, f, indent=2)
    return path


def build_parse_corpus() -> list[str]:
    seeds: list[object] = [
        # ----- IMF-fixdate variants (RFC 9110 §5.1.1) -----
        "Sun, 06 Nov 1994 08:49:37 GMT",
        "Mon, 06 Nov 1994 08:49:37 GMT",  # wrong weekday for date
        "Sun, 06 Nov 1994 08:49:60 GMT",  # leap second
        "Sun, 06 Nov 1994 08:49:37 -0500",  # numeric offset (reject)
        "Sun, 06 Nov 1994 08:49:37 UTC",  # wrong tz literal
        "sun, 06 Nov 1994 08:49:37 GMT",  # wrong case
        "Sun, 6 Nov 1994 08:49:37 GMT",  # single-digit day
        "Sun, 06 Nnv 1994 08:49:37 GMT",  # typo month
        "Sun, 32 Nov 1994 08:49:37 GMT",  # day out of range
        "Sun, 06 Nov 1994 25:00:00 GMT",  # hour out of range
        "Sun, 06 Nov 1994 08:61:00 GMT",  # minute out of range
        "Sun, 06 Nov 1994 08:49:61 GMT",  # second out of range
        "Sun, 06 Nov 1899 08:49:37 GMT",  # year too low
        "Sun, 06 Nov 2100 08:49:37 GMT",  # year too high
        # ----- RFC 850 variants -----
        "Sunday, 06-Nov-94 08:49:37 GMT",
        "Monday, 01-Jan-00 00:00:00 GMT",
        "Wednesday, 29-Feb-00 12:00:00 GMT",  # leap
        "Tuesday, 29-Feb-01 12:00:00 GMT",  # non-leap, reject
        # ----- asctime variants -----
        "Sun Nov  6 08:49:37 1994",
        "Sun Nov  6 08:49:60 1994",  # leap
        # ----- Pathological -----
        "",
        " ",
        "\x1b[31mSun, 06 Nov 1994 08:49:37 GMT",  # ANSI escape
        "\x00Sun, 06 Nov 1994 08:49:37 GMT",  # leading NUL
        "Sun, 06 Nov 1994 08:49:37 GMT\x00",  # trailing NUL
        "not a date at all",
        "99X 99X 99 99:99:99 GMT",
        "Sun,\u00a006 Nov 1994 08:49:37 GMT",  # NBSP
        "Sūn, 06 Nov 1994 08:49:37 GMT",  # accented weekday
        # ----- very long / adversarial -----
        "G" * 4096,
        "a" * 65536,
        "Sun, 06 Nov 1994 08:49:37 GMT" + " " * 1000,
        # ----- regex backtracking pattern (re-tests catastrophic regex) -----
        "((((((((((((((((((a+)+)+)+)+)+)+)+)+)+)+)+)+)+)+)+)+)!",
        # ----- bytes / type edges -----
        b"\xff\xfe\xfd",
        b"Sun, 06 Nov 1994 08:49:37 GMT",
        None,
        42,
        3.14,
        object(),
        ["Sun, 06 Nov 1994 08:49:37 GMT"],
    ]
    paths = []
    for i, s in enumerate(seeds):
        paths.append(_write("parse", i, s))
    return paths


def build_format_corpus() -> list[str]:
    seeds: list[datetime] = []
    # ----- year boundaries -----
    seeds.append(datetime(1, 1, 1, 0, 0, 0, tzinfo=timezone.utc))  # year=1
    seeds.append(datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc))  # year=9999
    # ----- leap-day (2000 was leap, 1900 was not) -----
    seeds.append(datetime(2000, 2, 29, 12, 0, 0, tzinfo=timezone.utc))
    seeds.append(datetime(2024, 2, 29, 12, 0, 0, tzinfo=timezone.utc))
    # ----- leap-second rebound (next-minute-zero with leap flag) -----
    seeds.append(datetime(1994, 11, 6, 8, 50, 0, tzinfo=timezone.utc) - timedelta(seconds=60))
    seeds[-1] = seeds[-1].replace(fold=0)
    # ----- microsecond boundaries -----
    seeds.append(datetime(2024, 1, 31, 23, 59, 0, 0, tzinfo=timezone.utc))
    seeds.append(datetime(2024, 1, 31, 23, 59, 0, 999999, tzinfo=timezone.utc))
    # ----- hour=23 / minute=59 / second=60 (leap second equivalent) -----
    seeds.append(datetime(2024, 1, 31, 23, 59, 0, tzinfo=timezone.utc))
    leap_eq = datetime(2024, 2, 1, 0, 0, 0, tzinfo=timezone.utc) - timedelta(seconds=60)
    seeds.append(leap_eq)
    # ----- timezone-aware + fixed offset: UTC, +14h, -12h, +99h (out of range) -----
    from datetime import tzinfo

    class _FO(tzinfo):
        def __init__(self, m):
            self._m = m

        def utcoffset(self, dt):
            return timedelta(minutes=self._m)

        def dst(self, dt):
            return timedelta(0)

        def tzname(self, dt):
            return f"UTC{self._m // 60:+d}:00"

    for off_minutes, _name in [
        (0, "UTC"),
        (14 * 60, "+14h"),
        (-12 * 60, "-12h"),
        (99 * 60, "+99h (rejected)"),
    ]:
        seeds.append(datetime(2024, 1, 31, 23, 59, 0, tzinfo=_FO(off_minutes)))
    # ----- naive (UTC assumed) -----
    seeds.append(datetime(2024, 1, 31, 23, 59, 0))
    # ----- microsecond = 1 (very small but valid) -----
    seeds.append(datetime(2024, 1, 31, 23, 59, 0, 1, tzinfo=timezone.utc))
    # ----- additional corner cases for breadth -----
    seeds.append(datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc))  # epoch
    seeds.append(datetime(2000, 1, 1, 0, 0, 0, tzinfo=timezone.utc))  # Y2K
    seeds.append(datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc))  # RFC example
    seeds.append(datetime(2024, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc))  # year-end max us
    seeds.append(datetime(1, 1, 1, 0, 0, 0, tzinfo=timezone.utc))  # year=1 (lower bound)
    seeds.append(datetime(1900, 2, 28, 23, 59, 59, tzinfo=timezone.utc))  # non-leap feb 28
    seeds.append(datetime(1900, 3, 1, 0, 0, 0, tzinfo=timezone.utc))  # non-leap day after feb
    seeds.append(datetime(2024, 6, 15, 12, 30, 45, 123456, tzinfo=timezone.utc))  # random middle
    # ----- non-UTC fixed offsets at various minutes -----
    for off in (5, 30, 60, 330, 480, 600, 720, -300, -480):
        seeds.append(datetime(2024, 6, 15, 12, 30, 45, tzinfo=_FO(off)))
    paths = []
    for i, dt in enumerate(seeds):
        paths.append(_write("format", i, dt))
    return paths


def build_cli_corpus() -> list[str]:
    seeds: list[list[str]] = [
        # ----- htdate-parse argv variants -----
        ["htdate-parse"],  # stdin-only
        ["htdate-parse", "Sun, 06 Nov 1994 08:49:37 GMT"],
        ["htdate-parse", "--dialect", "imf"],
        ["htdate-parse", "--dialect=imf", "Sun, 06 Nov 1994 08:49:37 GMT"],
        ["htdate-parse", "--dialect=rfc850", "Sunday, 06-Nov-94 08:49:37 GMT"],
        ["htdate-parse", "--version"],
        ["htdate-parse", "--help"],
        ["htdate-parse", "--unknown-flag"],
        ["htdate-parse", "--dialect=invalid_value"],
        ["htdate-parse", ""],
        ["htdate-parse", "\\x00garbage"],
        ["htdate-parse", "-d"],
        # ----- htdate-format argv variants -----
        ["htdate-format", "--now"],
        ["htdate-format", "-d", "2024-01-31T23:59:00+00:00"],
        ["htdate-format", "-d", ""],
        ["htdate-format", "-d", "\\x00garbage"],
        ["htdate-format", "-u", "0"],
        ["htdate-format", "-u", "1234567890"],
        ["htdate-format", "-u", str(2 ** 99)],
        ["htdate-format", "--assume-utc", "--now"],
        ["htdate-format", "--version"],
        ["htdate-format", "--help"],
        ["htdate-format"],  # usage error
        ["htdate-format", "--garbage-flag"],
        ["htdate-format", "-d", "2024-01-31T23:59:60Z"],
        # ----- 1MB positional (very long arg) -----
        ["htdate-parse", "A" * 1024],
    ]
    paths = []
    for i, argv in enumerate(seeds):
        paths.append(_write("cli", i, argv))
    return paths


def main() -> None:
    parse_paths = build_parse_corpus()
    format_paths = build_format_corpus()
    cli_paths = build_cli_corpus()
    print(f"parse_seeds:   {len(parse_paths)} files")
    print(f"format_seeds:  {len(format_paths)} files")
    print(f"cli_seeds:     {len(cli_paths)} files")
    print(f"total:         {len(parse_paths) + len(format_paths) + len(cli_paths)} files")
    print(f"corpus root:   {ROOT}")


if __name__ == "__main__":
    main()