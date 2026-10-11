.PHONY: install test lint format-check bench fuzz clean all help

PY ?= python3
PIP ?= $(PY) -m pip

help:
	@echo "htdate-pure — Makefile targets"
	@echo "  install       pip install -e . (editable)"
	@echo "  test          pytest -v"
	@echo "  lint          syntax-check all sources"
	@echo "  format-check  verify all .py files are syntactically valid"
	@echo "  bench         run benchmarks/run_benchmark.py vs httpdate"
	@echo "  fuzz          run tests/test_fuzz.py for the full corpus"
	@echo "  clean         remove build artifacts"

install:
	$(PIP) install -e .

test:
	$(PY) -m pytest -v

lint:
	$(PY) -m compileall -q src tests

format-check:
	$(PY) -m py_compile src/htdate_pure/*.py tests/*.py
	@echo "OK: all sources compile"

bench:
	$(PY) benchmarks/run_benchmark.py

fuzz:
	$(PY) -m pytest -v tests/test_fuzz.py

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov/
	rm -rf benchmarks/.venv_competitor/
	find . -type d -name __pycache__ -exec rm -rf {} +

all: install lint test
	@echo "htdate-pure build OK"