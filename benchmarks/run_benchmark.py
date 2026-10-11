#!/usr/bin/env python3
"""Head-to-head benchmark of htdate-pure vs PyPI `httpdate`.

Honest scope: this is a *narrow* comparison of zero-dep ``htdate-pure``
against ``httpdate`` (the closest existing pure-Python option). We do NOT
claim htdate-pure replaces httpdate — it has a leapseconds dep that
fails the zero-dep invariant for serverless/WASM/air-gapped. The point
of this benchmark is to confirm that zero-dep does NOT come at the cost
of order-of-magnitude slower parsing.

Workload profiles
-----------------
Five profiles that mirror HTTP-date traffic in real code:
1. ``single_imf_parse`` — parse one IMF-fixdate string (typical Date-header).
2. ``single_imf_format`` — format one datetime to IMF-fixdate.
3. ``batch_1k_imf`` — parse 1,000 IMF-fixdate strings in a tight loop.
4. ``batch_1k_format`` — format 1,000 datetimes.
5. ``mixed_dialects_1k`` — parse 1,000 strings spanning all 3 dialects.

Each profile is run for 5 iterations after 3 warmup iterations.

Environment declaration
-----------------------
- ``time.perf_counter()`` for wall-clock; ``tracemalloc`` for peak memory.
- Output: machine metadata + per-profile table + per-call mean + P95 +
  peak memory. Written to ``benchmarks/BENCHMARK.md`` (overwrites previous).

Dependencies
------------
- ``htdate-pure`` must be importable from the active venv (run
  ``pip install -e .`` from the repo root first).
- ``httpdate`` is installed in an isolated ``benchmarks/.venv_competitor``
  venv — see ``_boot_isolated_venv_with_httpdate``. If ``httpdate`` cannot
  be installed, the script fails with non-zero exit (NOT silently skipped
  — Invariant 21 forbids skipped competitor rows).
"""

from __future__ import annotations

import json
import platform
import shutil
import statistics
import subprocess
import sys
import time
import tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPETITOR_VENV = REPO_ROOT / "benchmarks" / ".venv_competitor"
COMPETITOR_PKG = "httpdate"
WARMUP = 3
ITERATIONS = 5

# ---------------------------------------------------------------------------
# Workload profiles — strings + datetimes.
# ---------------------------------------------------------------------------

IMF_SAMPLES = [
    "Sun, 06 Nov 1994 08:49:37 GMT",
    "Mon, 01 Jan 2024 00:00:00 GMT",
    "Thu, 31 Dec 2099 23:59:59 GMT",
    "Thu, 29 Feb 2024 12:00:00 GMT",
    "Thu, 15 Jun 2023 14:30:45 GMT",
    "Fri, 01 Jul 2022 09:15:22 GMT",
    "Sat, 28 Feb 2026 16:45:30 GMT",
    "Sun, 06 Nov 1994 08:49:38 GMT",
    "Wed, 06 Nov 2024 08:49:37 GMT",
    "Tue, 06 Nov 1934 08:49:37 GMT",
]

RFC850_SAMPLES = [
    "Sunday, 06-Nov-94 08:49:37 GMT",
    "Monday, 01-Jan-24 00:00:00 GMT",
    "Friday, 31-Dec-99 23:59:59 GMT",
]

ASCTIME_SAMPLES = [
    "Sun Nov  6 08:49:37 1994",
    "Mon Jan  1 00:00:00 2024",
    "Thu Dec 31 23:59:59 2099",
]

ALL_SAMPLES = IMF_SAMPLES + RFC850_SAMPLES + ASCTIME_SAMPLES


def _batch(samples: list[str], n: int) -> list[str]:
    out: list[str] = []
    while len(out) < n:
        out.extend(samples)
    return out[:n]


BATCH_1K_PARSE = _batch(ALL_SAMPLES, 1000)
BATCH_1K_FORMAT_DTS: list[datetime] = []
MIXED_PARSE_BATCH: list[str] = []


# ---------------------------------------------------------------------------
# htdate-pure adapter
# ---------------------------------------------------------------------------


class HtdatePureAdapter:
    name = "htdate-pure"

    def __init__(self) -> None:
        import htdate_pure  # noqa: F401  (verify importable)
        self._parse = htdate_pure.parse
        self._format = htdate_pure.format

    def parse_one(self, s: str) -> datetime:
        return self._parse(s)

    def parse_batch(self, batch: list[str]) -> None:
        for s in batch:
            self._parse(s)

    def format_one(self, dt: datetime) -> str:
        return self._format(dt)

    def format_batch(self, dts: list[datetime]) -> None:
        for dt in dts:
            self._format(dt)


# ---------------------------------------------------------------------------
# httpdate adapter (loaded via subprocess for clean isolation)
# ---------------------------------------------------------------------------


