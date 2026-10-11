# htdate-pure

![](https://img.shields.io/badge/version-0.1.0-blue) ![](https://img.shields.io/badge/license-MIT-green) ![](https://img.shields.io/badge/python-3.11+-blue) ![](https://img.shields.io/badge/dependencies-zero-brightgreen)

**Zero-dependency HTTP-date parser/serializer for Python 3.11+ — handles IMF-fixdate, RFC 850, and asctime (RFC 9110 §5.1.1) with no stdlib hijacking and zero runtime deps.**

## Quick Start

```bash
pip install -e .          # install from a local clone (not yet on PyPI)
```

```python
from htdate_pure import parse, format

dt = parse("Sun, 06 Nov 1994 08:49:37 GMT")   # IMF-fixdate (RFC 9110 §5.1.1)
print(format(dt))                            # 'Sun, 06 Nov 1994 08:49:37 GMT'
```

## ⚡ Performance & Benchmarks

Head-to-head comparison of `htdate-pure` (zero-dep, pure stdlib) vs the
PyPI-leading [`httpdate`](https://pypi.org/project/httpdate/) (which
transitively requires `leapseconds>=2023.4.0` — a data table dependency).
Benchmark scope is intentionally narrow: HTTP-date parse + format, 5
iterations per workload after 3-iteration warmup, microseconds per call,
peak memory via `tracemalloc`.

| Workload              | Tool           | Mean (us/call) | P95 (us/call) | Peak (KB) | Iterations |
|-----------------------|----------------|---------------:|--------------:|----------:|-----------:|
| single_imf_parse      | htdate-pure    |          22.53 |         22.33 |       2.9 |          5 |
| single_imf_parse      | httpdate       |       10361.85 |      10467.58 |       1.0 |          5 |
| single_imf_format     | htdate-pure    |          10.53 |         10.96 |       0.8 |          5 |
| single_imf_format     | httpdate       |        9825.82 |      10018.00 |       1.0 |          5 |
| batch_1k_parse_imf    | htdate-pure    |          13.02 |         13.07 |       0.6 |          5 |
| batch_1k_parse_imf    | httpdate       |          15.00 |         14.99 |       0.9 |          5 |
| batch_1k_format       | htdate-pure    |           8.94 |          9.01 |       2.0 |          5 |
| batch_1k_format       | httpdate       |          12.93 |         13.05 |       1.0 |          5 |
| mixed_dialects_1k     | htdate-pure    |          12.85 |         12.90 |       0.6 |          5 |
| mixed_dialects_1k     | httpdate       |          15.07 |         15.14 |       0.9 |          5 |

Reproduce locally:

```bash
pip install -e .
python3 benchmarks/run_benchmark.py
```

The bootstrap script auto-creates `benchmarks/.venv_competitor` with
`httpdate` + `leapseconds` installed (via `uv` if available, else stdlib
`venv` + `pip`). The full table is regenerated into
`benchmarks/BENCHMARK.md` on each run.

## Why `htdate-pure`? (Problem & Trade-Off Statement)

The HTTP-date problem is small on the surface but surprisingly thorny in
practice. Three options exist today and none is fully satisfactory:

- **`httpdate` on PyPI** (https://pypi.org/project/httpdate/) — the
  closest functional match, but it pulls in `leapseconds>=2023.4.0`, an
  IERS leap-second data table re-distributed as a wheel. That single
  transitive dependency breaks four real deployment targets:
  Pyodide (cannot `pip install` binary wheels with C extensions during
  worker boot), Cloudflare Workers (no `pip` at all), AWS Lambda zip
  deploys constrained to pure-Python wheels, and air-gapped CI runners
  with no PyPI egress.
- **stdlib `email.utils.parsedate_tz`** — present in every Python and a
  natural first guess, but only handles IMF-fixdate (drops RFC 850 and
  asctime silently), returns a 9-tuple (not a `datetime`), drops
  sub-second precision entirely, and accepts out-of-range values
  (month=13, day=99) without raising — it just rolls them over.
- **`time.strptime` + `calendar.timegm`** — handles all 3 formats if you
  hand-format the right `strptime` strings, but locale dependence makes
  it brittle, and there is no `format()` inverse for IMF-fixdate output.

`htdate-pure` covers all three RFC 9110 §5.1.1 formats, raises a typed
`InvalidFormat` exception (with a stable `.reason` token describing the
failure class) on every malformed input, uses only `re` + `datetime` +
`calendar` from the standard library, ships a symmetric `format()` that
always emits IMF-fixdate, and exposes CLIs that match the lib API. The
trade-off is honest: we re-implement ~150 lines of date arithmetic that
`httpdate` gets from `leapseconds`, and our leap-second policy is to
clamp `:60` to `:59` with a warning rather than tracking the IERS table.
Users who need strict IERS-tracked leap-second support and can tolerate
a binary data table dep should still pick `httpdate`.

## Key Features & Complete API / CLI Reference

- All three RFC 9110 §5.1.1 formats: IMF-fixdate, RFC 850 (obs-date),
  asctime
- Auto-detects input dialect via `parse_dialect()` (returns the format
  name alongside the parsed value)
- Handles dates before 1970 (full year range supported by `datetime`)
- Leap-second `:60` is detected via `is_leap_second()` and clamps to
  `:59` with a `RuntimeWarning`
- Strict range validation: month 1-12, day 1-31 (with month-aware day
  limits), hour 0-23, minute 0-59, second 0-60, timezone +0000 only
  (per RFC 9110 — "GMT" / "UT" are accepted as aliases)
- 270 tests across 12 files covering happy path, canonical vectors,
  pre-1970, leap seconds, fuzz surfaces, dialect detection, typo
  rejection, roundtrip, packaging, CLI, and format-specific edge cases

### Public API

```python
from htdate_pure import (
    parse,            # parse any of the 3 HTTP-date formats
    format,           # emit IMF-fixdate (always)
    to_imf,           # alias of format() — clearer name at call sites
    parse_dialect,    # detect which of the 3 formats matched -> "imf" | "rfc850" | "asctime" | None
    is_leap_second,   # True if the seconds field was :60
    InvalidFormat,    # raised on shape / pattern / range errors (subclass of ValueError)
)
```

**Library usage**

```python
from htdate_pure import parse, format, parse_dialect

# IMF-fixdate
dt = parse("Sun, 06 Nov 1994 08:49:37 GMT")
format(dt)                       # 'Sun, 06 Nov 1994 08:49:37 GMT'

# RFC 850 (obs-date) — parse_dialect returns the dialect name (str | None),
# NOT a (dt, dialect) tuple. Call parse() to get the datetime.
dialect = parse_dialect("Sunday, 06-Nov-94 08:49:37 GMT")
assert dialect == "rfc850"

# asctime
dialect = parse_dialect("Sun Nov  6 08:49:37 1994")
assert dialect == "asctime"

# Unknown input -> None (no exception raised)
assert parse_dialect("not a date at all") is None

# Pre-1970
parse("Fri, 31 Dec 1909 12:00:00 GMT")   # 1909-12-31 12:00:00+00:00
```

### CLI

```bash
# Parse a date string and emit ISO 8601
htdate-parse "Sun, 06 Nov 1994 08:49:37 GMT"
# → 1994-11-06T08:49:37+00:00

# Auto-detect dialect
htdate-parse --dialect "Sunday, 06-Nov-94 08:49:37 GMT"
# → rfc850 → 1994-11-06T08:49:37+00:00

# Format a datetime as IMF-fixdate
htdate-format -d datetime 2024-01-15T10:30:00
# → 'Mon, 15 Jan 2024 10:30:00 GMT'

htdate-format -d today
# → today's date in IMF-fixdate format
```

### Errors

The package raises a single typed exception, `InvalidFormat`, on every
malformed input. It is also a subclass of `ValueError` so existing
callers that catch `ValueError` continue to work without modification.

| Failure mode (RFC 9110 §5.1.1)           | `InvalidFormat.reason` token        |
|------------------------------------------|-------------------------------------|
| shape does not match any of the 3 formats | `no_matching_dialect`               |
| weekday name does not match the date     | `weekday_mismatch`                  |
| month is not 01-12                       | `month_out_of_range`                |
| day outside the month's valid range      | `day_out_of_range_for_month`        |
| day is non-numeric / out of 01-31        | `day_out_of_range`                  |
| hour / minute / second out of range      | `hour_out_of_range` / `_minute_` / `_second_` |
| year outside 1900-2099                   | `year_out_of_range`                 |
| 3-letter month abbreviation not in table | `invalid_month_name`                |
| weekday name not Sun-Sat                 | `invalid_weekday_name`              |
| timezone designator is not GMT / UT      | `invalid_timezone_literal`          |
| missing timezone designator              | `missing_timezone`                  |
| input is `None`, not a `str`, or empty   | `type_error` / `empty`              |

`InvalidFormat` exposes `.value` (the original input, unaltered) and
`.reason` (the stable machine-readable token from the table above) so
callers can react programmatically:

```python
from htdate_pure import parse, InvalidFormat

try:
    parse("Mon, 06 Nov 1994 08:49:37 GMT")  # Mon is wrong — 06 Nov 1994 was Sun
except InvalidFormat as exc:
    assert exc.reason == "weekday_mismatch"
    assert exc.value == "Mon, 06 Nov 1994 08:49:37 GMT"
```

All public functions are exception-safe: malformed inputs, `None`,
empty strings, oversized payloads, and unclosed brackets never raise
`TypeError` or `AttributeError` — they raise `InvalidFormat`
(equivalently `ValueError`) so callers can `try / except InvalidFormat`
cleanly.

## License

MIT — Copyright (c) Abhishek Prasad. See [`LICENSE`](./LICENSE) for the
full text.
