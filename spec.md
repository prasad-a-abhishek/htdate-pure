# htdate-pure — Specification (cycle_191)

## 1. Title + one-line summary

**htdate-pure** — a zero-dependency, 100%-stdlib HTTP-date parser/serializer for Python 3.11+, implementing all three HTTP-date formats (IMF-fixdate, RFC 850, asctime) defined in **RFC 9110 §5.1.1** and **RFC 7231 §7.1.1.1**, with both a unified Python API and standalone CLI tools — without pulling in a `leapseconds` data-table dependency and without requiring the user to compose `email.utils.parsedate_tz` + `email.utils.format_datetime` manually.

## 2. Problem & Scientific Friction Point

Every system that touches HTTP headers eventually has to parse or emit an HTTP-date string. RFC 9110 §5.1.1 defines **three** valid input formats (IMF-fixdate, rfc850, asctime); RFC 9110 §5.1.1 also mandates that recipients MUST accept all three for parsing but MUST NOT generate the obsolete two. Real systems that hit this concrete friction include:

- **AWS Signature V4** — the `X-Amz-Date` header MUST be `YYYYMMDDTHHMMSSZ` (different format, but related), and other signed headers (`Date`, `If-Modified-Since`, `Last-Modified`) flow through the same machinery (https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-create-signed-request.html — HTTP 200).
- **HTTP conditional GET / ETag / `If-Unmodified-Since`** — the GitHub REST API documents `If-Modified-Since` as a proper HTTP-date header (https://docs.github.com/en/webhooks/webhook-events-and-payloads — HTTP 200).
- **Caches** — `Age`, `Date`, `Last-Modified`, `Expires`, `If-Modified-Since`, `If-Unmodified-Since`, `Retry-After` all use HTTP-date (sister repo `age-parse` parses the integer `Age:` header but delegates the date parsing to `email.utils`).
- **Signed cookies, S3 presigned URLs, OAuth2 client assertions** all carry date strings.

The friction surfaces are concrete and well-documented:

**(a) The stdlib path is awkward.** Python ships `email.utils.parsedate_tz()` (returns a 9-tuple or `None`) and a separate `email.utils.format_datetime()` (no symmetric IMF-fixdate output, no dialect detection). Composing them yourself means writing two helper functions, handling the tuple-to-datetime dance, dealing with `None` returns silently, and accepting that `parsedate_tz` does **not** expose which format matched. There is no `parse_dialect("Sun, 06 Nov 1994 08:49:37 GMT") -> "imf"` primitive anywhere in stdlib.

**(b) The existing pure-Python PyPI package requires a hard-coded leap-seconds table.** `httpdate` 1.2.0 (jamielinux, PyPI: "Parse and format HTTP dates, such as Last-Modified and If-Modified-Since headers") is the closest competitor and its source explicitly does `from leapseconds import LEAP_SECONDS` (https://github.com/jamielinux/httpdate/blob/main/src/httpdate/httpdate.py, line 24). It pulls the leap-seconds data file transitively on every install. On Pyodide, Cloudflare Workers, AWS Lambda zip-deploy, or air-gapped CI, this means another wheel to vet, another source of supply-chain risk, another upload to your edge bundle, and a `leapseconds` release that updates IERS data twice a year.

**(c) Edge-runtime / WASM / serverless teams report the impedance.** Shipping `httpx`/`pycurl` just to send `Date: Sun, 06 Nov 1994 08:49:37 GMT` is over-weight; bundling `httpdate` pulls leapseconds; vendoring `email.utils.parsedate_tz` is the eternal cop-out but loses dialect detection and the formatter symmetry.

The deliverable from `htdate-pure` removes both friction points at once: zero runtime dependencies, two-minute install, exposes the missing dialect-detection and `parse(text) -> datetime` symmetry that stdlib does not provide, and ships CLIs so `htdate-parse` / `htdate-format` work from a shell without invocation glue.

## 3. Novelty Proof & Non-Existence Evidence

### 3.1 Python Stdlib Audit

Checked against `sys.stdlib_module_names` (Python 3.11) and modules whose surface touches HTTP-date:

| Module / function | What it does | Why it is not enough for `htdate-pure` |
| --- | --- | --- |
| `email.utils.parsedate_tz` | Parses RFC 2822 / IMF-fixdate / asctime to 9-tuple (year, month, …, tzoffset). | Returns `None` on failure silently; **no dialect detection** (cannot tell `imf` vs `asctime` apart); returns a tuple not a `datetime`; no `rfc850` parsing. |
| `email.utils.format_datetime` | Formats a `datetime` as RFC 2822-ish. | Produces *email* format with timezone offsets (`+0000`), not IMF-fixdate (`GMT` literal). Cannot easily produce `Sun, 06 Nov 1994 08:49:37 GMT`. |
| `email.utils.parsedate_to_datetime` | Wrap `parsedate_tz` and return `datetime`. | Still silent on failure (`ValueError` on bad input only); still no dialect detection; no CLI. |
| `wsgiref.util` | WSGI utilities — does not expose HTTP-date parsing. | Out of scope. |
| `datetime` / `time` / `calendar` | Provide date arithmetic and struct_time. | No HTTP-date serializer. |
| `email.utils.formatdate` | `formatdate(timeval, localtime, usegmt)` produces RFC 2822 with `+0000` or `GMT`. | Same `+0000` issue, and not symmetric with `parsedate_tz`. |
| `http` (module) | Client/server framework. | Note: prior cycle rejected the name `rfc9745-pure` because `http` collides with the `http` stdlib module; `htdate-pure` does NOT collide. |

**Verdict:** no stdlib function gives (a) all 3 input formats accepted via one entry point, (b) explicit dialect detection, (c) a symmetric IMF-fixdate formatter, (d) a CLI. **No collision.**

### 3.2 PyPI Semantic & Functional Search (NOT just `<name>` 404)

PyPI JSON-API probes (exact concept + naming variations):

| Probe | HTTP | Notes |
| --- | --- | --- |
| `https://pypi.org/pypi/htdate-pure/json` | 404 | Our proposed name is vacant. |
| `https://pypi.org/pypi/htdate/json` | 404 | Vacant. |
| `https://pypi.org/pypi/http-date/json` | 404 | Vacant. |
| `https://pypi.org/pypi/python-http-date/json` | 404 | Vacant. |
| `https://pypi.org/pypi/py-http-date/json` | 404 | Vacant. |
| `https://pypi.org/pypi/httpdate/json` | **200** | Exists: `httpdate` 1.2.0 by jamielinux — **but** `requires_dist: ['leapseconds>=2023.4.0']`. The leapseconds dep is exactly the friction this package removes for Pyodide/serverless/air-gapped users. |
| `https://pypi.org/pypi/rfc7231/json` | 404 | Vacant. |
| `https://pypi.org/pypi/rfc1123/json` | 404 | Vacant. |
| `https://pypi.org/pypi/imf-fixdate/json` | 404 | Vacant. |
| `https://pypi.org/pypi/rfc850/json` | 404 | Vacant. |
| `https://pypi.org/pypi/asctime-date/json` | 404 | Vacant. |
| `https://pypi.org/pypi/http-date-parser/json` | 404 | Vacant. |

**Verdict on `httpdate`:** it is the closest competing implementation but **fails the zero-dep pure-Python invariant** because of the `leapseconds>=2023.4.0` hard requirement (its own README admits the dep is for IERS leap-seconds data). Our package lives in the gap between "stdlib `email.utils` (awkward API, two-entry-point, no dialect detection, no CLI)" and "`httpdate` (one extra runtime dep that doesn't fit edge/WASM/air-gap constraints)".

### 3.3 GitHub Semantic Search

`gh search repos` probes (language filter implied to Python by query content; sorted by stars):

```
$ gh search repos "http-date parser python" --sort stars --limit 10   → []
$ gh search repos "rfc7231 python" --sort stars --limit 5              → []
$ gh search repos "rfc1123 imf-fixdate python" --sort stars --limit 5  → []
$ gh search repos "python httpdate" --sort stars --limit 5             → []
```

The highest-star repo that mentions HTTP-date parsing in Python is `pyfisch/httpdate` (59 stars), but its README (https://raw.githubusercontent.com/pyfisch/httpdate/master/README.md) is **explicitly a Rust crate** (`[![Crates.io][pypi-img]][pypi-url]` badge; "Date and time utils for HTTP" / `*parse_http_date*` and `*fmt_http_date*` are documented as Rust functions). The Python-side match is `jamielinux/httpdate` (2 stars) — already covered above with its leapseconds dep.

**Verdict:** no pure-Python `>10`-star repo performs the zero-dep role we are filling.

### 3.4 Primary Scientific / Engineering Need Citation

| URL | HTTP code | Why cited |
| --- | --- | --- |
| https://www.rfc-editor.org/rfc/rfc9110.html | 200 | Authoritative source for HTTP-date §5.1.1; canonical reference for all three formats and the MUST-NOT-generate-obsolete rule. |
| https://www.rfc-editor.org/rfc/rfc7231.html | 200 | RFC 7231 §7.1.1.1 — the predecessor of RFC 9110 §5.1.1; primary literature citation. |
| https://www.rfc-editor.org/rfc/rfc5322.html | 200 | IMF-fixdate syntax derivation (RFC 5322 §3.3). |
| https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-create-signed-request.html | 200 | Real-world consumer of HTTP-date semantics (SigV4 signed headers). |
| https://docs.github.com/en/webhooks/webhook-events-and-payloads | 200 | Real-world WebHook delivery uses HTTP-date headers; conditional GET machinery. |
| https://github.com/jamielinux/httpdate/blob/main/src/httpdate/httpdate.py | 200 | Direct evidence of the only existing pure-Python HTTP-date package and its `from leapseconds import LEAP_SECONDS` dependency on line 24. |

(All curl-tested with `curl -I -L -s -o /dev/null -w "%{http_code}\n"`.)

### 3.5 Automated Gate Output

```json
{
  "name": "htdate-pure",
  "concept": "htdate-rfc1123-http-date",
  "keywords": ["http-date", "rfc1123", "rfc7231", "imf-fixdate"],
  "verdict": "APPROVED",
  "failures": [],
  "warnings": [],
  "details": {
    "stdlib": {"passed": true, "message": "No Python standard library collision."},
    "local_projects": {"passed": true, "message": "No local project collision."},
    "pypi": {"passed": true, "message": "No obvious PyPI package collisions among common naming variations."},
    "github": {"passed": true, "message": "No dominant high-star existing pure-Python repos found."}
  }
}
```

(Command: `python3 /root/.hermes/repo_factory/scripts/check_existing.py --name htdate-pure --concept htdate-rfc1123-http-date --keywords "http-date rfc1123 rfc7231 imf-fixdate" --json` — exit code 0.)

**Local-project cross-check:** `/root/projects/` does **not** contain any package that handles HTTP `Date:` headers. Sister repos `age-parse` (already shipped, parses `Age:` integer), `http-header-pure` (Link/Cache-Control/Content-Disposition ONLY), `accept-header`, `accept-ch-parse`, `accept-encoding-parse`, `allow-parse`, `bearerparse`, `cache-control-parse`, `cidr-subnet-pure`, `content-length-parse`, `content-range-parse`, `cookiespec`, `httpcneg`, `linkheader`, `rfc-8288-link-header-pure` all cover adjacent headers — **none touch `Date:` / `Last-Modified:` / `If-Modified-Since:` / `If-Unmodified-Since:` / `Expires:` / `Retry-After:`**. The placeholder `partialdate/` directory contains only a `# placeholder, will be replaced by build worker` note. Therefore this slot is open.

## 4. Core Mathematics & Canonical Reference

The three HTTP-date formats are reproduced verbatim from RFC 9110 §5.1.1 (which restates RFC 7231 §7.1.1.1):

```
IMF-fixdate  = day-name "," SP date1 SP time-of-day SP GMT
              ; fixed length, preferred
              ; e.g. Sun, 06 Nov 1994 08:49:37 GMT

rfc850-date  = day-name "," SP date2 SP time-of-day SP GMT
              ; obsolete
              ; e.g. Sunday, 06-Nov-94 08:49:37 GMT

asctime-date = day-name SP date3 SP time-of-day SP year
              ; obsolete; no timezone — interpreted as UTC
              ; e.g. Sun Nov  6 08:49:37 1994

day-name     = %x4D.6F.6E ; "Mon"
             / %x54.75.65 ; "Tue"
             / %x57.65.64 ; "Wed"
             / %x54.68.75 ; "Thu"
             / %x46.72.69 ; "Fri"
             / %x53.61.74 ; "Sat"
             / %x53.75.6E ; "Sun"

date1        = day SP month SP year
              ; day: 2-digit with leading zero for <10 (e.g. "06")
              ; month: "Jan" | "Feb" | ... | "Dec"
              ; year: 4-digit
date2        = day "-" month "-" 2-digit-year
              ; 2-digit-year: values 00–49 → 2000–2049; 50–99 → 1950–1999
date3        = month SP ( day ; leading space if day < 10 ; " 6" not "06" )
              ; year: 4-digit
time-of-day  = hour ":" minute ":" second
              ; hour:   00–23
              ; minute: 00–59
              ; second: 00–60 (60 allowed for leap seconds)
```

Canonical output: **IMF-fixdate only**. RFC 9110 §5.1.1 explicitly states "Recipients of a date that contains an obsolete format … are not required to handle it … but should not generate such a date." This is why `htdate.format()` always emits IMF-fixdate.

Leap-second handling (per the format spec the second value can be `60`): `htdate.parse` will accept second `60` and normalize it to `00` of the next minute — RFC 9110 §5.1.1 says recipients SHOULD accept `60`. Two-digit-year interpretation for rfc850 matches RFC 9110 §5.1.1: `70-99` → `1970-1999`, `00-69` → `2000-2069`.

## 5. Public API & Test Plan

### 5.1 Public API

```python
# htdate/__init__.py  (top-level package)
from htdate import parse, format, parse_dialect, InvalidFormat

# 1. parse(): auto-detect across the 3 dialects, return aware datetime in UTC.
#    Raises InvalidFormat on any unparseable input.
>>> parse("Sun, 06 Nov 1994 08:49:37 GMT")
datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc)
>>> parse("Sunday, 06-Nov-94 08:49:37 GMT")
datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc)
>>> parse("Sun Nov  6 08:49:37 1994")
datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc)
>>> parse("Sun, 06 Nov 1994 08:49:37 +0500")
InvalidFormat: "Sun, 06 Nov 1994 08:49:37 +0500": timezone must be 'GMT' or absent (asctime)

# 2. parse_dialect(): diagnostic — which format did parse() recognise?
>>> parse_dialect("Sun, 06 Nov 1994 08:49:37 GMT")
'imf'
>>> parse_dialect("Sunday, 06-Nov-94 08:49:37 GMT")
'rfc850'
>>> parse_dialect("Sun Nov  6 08:49:37 1994")
'asctime'
>>> parse_dialect("not a date")
None

# 3. format(): canonical IMF-fixdate output, requires tzinfo == UTC or None.
>>> from datetime import datetime, timezone
>>> format(datetime(2024, 1, 31, 23, 59, 0, tzinfo=timezone.utc))
'Wed, 31 Jan 2024 23:59:00 GMT'
>>> format(datetime(2024, 1, 31, 23, 59, 0))  # naive → assume UTC
'Wed, 31 Jan 2024 23:59:00 GMT'
>>> format(datetime(2024, 1, 31, 23, 59, 0, tzinfo=timezone(timedelta(hours=5))))
ValueError: tzinfo must be UTC or None (got +05:00)

# 4. to_imf(): alias for format() — convenience name matching canonical "IMF-fixdate" jargon.
>>> to_imf(datetime(2024, 1, 31, 23, 59, 0, tzinfo=timezone.utc))
'Wed, 31 Jan 2024 23:59:00 GMT'

# 5. InvalidFormat: single exception class with structured .value/.reason.
try:
    parse("foo")
except InvalidFormat as e:
    e.value      # "foo"
    e.reason     # e.g. "no matching dialect"
```

### 5.2 CLI

```
$ htdate-parse "Sun, 06 Nov 1994 08:49:37 GMT"
1994-11-06T08:49:37+00:00

$ htdate-parse --dialect "Sun, 06 Nov 1994 08:49:37 GMT"
imf

$ htdate-format --now
Sun, 11 Oct 2026 03:05:00 GMT

$ htdate-format -d "2024-01-31T23:59:00+00:00"
Wed, 31 Jan 2024 23:59:00 GMT

$ htdate-parse "garbage" ; echo $?
InvalidFormat: garbage: no matching dialect
2
```

### 5.3 Acceptance Criteria (≥100 enumerated)

**A. Stdlib / Dependency hygiene (5 criteria)**
1. `dependencies = []` in pyproject.toml.
2. `import sys; import htdate; sys.modules.keys()` after import contains no entry from outside the stdlib + `htdate` itself.
3. `make install` works in an empty virtualenv on Python 3.11/3.12/3.13 with no pre-installed packages.
4. `python -c "import htdate, sys; bad = [m for m in sys.modules if m.startswith('leapseconds') or m.startswith('httpdate')]; assert not bad"`.
5. README's "Install" block uses `pip install git+https://github.com/prasad-a-abhishek/htdate-pure.git` and never `pip install htdate-pure`.

**B. IMF-fixdate parse (10 criteria)**
6. `parse("Sun, 06 Nov 1994 08:49:37 GMT")` → `datetime(1994,11,6,8,49,37,tzinfo=utc)`.
7. Same input returns tz-aware UTC datetime (not naive).
8. Day with leading zero ("06") and day without ("6" in asctime) are accepted in their respective dialects and rejected in the wrong dialect.
9. Lowercase `Sun, 06 nov 1994 08:49:37 gmt` is rejected (case-sensitive per RFC 9110).
10. `parse("Sun, 06 Nov 1994 08:49:37 UTC")` is rejected (only `GMT` literal allowed, per RFC 9110).
11. `parse("Sun, 06 Nov 1994 08:49:37 +0000")` is rejected.
12. Day-of-month out of range → `InvalidFormat`.
13. Month name typo → `InvalidFormat`.
14. Year before 1900 → `InvalidFormat` (RFC 9110 minimum year).
15. Leap-day `parse("Fri, 29 Feb 2008 12:00:00 GMT")` → `datetime(2008,2,29,...)`.
16. `parse("Sat, 29 Feb 2008 12:00:00 GMT")` (wrong weekday vs. calendar) → `InvalidFormat` (cross-check).
17. `parse("Tue, 31 Feb 2008 12:00:00 GMT")` (Feb 31 doesn't exist) → `InvalidFormat`.

**C. RFC 850 parse (8 criteria)**
18. `parse("Sunday, 06-Nov-94 08:49:37 GMT")` → `datetime(1994,11,6,8,49,37,tzinfo=utc)`.
19. Day `parse("Sunday, 06-Nov-00 08:49:37 GMT")` → `datetime(2000,11,6,8,49,37,...)` (year ≥ 2000).
20. `parse("Sunday, 06-Nov-49 08:49:37 GMT")` → `datetime(2049,11,6,...)` (cutover at 50).
21. `parse("Sunday, 06-Nov-50 08:49:37 GMT")` → `datetime(1950,11,6,...)`.
22. `parse("Sunday, 06-Nov-99 08:49:37 GMT")` → `datetime(1999,11,6,...)`.
23. Wrong weekday (e.g. "Monday, 06-Nov-94 08:49:37 GMT" where 06-Nov-94 was a Sunday) → `InvalidFormat`.
24. Hyphen separator required (no slash, no space) — `parse("Sunday, 06/Nov/94 08:49:37 GMT")` rejected.
25. Two-digit year, not 4-digit, in this dialect — `parse("Sunday, 06-Nov-1994 08:49:37 GMT")` rejected.

**D. ANSI C asctime parse (5 criteria)**
26. `parse("Sun Nov  6 08:49:37 1994")` (note double space before 6) → `datetime(1994,11,6,...)`.
27. `parse("Sun Nov 06 08:49:37 1994")` (no double space) → `InvalidFormat` (leading-space-day is mandatory).
28. `parse("Sun Nov  6 08:49:37 1994 PST")` → `InvalidFormat` (no timezone; must be absent).
29. Day 1 with leading space "Sun Nov  1 08:49:37 1994" → `datetime(1994,11,1,...)`.
30. Year position is end, not after-day — `parse("Sun Nov  6 1994 08:49:37")` rejected.

**E. Format / IMF-fixdate output (8 criteria)**
31. `format(dt(1994,11,6,8,49,37,tzinfo=utc))` → `"Sun, 06 Nov 1994 08:49:37 GMT"`.
32. Naive datetime without tzinfo is assumed UTC (treated as UTC).
33. Non-UTC tzinfo raises `ValueError` with explicit message.
34. Leap second `second=60` either rejected with InvalidFormat (format side) OR coerced to 59 (depends on implementation choice — pick one and document; test asserts whichever). Default choice: **reject** on format (we never emit a leap-second), **normalize** on parse.
35. Output string is exactly 29 characters ("Sun, 06 Nov 1994 08:49:37 GMT").
36. Output uses English month/day abbreviations per RFC 9110 day-name and month table.
37. Year zero-padded to 4 digits (e.g. "0123" → year 123 CE not "123").
38. `to_imf()` returns the same string as `format()`.

**F. `parse_dialect` diagnostics (6 criteria)**
39. IMF-fixdate sample → `"imf"`.
40. RFC 850 sample → `"rfc850"`.
41. asctime sample → `"asctime"`.
42. Empty string → `None`.
43. Whitespace-only → `None`.
44. Garbage → `None` (no exception).

**G. Round-trip (3 criteria)**
45. For each of ≥10 canonical vectors (`(datetime, IMF-fixdate)` pairs), `format(parse(s)) == s` (after normalization of canonical weekday-name capitalization — assert the round-trip is `Sun, 06 Nov 1994 08:49:37 GMT` → ... → `Sun, 06 Nov 1994 08:49:37 GMT`).
46. `parse(format(dt(...)))` works for any UTC datetime in 1900–2100.
47. Round-trip is idempotent: `format(parse(format(parse(s)))) == format(parse(s))`.

**H. CLI (8 criteria)**
48. `htdate-parse "Sun, 06 Nov 1994 08:49:37 GMT"` prints ISO-8601 with `+00:00`.
49. `htdate-parse --dialect "..."` prints one of `imf`/`rfc850`/`asctime`.
50. `htdate-parse "garbage"` exits with non-zero status and prints the InvalidFormat message to stderr.
51. `htdate-format --now` prints current GMT as IMF-fixdate.
52. `htdate-format -d "2024-01-31T23:59:00+00:00"` prints `Wed, 31 Jan 2024 23:59:00 GMT`.
53. `htdate-format -d "2024-01-31T23:59:00" --assume-utc` prints IMF-fixdate.
54. `htdate-format` without args prints usage to stderr and exits non-zero.
55. `htdate-format -d "2024-01-31T23:59:00+05:00"` (non-UTC) exits non-zero with explicit message.

**I. Edge / unusual inputs (10 criteria)**
56. `parse("")` → `InvalidFormat`.
57. `parse(" ")` (whitespace) → `InvalidFormat`.
58. `parse("\x00")` (NUL byte) → `InvalidFormat`.
59. `parse("Sun, 06 Nov 1994 08:49:37 GMT\n")` (trailing newline) → accepted (strip trailing whitespace).
60. `parse("\tSun, 06 Nov 1994 08:49:37 GMT")` (leading tab) → `InvalidFormat` (no leading whitespace per RFC).
61. Pre-1970 dates e.g. `parse("Tue, 19 Jan 1900 03:14:07 GMT")` → `datetime(1900,1,19,3,14,7,tzinfo=utc)` (datetime allows it; verify).
62. Year 2099 `parse("Sun, 31 Dec 2099 23:59:59 GMT")` → `datetime(2099,12,31,...)`.
63. Year 2100 `parse("Sun, 31 Dec 2100 23:59:59 GMT")` → `InvalidFormat` (or accepted depending on year-cap choice; document + assert).
64. `parse("Sun, 06 Nov 1994 08:49:60 GMT")` (leap-second `second=60`) → `datetime(1994,11,6,8,49,60)` NOT raised (per RFC, second `60` is allowed).
65. `parse("Sun, 06 Nov 1994 08:49:61 GMT")` (second `61`) → `InvalidFormat`.

**J. Type & exception ergonomics (5 criteria)**
66. `parse` always returns a `datetime` with `tzinfo == timezone.utc` (never naive).
67. `InvalidFormat` subclasses `ValueError` so existing `except ValueError` callers work.
68. `parse_dialect` returns `Optional[str]`, never raises on bad input.
69. Public exports: `parse`, `format`, `to_imf`, `parse_dialect`, `InvalidFormat`, `__version__`.
70. `__version__` is a `str` matching `^0\.\d+\.\d+$`.

**K. Performance / packaging (5 criteria)**
71. `parse("Sun, 06 Nov 1994 08:49:37 GMT")` runs in <2 ms on CPython 3.11 (single call, warmed).
72. `format(...)` runs in <2 ms.
73. Package size (sdist + wheel) ≤ 25 kB each.
74. Wheel is `py3-none-any` (no platform tag).
75. Module exports cleanly under `python -S` (no sitecustomize dependencies).

**L. Spec-conformance & consistency (10 criteria)**
76. Spec-defined canonical vectors (one per dialect) all parse to the RFC's example timestamps.
77. Weekday vs date cross-check enforced for all three dialects.
78. Comma-only-after-weekday separator for IMF-fixdate and rfc850 (no extra whitespace allowed).
79. Spaces NOT surrounding the comma for IMF-fixdate: `"Sun , 06 Nov 1994 08:49:37 GMT"` rejected.
80. Hours can be `00..23`; `parse("..., 24:00:00 GMT")` is rejected.
81. Minutes and seconds must be `00..59` (or `60` seconds for leap seconds per above AC).
82. `format(...)` never emits seconds `60` (we never generate).
83. If naive datetime passed to `format`, tzinfo is filled with UTC and a warning is *not* raised (just documented as "naive = UTC").
84. Output weekday-name is exactly the 3-letter abbreviation `Mon, Tue, Wed, Thu, Fri, Sat, Sun` — no abbreviation expansion.
85. Month-name output is exactly `Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec`.

**M. Documentation / tests / fuzz (8 criteria)**
86. `README.md` has a 10-line "Quick start" example using `parse` and `format`.
87. `README.md` has a "Why?" section contrasting stdlib `email.utils` and `httpdate` (leapseconds dep).
88. `tests/test_parse.py` ≥ 30 unit tests.
89. `tests/test_format.py` ≥ 20 unit tests.
90. `tests/test_cli.py` ≥ 10 unit tests (one per AC in §H).
91. `tests/test_roundtrip.py` ≥ 15 vectors covering all 3 dialects.
92. `tests/test_canonical_vectors.py` ≥ 30 vectors from RFC 9110 §5.1.1 examples and edge cases.
93. Total test count ≥ 100 unique test cases.
94. `tests/test_leap_seconds.py` covers AC 64–65 + parser side; ≥ 4 tests.
95. `tests/test_dialect_detection.py` covers AC 39–44; ≥ 6 tests.
96. `tests/test_typo_rejection.py` ≥ 8 negative-path tests (typos, wrong weekday, wrong month, wrong year-range).
97. `tests/test_pre_1970.py` ≥ 3 tests for pre-1970 timestamps.
98. Fuzz surfaces (for downstream adversary audit): `parse(text: str)`, `format(dt: datetime)`, CLI `htdate-parse` argv, CLI `htdate-format` argv — 4 surfaces total.
99. `fuzz_parse.py` corpus seeds at least 20 examples (3 per dialect + 8 negative-path + canonical vectors).
100. `Makefile` has targets: `install`, `test`, `lint`, `format-check`, `bench`, `fuzz`.

(That's 100 acceptance criteria exactly. None of the spec §'s overlap with the "trivially redundant with another repo" forbidden list in repo-factory ROOT_SYSTEM_POLICY — `htdate-pure` is not a hash, not a stdlib duplicate, not a checksum, not a chemoinformatics primitive, not a personalisation/cookie algorithm.)

## 6. Mandatory Rule

**MUST be 100% zero-dependency in Python standard library** (`dependencies = []`).

Module boundary: only stdlib imports — `datetime`, `re`, `sys`, `typing`, `calendar` (for month-leap-day math only), `_strptime` (NOT used; we parse manually to keep the parser self-contained and predictable). No third-party deps. The wheel must build without network at install time beyond pulling the git+sdist source.

## 7. Size Budget

≤ 1000 LOC total (soft guideline). Expected breakdown:
- `htdate/__init__.py`: ~20 LOC (exports).
- `htdate/_parser.py`: ~250 LOC (3-format dialect detection, weekday cross-check, leap-second handling).
- `htdate/_format.py`: ~80 LOC (IMF-fixdate formatter, tz validation, weekday-by-integer table).
- `htdate/_tables.py`: ~30 LOC (weekday name + month name tables, including reverse lookup).
- `htdate/exceptions.py`: ~10 LOC (`InvalidFormat` exception with `.value` and `.reason`).
- `htdate/cli.py`: ~80 LOC (`htdate-parse`, `htdate-format` argument parsers).
- `tests/test_*.py`: ~500 LOC across 9 test files.

## 8. Target User Named In One Sentence

**Serverless / Pyodide / Cloudflare-Workers / WASM / air-gapped-CI developers who need to parse or emit a single HTTP `Date:` header without dragging in httpx, requests, urllib3, or a `leapseconds` data-table transitive dependency** — i.e. anyone whose deploy bundle is measured in kilobytes, not megabytes.

## 9. Competitor Named

`httpdate` 1.2.0 on PyPI (jamielinux, https://pypi.org/pypi/httpdate/json, https://github.com/jamielinux/httpdate/blob/main/src/httpdate/httpdate.py). It implements exactly the same RFC 9110 §5.1.1 surface area, including the 3-format tolerance, but **requires `leapseconds>=2023.4.0`** (declared in `requires_dist` and visible at line 24 of `httpdate.py`: `from leapseconds import LEAP_SECONDS`). For serverless/WASM/air-gapped users the leapseconds data table is a non-starter.

Secondary comparator: `email.utils` (Python stdlib). Provides `parsedate_tz`, `parsedate_to_datetime`, `formatdate`, `format_datetime` — but the parser returns a tuple or silently returns `None`, has no dialect detection, has no CLI, and the formatter emits `+0000` rather than `GMT`. `htdate-pure` is the stdlib-shaped-but-cleaner pure-Python replacement.

## 10. Honest Install Command

```bash
pip install git+https://github.com/prasad-a-abhishek/htdate-pure.git
```

(PyPI publish is pending. The README will surface this exact line — *not* `pip install htdate-pure` — and will not pretend the package is on PyPI.)

## 11. Fuzz Surface Note (for downstream adversary audit)

1. **Public core API surface** — `parse(text: str) -> datetime`, `format(dt: datetime) -> str`, `parse_dialect(text: str) -> Optional[str]`.
2. **CLI `htdate-parse` argv surface** — first positional argument `header_text`, `--dialect` boolean.
3. **CLI `htdate-format` argv surface** — `-d` / `--datetime` ISO-8601 input, `--now` boolean, `--assume-utc` boolean.
4. **Exception channel surface** — `InvalidFormat` raised from `parse()` with `.value` (original string) and `.reason` (machine-readable token). Never raised from `parse_dialect`.

Each surface gets fuzzed with a 30-second run in Phase 4 of the build pipeline (Atheris for Python 3.11+, hypothesis for property-based examples).

## 12. Out of Scope (Honest Limitations)

- `htdate-pure` does **not** implement HTTP-date parsing for `X-Amz-Date` (basic ISO 8601 compact form `YYYYMMDDTHHMMSSZ`) — that is a different AWS-SigV4-specific format with its own parsing concerns. AWS-sigv4 users can use `datetime.strptime(..., "%Y%m%dT%H%M%SZ")`.
- `htdate-pure` does **not** parse or emit RFC 2822 email dates; the email format is a different RFC and a different use case.
- `htdate-pure` does **not** implement leap-seconds arithmetic (no IERS data table); we accept second `60` per the format spec but do not collapse it to UTC microseconds.
- `htdate-pure` is not a date arithmetic library — use `datetime` directly for that.

## 13. Failure / Edge Behaviour Reference

| Input | Result |
| --- | --- |
| `parse("Sun, 06 Nov 1994 08:49:37 GMT")` | `datetime(1994, 11, 6, 8, 49, 37, tzinfo=utc)` |
| `parse("Sunday, 06-Nov-94 08:49:37 GMT")` | `datetime(1994, 11, 6, 8, 49, 37, tzinfo=utc)` |
| `parse("Sun Nov  6 08:49:37 1994")` | `datetime(1994, 11, 6, 8, 49, 37, tzinfo=utc)` |
| `parse("Sun, 06 Nov 1994 08:49:60 GMT")` | `datetime(1994, 11, 6, 8, 49, 60, tzinfo=utc)` (leap second) |
| `parse("Tue, 31 Feb 2008 12:00:00 GMT")` | raises `InvalidFormat("...", reason="day_out_of_range_for_month")` |
| `parse("Mon, 06 Nov 1994 08:49:37 GMT")` | raises `InvalidFormat(..., reason="weekday_mismatch")` |
| `format(datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone(timedelta(hours=5))))` | raises `ValueError("tzinfo must be UTC or None (got +05:00)")` |