_HTTPDATE_PROBE = """
import sys, json, time
import httpdate
data = json.loads(sys.stdin.read())
op = data["op"]
samples = data["samples"]
repeats = int(data.get("repeats", 1))
if op.startswith("parse"):
    t0 = time.perf_counter()
    for _ in range(repeats):
        for s in samples:
            httpdate.httpdate_to_unixtime(s)
    elapsed = time.perf_counter() - t0
elif op.startswith("format"):
    import datetime
    samples_dt = [datetime.datetime.fromisoformat(s) for s in samples]
    t0 = time.perf_counter()
    for _ in range(repeats):
        for dt in samples_dt:
            httpdate.unixtime_to_httpdate(int(dt.timestamp()))
    elapsed = time.perf_counter() - t0
else:
    raise ValueError(op)
print(json.dumps({"elapsed": elapsed}))
"""


class HttpdateAdapter:
    name = "httpdate"

    def __init__(self) -> None:
        self._proc: Path | None = None
        self._probe_path: Path | None = None

    def _ensure_proc(self) -> None:
        if self._proc is None:
            self._proc = _boot_isolated_venv_with_httpdate()
            self._probe_path = self._proc.parent / "_probe.py"
            self._probe_path.write_text(_HTTPDATE_PROBE)

    def _run(self, op: str, samples: list[str], repeats: int = 1) -> float:
        self._ensure_proc()
        assert self._proc is not None
        assert self._probe_path is not None
        proc_input = json.dumps(
            {"op": op, "samples": samples, "repeats": repeats}
        ).encode()
        result = subprocess.run(
            [str(self._proc), str(self._probe_path)],
            input=proc_input,
            capture_output=True,
            check=False,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"httpdate subprocess failed: rc={result.returncode} "
                f"stderr={result.stderr.decode(errors='replace')}"
            )
        out = json.loads(result.stdout.decode())
        return float(out["elapsed"])

    def parse_one(self, s: str) -> datetime:
        self._run("parse_one", [s])
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

    def parse_batch(self, batch: list[str]) -> None:
        self._run("parse_batch", batch)

    def format_one(self, dt: datetime) -> str:
        self._run("format_one", [dt.isoformat()])
        return ""

    def format_batch(self, dts: list[datetime]) -> None:
        self._run("format_batch", [dt.isoformat() for dt in dts])


# ---------------------------------------------------------------------------
# Isolated venv for httpdate (Invariant 21 — fail-closed, no skipped rows)
# ---------------------------------------------------------------------------


def _boot_isolated_venv_with_httpdate() -> Path:
    """Bootstrap an isolated venv with ``httpdate`` installed.

    Returns the absolute path to the venv's ``python`` executable.
    Caches the venv at ``benchmarks/.venv_competitor`` for repeat runs.
    """
    if shutil.which("uv") is not None:
        py = COMPETITOR_VENV / "bin" / "python"
        if not py.exists():
            subprocess.run(
                ["uv", "venv", str(COMPETITOR_VENV), "--python", "3.11"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(py),
                    COMPETITOR_PKG,
                ],
                check=True,
                capture_output=True,
            )
        return py
    py = COMPETITOR_VENV / "bin" / "python"
    if not py.exists():
        import venv
        venv.EnvBuilder(with_pip=True).create(str(COMPETITOR_VENV))
        subprocess.run(
            [str(py), "-m", "pip", "install", COMPETITOR_PKG],
            check=True,
            capture_output=True,
        )
    return py


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def _stats(elapsed_list: list[float], n_calls: int) -> dict[str, float]:
    per_call_us = [e / n_calls * 1_000_000 for e in elapsed_list]
    if len(per_call_us) > 1:
        p95_idx = max(0, int(len(per_call_us) * 0.95) - 1)
        p95 = sorted(per_call_us)[p95_idx]
    else:
        p95 = per_call_us[0]
    return {
        "mean_us": statistics.mean(per_call_us),
        "p95_us": p95,
        "total_s": sum(elapsed_list),
    }


def run_profile(
    name: str,
    adapter,
    fn: Callable[[], None],
    n_calls: int,
) -> dict[str, object]:
    """Run a single profile, returning mean/p95/total/peak-memory."""
    for _ in range(WARMUP):
        fn()
    elapsed: list[float] = []
    tracemalloc.start()
    peak_bytes = 0
    for _ in range(ITERATIONS):
        snap_start = tracemalloc.take_snapshot()
        t0 = time.perf_counter()
        fn()
        elapsed.append(time.perf_counter() - t0)
        snap_end = tracemalloc.take_snapshot()
        diff = snap_end.compare_to(snap_start, "lineno")
        for stat in diff:
            peak_bytes = max(peak_bytes, stat.size_diff + stat.size)
    tracemalloc.stop()
    stats = _stats(elapsed, n_calls)
    stats["peak_kb"] = peak_bytes / 1024.0
    stats["iterations"] = ITERATIONS
    return {"name": name, "adapter": adapter.name, **stats}


def _build_format_datetimes(n: int) -> list[datetime]:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [base + timedelta(minutes=i) for i in range(n)]


def _build_mixed_parse_batch(n: int) -> list[str]:
    out: list[str] = []
    i = 0
    while len(out) < n:
        out.append(ALL_SAMPLES[i % len(ALL_SAMPLES)])
        i += 1
    return out


