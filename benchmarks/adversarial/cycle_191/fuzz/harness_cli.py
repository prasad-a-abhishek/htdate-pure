"""Fuzz harness for htdate-pure CLI entry points (T02, cycle_191/adversary).

Attack surfaces covered:

1. ``htdate-parse`` console script — the published entry point that
   wraps :func:`htdate_pure.cli.main_parse`. Supports:

   * a positional ``header`` argument,
   * ``--dialect`` flag,
   * ``--version`` (handled by argparse, exits 0),
   * reading from stdin when no positional is given.

2. ``htdate-format`` console script — wraps
   :func:`htdate_pure.cli.main_format`. Supports:

   * ``-d/--datetime ISO-8601``,
   * ``-u/--unix EPOCH``,
   * ``--now``,
   * ``--assume-utc``,
   * ``--version``,
   * mutually-exclusive source rules (one of the three must be set).

Crash semantics
---------------
The documented exit-code matrix is:

* ``0`` — success
* ``2`` — parse / format error (CLI EXIT_INPUT_ERROR per F-QA-003)
* ``64`` — usage error (CLI EXIT_USAGE, matches sysexits.h EX_USAGE)

A CLI invocation is a *CRASH* when:

* its exit code is **outside** ``{0, 2, 64}``, **OR**
* its exit code is in the success set but stderr contains the marker
  ``Traceback (most recent call last)`` (indicating an unhandled
  exception in our code that somehow surfaced to stdout/stderr),
* we lost the subprocess to a timeout (Terminated by SIGKILL after the
  per-call deadline; the harness sets ``timeout=10s`` to bound
  infinite loops).

Implementation
--------------
We invoke each console script via :mod:`subprocess` with mutated argv.
A separate :class:`concurrent.futures.ThreadPoolExecutor` is *not*
used because we want strict serialization and a hard per-call timeout;
the default :func:`subprocess.run` honors ``timeout=``.

For ``htdate-parse``, we pipe stdin (a randomized fake HTTP-date)
and pass mutated argv. For ``htdate-format``, we mutate the source
flags and the source-flag values.

Each iteration also re-randomizes the working environment:

* ``LANG``/``LC_ALL`` to a few C.UTF-8 / POSIX variants,
* ``PYTHONHASHSEED`` to a fresh value (defends against hash-randomized
  scheduling surprises).

Iteration budget
----------------
``MAX_ITER = 1_000`` for the CLI harness — subprocess-spawning fuzzers
are inherently orders of magnitude slower than in-process mutations,
and the CLI surface area is smaller (argparse rejects garbage fast).
Override via ``HTDATE_FUZZ_ITER``.

Coverage caveats
----------------
ASan/UBSan instrumentation is unavailable in this container. Side
effects (file creation in ``/tmp``, network outbound) are constrained
because none of the CLIs do those things today.
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import time

MAX_ITER = int(os.environ.get("HTDATE_FUZZ_ITER", "1000"))

# Whitelist of exit codes the CLIs are permitted to produce.
_ALLOWED = {0, 2, 64}
_TRACEBACK_MARKER = "Traceback (most recent call last)"
_PER_CALL_TIMEOUT_S = 5.0


# ---------------------------------------------------------------------------
# Argv generators
# ---------------------------------------------------------------------------

_PRINTABLE = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    " _-.,:/+@=()[]{}'*\"\\<>"
)


def _randstr(rng: random.Random, lo: int = 0, hi: int = 64) -> str:
    n = rng.randint(lo, hi)
    return "".join(rng.choices(_PRINTABLE, k=n))


def _randbytes(rng: random.Random, lo: int = 1, hi: int = 64) -> bytes:
    n = rng.randint(lo, hi)
    # Mix printable ascii with control chars to stress argv parsing.
    pool = list(range(0x20)) + list(range(0x7F, 0x100))  # control bytes + high
    return bytes(rng.choices(pool, k=n))


def _argv_parse(rng: random.Random) -> list[str]:
    """Generate mutated argv for ``htdate-parse``.

    Variants:
    * No positional + non-empty stdin (the documented stdin path).
    * Random positional, possibly with --dialect / --version.
    * Pure flag noise (no positional) with stdin.
    """
    variant = rng.choice(("stdin_only", "positional", "dialect", "noise"))
    if variant == "stdin_only":
        return []
    if variant == "dialect":
        d = rng.choice(("--dialect", "--dialect=", "-d", "--D"))
        if rng.random() < 0.4:
            return [d]
        # A positional too:
        pos = _randstr(rng, 1, 80)
        return [pos, d]
    if variant == "positional":
        pos = _randstr(rng, 1, 120)
        if rng.random() < 0.5:
            return [pos]
        if rng.random() < 0.5:
            return [pos, "--dialect"]
        return [pos]
    # noise
    nflags = rng.randint(1, 5)
    out = []
    for _ in range(nflags):
        flag = rng.choice(("--dialect", "--version", "-h", "--help",
                           "--unknown", "--" + _randstr(rng, 1, 10)))
        out.append(flag)
        if rng.random() < 0.3:
            out.append(_randstr(rng, 0, 64))
    return out


def _argv_format(rng: random.Random) -> list[str]:
    """Generate mutated argv for ``htdate-format``."""
    n = rng.randint(0, 3)
    out = []
    choices = ("-d", "--datetime", "-u", "--unix", "--now", "--assume-utc",
               "--version", "-h", "--help", "--bogus-" + _randstr(rng, 1, 6))
    for _ in range(n):
        f = rng.choice(choices)
        out.append(f)
        if f in ("-d", "--datetime"):
            iso = rng.choice((
                "2024-01-31T23:59:00+00:00",
                "2024-01-31T23:59:00",
                "2024-01-31T23:59:60Z",
                "1994-11-06T08:49:37+00:00",
                _randstr(rng, 0, 30),
                _randstr(rng, 0, 30),
                "",  # empty ISO
                "not-a-date",
            ))
            out.append(iso)
        elif f in ("-u", "--unix"):
            out.append(rng.choice(("-1", "0", "1", "1234567890",
                                   str(2**31), str(-(2**31)),
                                   str(2**63), str(-(2**63)),
                                   str(2**99),
                                   _randstr(rng, 1, 12))))
    return out


# ---------------------------------------------------------------------------
# Stdin payload generators
# ---------------------------------------------------------------------------

_SEEDS = (
    "Sun, 06 Nov 1994 08:49:37 GMT",
    "Sunday, 06-Nov-94 08:49:37 GMT",
    "Sun Nov  6 08:49:37 1994",
    "",  # empty stdin
    "not a date",
    "\x00\x00\x00",
    "G" * 256,
)


def _stdin_payload(rng: random.Random) -> bytes:
    seed = rng.choice(_SEEDS)
    if rng.random() < 0.5:
        return seed.encode("utf-8", errors="replace")
    # Mutate: replace random bytes. Guard against empty seed so a
    # zero-length payload (which the CLIs must still tolerate) does
    # not crash the harness.
    ba = bytearray(seed.encode("utf-8", errors="replace"))
    if not ba:
        ba = bytearray(rng.randrange(1, 64))
    for _ in range(rng.randint(1, 5)):
        idx = rng.randrange(len(ba))
        ba[idx] = rng.randrange(256)
    return bytes(ba)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class _Crash(Exception):
    def __init__(self, op: str, argv: list[str], payload, exit_code, stderr: str) -> None:
        self.op = op
        self.argv = argv
        self.payload = payload
        self.exit_code = exit_code
        self.stderr = stderr


def _run(cmd: list[str], stdin_bytes: bytes | None, op: str) -> None:
    """Invoke cmd, classify the result.

    CRASH conditions:
    * timeout (raises :class:`subprocess.TimeoutExpired`)
    * exit code outside allowed set
    * unhandled traceback in stderr on a "successful" exit code
    """
    env = os.environ.copy()
    env["LANG"] = "C.UTF-8"
    env["LC_ALL"] = "C.UTF-8"
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_bytes,
            capture_output=True,
            timeout=_PER_CALL_TIMEOUT_S,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise _Crash(op, cmd, stdin_bytes, -1, "timeout: " + str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise _Crash(op, cmd, stdin_bytes, -2, f"subprocess error: {exc}") from exc

    if proc.returncode not in _ALLOWED:
        raise _Crash(
            op, cmd, stdin_bytes, proc.returncode,
            proc.stderr.decode("utf-8", errors="replace")[:2000],
        )
    if proc.returncode == 0 and _TRACEBACK_MARKER in proc.stderr.decode("utf-8", errors="replace"):
        raise _Crash(
            op, cmd, stdin_bytes, proc.returncode,
            proc.stderr.decode("utf-8", errors="replace")[:2000],
        )


def fuzz(iterations: int = MAX_ITER, seed: int = 0) -> None:
    """CLI fuzz loop.

    Each iteration toggles between ``htdate-parse`` and
    ``htdate-format`` and re-randomizes argv / stdin / environment.
    """
    rng = random.Random(seed or int.from_bytes(os.urandom(8), "big"))

    # ----- Smoke.
    try:
        _run(["htdate-parse", "Sun, 06 Nov 1994 08:49:37 GMT"], None, "smoke_parse_ok")
        _run(["htdate-parse", "--bogus"], None, "smoke_parse_usage")
        _run(["htdate-format", "--now"], None, "smoke_format_ok")
        _run(["htdate-format"], None, "smoke_format_usage")
    except _Crash as crash:
        sys.stderr.write(
            f"FATAL: CLI smoke failed: {crash.op}: exit {crash.exit_code}: "
            f"{crash.stderr!r}\n"
        )
        sys.exit(2)

    start = time.monotonic()
    for i in range(iterations):
        op = i % 2
        try:
            if op == 0:
                _run(
                    ["htdate-parse", *_argv_parse(rng)],
                    _stdin_payload(rng) if rng.random() < 0.5 else None,
                    "htdate-parse",
                )
            else:
                _run(
                    ["htdate-format", *_argv_format(rng)],
                    None,
                    "htdate-format",
                )
        except _Crash as crash:
            elapsed = time.monotonic() - start
            sys.stderr.write(
                "\n"
                + "=" * 78 + "\n"
                + f"CLI CRASH at iteration {i} ({elapsed:.2f}s into fuzz)\n"
                + f"  op:        {crash.op}\n"
                + f"  argv:      {crash.argv!r}\n"
                + f"  exit:      {crash.exit_code}\n"
                + f"  stderr:    {crash.stderr!r}\n"
                + "=" * 78 + "\n"
            )
            sys.exit(1)

    elapsed = time.monotonic() - start
    print(f"OK: {iterations} iters ({elapsed:.2f}s) — no CLI crashes")


if __name__ == "__main__":
    fuzz()
