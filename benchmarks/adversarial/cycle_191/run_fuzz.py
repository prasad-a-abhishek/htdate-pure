"""Runner for cycle_191/adversary T03 fuzz execution.

Executes each of the three harnesses with a 60s wall-clock timeout,
captures stdout/stderr to logs/<harness>.log, parses iter counts and
crash markers out of the log, writes crashes/<harness>/<sha> for any
crash captured, and aggregates everything into stats.json.

This is a build-time helper — it is invoked once by T03, not on every
test run. Output is consumed by the T04 triage step.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, field
from typing import Optional

ROOT = os.path.dirname(os.path.abspath(__file__))
FUZZ = os.path.join(ROOT, "fuzz")
LOGS = os.path.join(ROOT, "logs")
CRASHES = os.path.join(ROOT, "crashes")
STATS_PATH = os.path.join(ROOT, "stats.json")

WALL_TIMEOUT_S = 60

HARNESSES = [
    # (name, script, default_iter)
    ("parse", "harness_parse.py", 100_000),
    ("format", "harness_format.py", 100_000),
    ("cli", "harness_cli.py", 1_000),
]


@dataclass
class HarnessResult:
    name: str
    iters_run: int = 0
    iters_target: int = 0
    elapsed_s: float = 0.0
    crashes_count: int = 0
    hangs_count: int = 0
    oom_count: int = 0
    timed_out: bool = False
    exit_code: int = 0
    log_path: str = ""
    crash_files: list[str] = field(default_factory=list)


_CRASH_MARKER = re.compile(r"^CRASH at iteration (\d+)", re.MULTILINE)
_CLI_CRASH_MARKER = re.compile(r"^CLI CRASH at iteration (\d+)", re.MULTILINE)
_OK_MARKER = re.compile(r"^OK:\s+(\d+)\s+iters\s+\(([\d.]+)s\)")


def _parse_iter_count(stdout: str, stderr: str, expected_target: int) -> tuple[int, float, bool]:
    """Extract iter count + elapsed time from harness output.

    Returns (iters_run, elapsed_seconds, parsed_ok). Falls back to 0/0.0/False.
    """
    combined = stdout + "\n" + stderr
    # OK line — clean finish
    m = _OK_MARKER.search(combined)
    if m:
        return int(m.group(1)), float(m.group(2)), True
    # Crash line — parse which iter fired
    m = _CRASH_MARKER.search(combined)
    if m:
        # Iter at which the crash fired; treat as iters_run since the
        # loop never completed.
        crash_iter = int(m.group(1))
        return crash_iter, 0.0, True
    m = _CLI_CRASH_MARKER.search(combined)
    if m:
        crash_iter = int(m.group(1))
        return crash_iter, 0.0, True
    # Parsed no markers — caller must rely on wall time + exit code.
    return 0, 0.0, False


def _dump_crash(name: str, stdout: str, stderr: str) -> Optional[str]:
    """If the harness output contains a crash report, write it under
    crashes/<name>/<sha> with a base64 payload + stderr dump.

    Returns the crash file path, or None if no crash detected.
    """
    combined = stdout + "\n" + stderr
    if "CRASH at iteration" not in combined and "CLI CRASH at iteration" not in combined:
        return None
    # Heuristic: take the last 4 KiB of stderr (which contains the
    # formatted crash banner) plus the truncated input payload. The
    # actual value is already echoed in the harness output as
    # ``value: <repr>`` so we don't need to reproduce it here.
    blob = (stdout + "\n---STDERR---\n" + stderr).encode("utf-8", errors="replace")
    sha = hashlib.sha256(blob).hexdigest()[:16]
    sub = os.path.join(CRASHES, name)
    os.makedirs(sub, exist_ok=True)
    path = os.path.join(sub, f"{sha}.txt")
    with open(path, "wb") as f:
        f.write(b"# cycle_191/adversary T03 crash dump\n")
        f.write(b"# sha256(first16): " + sha.encode("ascii") + b"\n")
        f.write(b"# base64(stderr+stdout):\n")
        f.write(base64.b64encode(blob))
        f.write(b"\n")
    return path


def _run_one(name: str, script: str, target_iters: int) -> HarnessResult:
    log_path = os.path.join(LOGS, f"harness_{name}.log")
    cmd = [
        sys.executable,
        os.path.join(FUZZ, script),
    ]
    env = os.environ.copy()
    # Tell the harness to use the full iteration target. The harness
    # honours HTDATE_FUZZ_ITER.
    env["HTDATE_FUZZ_ITER"] = str(target_iters)

    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=WALL_TIMEOUT_S,
            env=env,
            cwd=ROOT,
            check=False,
        )
        elapsed = time.monotonic() - start
        timed_out = False
        exit_code = proc.returncode
        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - start
        timed_out = True
        exit_code = -1  # sentinel for timeout
        # TimeoutExpired holds partial bytes only since Python 3.5+
        stdout = (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace") + "\n[Fuzz runner: timeout via subprocess.TimeoutExpired]\n"
    except (OSError,) as exc:
        elapsed = time.monotonic() - start
        timed_out = False
        exit_code = -2
        stdout = ""
        stderr = f"[Fuzz runner: subprocess error: {exc}]\n"

    os.makedirs(LOGS, exist_ok=True)
    with open(log_path, "w") as f:
        f.write(f"# command:   {' '.join(cmd)}\n")
        f.write(f"# timeout_s: {WALL_TIMEOUT_S}\n")
        f.write(f"# iters:     {target_iters}\n")
        f.write(f"# exit:      {exit_code}\n")
        f.write(f"# timed_out: {timed_out}\n")
        f.write(f"# elapsed_s: {elapsed:.3f}\n")
        f.write("# ---- STDOUT ----\n")
        f.write(stdout)
        if not stdout.endswith("\n"):
            f.write("\n")
        f.write("# ---- STDERR ----\n")
        f.write(stderr)

    iters_run, parsed_elapsed, _ok = _parse_iter_count(stdout, stderr, target_iters)
    # If the harness printed an OK line, prefer its elapsed time; else use wall time
    if parsed_elapsed == 0.0:
        parsed_elapsed = elapsed

    crashes = 0
    hangs = 0
    oom = 0
    crash_files: list[str] = []

    if "CRASH at iteration" in stdout + stderr or "CLI CRASH at iteration" in stdout + stderr:
        crashes = 1
        path = _dump_crash(name, stdout, stderr)
        if path is not None:
            crash_files.append(path)
    if timed_out:
        hangs = 1

    return HarnessResult(
        name=name,
        iters_run=iters_run or (target_iters if not timed_out and exit_code == 0 else 0),
        iters_target=target_iters,
        elapsed_s=parsed_elapsed,
        crashes_count=crashes,
        hangs_count=hangs,
        oom_count=oom,
        timed_out=timed_out,
        exit_code=exit_code,
        log_path=os.path.relpath(log_path, ROOT),
        crash_files=crash_files,
    )


def main() -> int:
    results: list[HarnessResult] = []
    for name, script, target in HARNESSES:
        print(f"[run] {name} target={target} ", end="", flush=True)
        r = _run_one(name, script, target)
        print(
            f"iters={r.iters_run} elapsed={r.elapsed_s:.2f}s "
            f"crashes={r.crashes_count} hangs={r.hangs_count} "
            f"oom={r.oom_count} timed_out={r.timed_out} exit={r.exit_code}"
        )
        results.append(r)

    # Aggregate.
    total_iters = sum(r.iters_run for r in results)
    total_crashes = sum(r.crashes_count for r in results)
    total_hangs = sum(r.hangs_count for r in results)
    total_oom = sum(r.oom_count for r in results)
    wall_total = sum(r.elapsed_s for r in results)

    # Count corpus seeds per harness.
    corpus_root = os.path.join(ROOT, "corpus")
    seed_counts = {}
    if os.path.isdir(corpus_root):
        for sub in os.listdir(corpus_root):
            full = os.path.join(corpus_root, sub)
            if os.path.isdir(full):
                seed_counts[sub] = sum(
                    1 for _ in os.listdir(full) if not _.startswith(".")
                )

    payload = {
        "cycle": "cycle_191",
        "phase": "adversary/T03",
        "wall_timeout_s": WALL_TIMEOUT_S,
        "wall_total_s": round(wall_total, 3),
        "totals": {
            "iters_total": total_iters,
            "crashes_total": total_crashes,
            "hangs_total": total_hangs,
            "oom_total": total_oom,
        },
        "harnesses": [asdict(r) for r in results],
        "corpus_seeds_per_harness": seed_counts,
        "corpus_total_seeds": sum(seed_counts.values()),
    }

    with open(STATS_PATH, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    print(f"\n[stats] wrote {STATS_PATH}")
    print(
        f"[totals] iters={total_iters} crashes={total_crashes} "
        f"hangs={total_hangs} oom={total_oom}"
    )
    # Exit 0 even on harness crashes — the orchestrator parses stats.json.
    # Any crash is recorded, not a runner failure.
    return 0


if __name__ == "__main__":
    sys.exit(main())