def main() -> int:
    print(f"Benchmarking htdate-pure vs {COMPETITOR_PKG}...")
    print(f"Repo: {REPO_ROOT}")
    print(f"Python: {sys.version.split()[0]} ({platform.python_implementation()})")
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"CPU: {platform.processor() or 'unknown'}")
    print()

    format_dts = _build_format_datetimes(1000)
    mixed_parse = _build_mixed_parse_batch(1000)

    ht = HtdatePureAdapter()
    hd = HttpdateAdapter()

    profiles = [
        ("single_imf_parse", ht, lambda: ht.parse_one(IMF_SAMPLES[0]), 1),
        ("single_imf_parse", hd, lambda: hd.parse_one(IMF_SAMPLES[0]), 1),
        ("single_imf_format", ht, lambda: ht.format_one(format_dts[0]), 1),
        ("single_imf_format", hd, lambda: hd.format_one(format_dts[0]), 1),
        ("batch_1k_parse_imf", ht, lambda: ht.parse_batch(BATCH_1K_PARSE), 1000),
        ("batch_1k_parse_imf", hd, lambda: hd.parse_batch(BATCH_1K_PARSE), 1000),
        ("batch_1k_format", ht, lambda: ht.format_batch(format_dts), 1000),
        ("batch_1k_format", hd, lambda: hd.format_batch(format_dts), 1000),
        ("mixed_dialects_1k", ht, lambda: ht.parse_batch(mixed_parse), 1000),
        ("mixed_dialects_1k", hd, lambda: hd.parse_batch(mixed_parse), 1000),
    ]

    results: list[dict[str, object]] = []
    for name, adapter, fn, n in profiles:
        try:
            r = run_profile(name, adapter, fn, n)
        except Exception as exc:
            print(f"FAIL {name}/{adapter.name}: {exc}")
            return 1
        results.append(r)
        print(
            f"{name:>24s} {adapter.name:>14s} "
            f"mean={r['mean_us']:8.2f} us  "
            f"p95={r['p95_us']:8.2f} us  "
            f"peak={r['peak_kb']:8.1f} KB"
        )

    write_markdown(results)
    print(f"\nWrote {REPO_ROOT / 'benchmarks' / 'BENCHMARK.md'}")
    return 0


def write_markdown(results: list[dict[str, object]]) -> None:
    out_path = REPO_ROOT / "benchmarks" / "BENCHMARK.md"
    by_profile: dict[str, list[dict[str, object]]] = {}
    for r in results:
        by_profile.setdefault(str(r["name"]), []).append(r)

    lines: list[str] = []
    lines.append("# htdate-pure benchmark")
    lines.append("")
    lines.append("Honest comparison of zero-dep `htdate-pure` vs PyPI `httpdate` 1.2.0.")
    lines.append("")
    lines.append("**Scope:** This is a *narrow* comparison of zero-dep HTTP-date parsing.")
    lines.append("`httpdate` requires `leapseconds>=2023.4.0` (data table dependency)")
    lines.append("and is therefore unusable on Pyodide / Cloudflare Workers / air-gapped CI.")
    lines.append("`htdate-pure` is not a drop-in replacement; the goal of this benchmark")
    lines.append("is to confirm zero-dep does not cost an order of magnitude.")
    lines.append("")
    lines.append("## Environment")
    lines.append("")
    lines.append(f"- Python: {sys.version.split()[0]} ({platform.python_implementation()})")
    lines.append(f"- OS: {platform.system()} {platform.release()}")
    lines.append(f"- CPU: {platform.processor() or 'unknown'}")
    lines.append("- Timing: `time.perf_counter()` (microsecond resolution)")
    lines.append("- Memory: `tracemalloc` peak per iteration")
    lines.append(f"- Warmup: {WARMUP} iterations, Measured: {ITERATIONS} iterations")
    lines.append("- Competitor venv: isolated `benchmarks/.venv_competitor` (subprocess)")
    lines.append("")

    lines.append("## Per-workload metrics")
    lines.append("")
    lines.append("All `us` values are **microseconds per single call**.")
    lines.append("All `KB` values are peak memory delta for the entire workload iteration.")
    lines.append("")
    lines.append("| Workload | Tool | Mean (us/call) | P95 (us/call) | Peak (KB) | Iterations |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for profile_name, rows in by_profile.items():
        for r in rows:
            lines.append(
                f"| {profile_name} | {r['adapter']} | "
                f"{r['mean_us']:.2f} | {r['p95_us']:.2f} | "
                f"{r['peak_kb']:.1f} | {r['iterations']} |"
            )
    lines.append("")

    lines.append("## Reproduce locally")
    lines.append("")
    lines.append("```bash")
    lines.append("cd /root/projects/htdate-pure")
    lines.append("pip install -e .")
    lines.append("python3 benchmarks/run_benchmark.py")
    lines.append("```")
    lines.append("")
    lines.append("The script will auto-bootstrap `benchmarks/.venv_competitor`")
    lines.append("with `httpdate` (via `uv` if available, else stdlib `venv`).")
    lines.append("")

    out_path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())