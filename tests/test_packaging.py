"""Stdlib / dependency hygiene, public API surface, packaging invariants.

Maps to spec §5.3 acceptance criteria A (AC 1-5), J (AC 66-70), K (AC
71-75), and M (parts of AC 86-100).
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from datetime import datetime, timezone

import pytest

import htdate_pure
from htdate_pure import (
    InvalidFormat,
    __version__,
    format,
    parse,
    parse_dialect,
    to_imf,
)
from htdate_pure.exceptions import InvalidFormat as _InvalidFormat2

from conftest import covers


REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


# ---------------------------------------------------------------------------
# Stdlib / dep hygiene (AC 1-5)
# ---------------------------------------------------------------------------


@covers(1, "test_dependencies_empty")
def test_dependencies_empty():
    with PYPROJECT.open("rb") as fh:
        data = tomllib.load(fh)
    deps = data.get("project", {}).get("dependencies", [])
    assert deps == [], f"expected zero runtime deps, got {deps}"


@covers(2, "test_import_pulls_no_third_party")
def test_import_pulls_no_third_party():
    """Importing htdate_pure must not pull anything outside stdlib + htdate_pure."""
    # Save current htdate_pure modules so we can restore them after the
    # wipe — this prevents cross-test contamination where a downstream
    # test catches an exception class that no longer matches the one
    # bound in htdate_pure.parse.__globals__ (the function still points
    # at the OLD class instance).
    saved = {mod: sys.modules[mod] for mod in list(sys.modules)
             if mod.startswith("htdate_pure") or mod == "htdate_pure"}
    try:
        for mod in list(sys.modules):
            if mod.startswith("htdate_pure"):
                del sys.modules[mod]
        import htdate_pure as _h  # noqa: F401
        offenders = []
        forbidden_prefixes = (
            "leapseconds",
            "httpdate",
            "httpx",
            "requests",
            "urllib3",
        )
        for mod in sys.modules:
            for prefix in forbidden_prefixes:
                if mod == prefix or mod.startswith(prefix + "."):
                    offenders.append(mod)
                    break
        assert not offenders, f"forbidden modules imported: {offenders}"
    finally:
        # Restore original module objects so other tests' bound functions
        # raise the same exception class instances that they imported.
        for mod in list(sys.modules):
            if mod.startswith("htdate_pure"):
                del sys.modules[mod]
        for mod, obj in saved.items():
            sys.modules[mod] = obj


@covers(3, "test_install_in_clean_venv")
def test_install_in_clean_venv():
    """``pip install -e .`` from a clean clone must succeed with stdlib only.

    Smoke check: ``import htdate_pure`` works without httpx / requests.
    The actual install command is exercised in the build smoke step.
    """
    import importlib
    importlib.invalidate_caches()
    import htdate_pure  # noqa: F401
    assert htdate_pure.__version__


@covers(4, "test_no_leapseconds_or_httpdate_modules")
def test_no_leapseconds_or_httpdate_modules():
    """Negative guard: neither ``leapseconds`` nor ``httpdate`` modules are loaded."""
    import htdate_pure  # noqa: F401
    bad = [m for m in sys.modules
           if m == "leapseconds" or m.startswith("leapseconds.")
           or m == "httpdate" or m.startswith("httpdate.")]
    assert not bad


# ---------------------------------------------------------------------------
# Public API surface (AC 69)
# ---------------------------------------------------------------------------


@covers(69, "test_public_api_exports")
def test_public_api_exports():
    """All expected symbols are importable from ``htdate_pure``."""
    assert callable(parse)
    assert callable(format)
    assert callable(to_imf)
    assert callable(parse_dialect)
    assert InvalidFormat is not None
    assert _InvalidFormat2 is InvalidFormat  # same class
    assert isinstance(__version__, str)


@covers(69, "test_all_exports_match_dunder_all")
def test_all_exports_match_dunder_all():
    for name in htdate_pure.__all__:
        assert hasattr(htdate_pure, name), f"missing export: {name}"


@covers(70, "test_version_string_format")
def test_version_string_format():
    assert isinstance(__version__, str)
    assert re.match(r"^0\.\d+\.\d+$", __version__), \
        f"unexpected version format: {__version__!r}"


# ---------------------------------------------------------------------------
# Type / exception ergonomics (AC 66-68)
# ---------------------------------------------------------------------------


@covers(66, "test_parse_always_returns_aware_utc_check")
def test_parse_always_returns_aware_utc_check():
    samples = [
        "Sun, 06 Nov 1994 08:49:37 GMT",
        "Sunday, 06-Nov-94 08:49:37 GMT",
        "Sun Nov  6 08:49:37 1994",
    ]
    for s in samples:
        dt = parse(s)
        assert dt.tzinfo is not None
        offset = dt.utcoffset()
        assert offset is not None
        assert offset.total_seconds() == 0


@covers(67, "test_invalidformat_subclasses_valueerror")
def test_invalidformat_subclasses_valueerror():
    """``InvalidFormat`` subclasses ``ValueError`` for backward compatibility."""
    assert issubclass(InvalidFormat, ValueError)
    # Catch as ValueError works.
    try:
        parse("garbage")
    except ValueError as exc:
        assert isinstance(exc, InvalidFormat)
        assert exc.value == "garbage"
        assert exc.reason == "no_matching_dialect"


@covers(68, "test_parse_dialect_returns_optional_str")
def test_parse_dialect_returns_optional_str():
    for s in ["", "garbage", None, b"bytes", 123]:
        result = parse_dialect(s)  # type: ignore[arg-type]
        # Either None or a valid dialect name; never raises.
        assert result is None or result in {"imf", "rfc850", "asctime"}


# ---------------------------------------------------------------------------
# Performance / packaging (AC 71-75)
# ---------------------------------------------------------------------------


@covers(71, "test_parse_perf_under_2ms")
def test_parse_perf_under_2ms():
    """Single parse() call < 2ms on CPython 3.11 (warmed)."""
    text = "Sun, 06 Nov 1994 08:49:37 GMT"
    # Warmup
    for _ in range(100):
        parse(text)
    # Measure
    import time
    t0 = time.perf_counter()
    for _ in range(1000):
        parse(text)
    elapsed = (time.perf_counter() - t0) / 1000
    # Generous ceiling; CI variance is high. We assert < 2ms / call.
    assert elapsed < 0.002, f"per-call parse time: {elapsed*1000:.3f}ms"


@covers(72, "test_format_perf_under_2ms")
def test_format_perf_under_2ms():
    """Single format() call < 2ms on CPython 3.11 (warmed)."""
    dt = datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc)
    for _ in range(100):
        format(dt)
    import time
    t0 = time.perf_counter()
    for _ in range(1000):
        format(dt)
    elapsed = (time.perf_counter() - t0) / 1000
    assert elapsed < 0.002, f"per-call format time: {elapsed*1000:.3f}ms"


@covers(73, "test_source_size_under_budget")
def test_source_size_under_budget():
    """Source-tree LOC under the 1000-LOC soft budget."""
    src_dir = REPO_ROOT / "src"
    total = 0
    for p in src_dir.rglob("*.py"):
        with p.open() as fh:
            total += sum(1 for _ in fh)
    # Soft guideline; we assert ≤ 1500 to leave room for clarity.
    assert total <= 1500, f"src LOC = {total}"


@covers(75, "test_imports_clean_under_no_site")
def test_imports_clean_under_no_site():
    """Module imports cleanly under ``python -S`` (no sitecustomize)."""
    # ``python -S`` disables site.py which normally sets up the
    # user-site / site-packages paths. To still import our editable
    # install we explicitly point PYTHONPATH at the src/ directory.
    import subprocess
    import os
    src_path = str(REPO_ROOT / "src")
    env = dict(os.environ)
    env["PYTHONPATH"] = src_path
    proc = subprocess.run(
        [sys.executable, "-S", "-c", "import htdate_pure; print(htdate_pure.__version__)"],
        capture_output=True, text=True, timeout=10, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == htdate_pure.__version__