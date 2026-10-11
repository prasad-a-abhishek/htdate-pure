# htdate-pure benchmark

Honest comparison of zero-dep `htdate-pure` vs PyPI `httpdate` 1.2.0.

**Scope:** This is a *narrow* comparison of zero-dep HTTP-date parsing.
`httpdate` requires `leapseconds>=2023.4.0` (data table dependency)
and is therefore unusable on Pyodide / Cloudflare Workers / air-gapped CI.
`htdate-pure` is not a drop-in replacement; the goal of this benchmark
is to confirm zero-dep does not cost an order of magnitude.

## Environment

- Python: 3.11.15 (CPython)
- OS: Linux 6.12.67-linuxkit
- CPU: unknown
- Timing: `time.perf_counter()` (microsecond resolution)
- Memory: `tracemalloc` peak per iteration
- Warmup: 3 iterations, Measured: 5 iterations
- Competitor venv: isolated `benchmarks/.venv_competitor` (subprocess)

## Per-workload metrics

All `us` values are **microseconds per single call**.
All `KB` values are peak memory delta for the entire workload iteration.

| Workload | Tool | Mean (us/call) | P95 (us/call) | Peak (KB) | Iterations |
|---|---|---:|---:|---:|---:|
| single_imf_parse | htdate-pure | 22.53 | 22.33 | 2.9 | 5 |
| single_imf_parse | httpdate | 10361.85 | 10467.58 | 1.0 | 5 |
| single_imf_format | htdate-pure | 10.53 | 10.96 | 0.8 | 5 |
| single_imf_format | httpdate | 9825.82 | 10018.00 | 1.0 | 5 |
| batch_1k_parse_imf | htdate-pure | 13.02 | 13.07 | 0.6 | 5 |
| batch_1k_parse_imf | httpdate | 15.00 | 14.99 | 0.9 | 5 |
| batch_1k_format | htdate-pure | 8.94 | 9.01 | 2.0 | 5 |
| batch_1k_format | httpdate | 12.93 | 13.05 | 1.0 | 5 |
| mixed_dialects_1k | htdate-pure | 12.85 | 12.90 | 0.6 | 5 |
| mixed_dialects_1k | httpdate | 15.07 | 15.14 | 0.9 | 5 |

## Reproduce locally

```bash
cd /root/projects/htdate-pure
pip install -e .
python3 benchmarks/run_benchmark.py
```

The script will auto-bootstrap `benchmarks/.venv_competitor`
with `httpdate` (via `uv` if available, else stdlib `venv`).

