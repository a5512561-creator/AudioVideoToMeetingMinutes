# Makefile — meeting-minutes pipeline task runner.
#
# Variable-based UX (standard Make idiom): `make TARGET VAR=value`
#   make help
#   make install                          # or make install-dev
#   make test                             # or make test-verbose
#   make run SRC="path\to\transcript.txt" NAME=q2_sync
#   make rerender NAME=q2_sync
#   make open NAME=q2_sync
#   make clean | clean-out | clean-logs | clean-all
#
# Requires GNU Make 4.x on Windows. Already shipped via WinGet on Paddy's
# box; install via `winget install ezwinports.make` if a teammate hasn't.

.DEFAULT_GOAL := help
.PHONY: help install install-dev test test-verbose run rerender open \
        clean clean-out clean-logs clean-all

# Force every recipe line through cmd.exe — otherwise GNU Make's fast-path
# tries to exec `echo.` (cmd-only blank-line syntax) and rd/s as binaries
# and crashes with "process_begin: CreateProcess failed."
SHELL := cmd.exe
.SHELLFLAGS := /c

PY     := .venv\Scripts\python.exe
PIP    := .venv\Scripts\pip.exe
# `python -m pytest` instead of `pytest.exe` — the standalone .exe shim
# sometimes returns exit 1 with no output when invoked via Make on Windows;
# the module invocation is reliable.
PYTEST := $(PY) -m pytest

# ── Required-variable guards ─────────────────────────────────────────────
# We only enforce SRC / NAME when the matching target is the actual goal.
# That way `make help` / `make test` / `make clean` keep working without
# args, while `make run` without SRC fails fast with a useful message.
ifeq (run,$(filter run,$(MAKECMDGOALS)))
ifndef SRC
$(error SRC is required. Usage: make run SRC="path\to\transcript" [NAME=foo])
endif
endif
ifeq (rerender,$(filter rerender,$(MAKECMDGOALS)))
ifndef NAME
$(error NAME is required. Usage: make rerender NAME=foo)
endif
endif
ifeq (open,$(filter open,$(MAKECMDGOALS)))
ifndef NAME
$(error NAME is required. Usage: make open NAME=foo)
endif
endif

# ── Help ─────────────────────────────────────────────────────────────────
help:
	@echo Meeting-Minutes pipeline -- Makefile targets
	@echo.
	@echo Setup:
	@echo   make install            Create .venv + install runtime deps
	@echo   make install-dev        Install runtime + test deps
	@echo.
	@echo Run:
	@echo   make test               Run pytest
	@echo   make test-verbose       pytest -v
	@echo   make run SRC="FILE" [NAME=foo]
	@echo                           Full pipeline. Auto-detects Android (MM:SS .txt)
	@echo                           and Teams (WEBVTT .vtt) -- see stage.load_transcript
	@echo                           log line for the format chosen. NAME defaults to
	@echo                           SRC basename.
	@echo   make rerender NAME=foo  Re-render outputs (no LLM calls)
	@echo   make open NAME=foo      Open out\^<NAME^>\minutes.html in browser
	@echo.
	@echo Clean (DESTRUCTIVE):
	@echo   make clean              pycache + .pytest_cache + .mypy_cache + .ruff_cache
	@echo   make clean-out          Remove out/ (all run artefacts)
	@echo   make clean-logs         Remove log/
	@echo   make clean-all          All three above

# ── Setup ────────────────────────────────────────────────────────────────
install:
	python -m venv .venv
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt

install-dev:
	python -m venv .venv
	$(PIP) install -U pip
	$(PIP) install -r requirements-dev.txt

# ── Tests ────────────────────────────────────────────────────────────────
# -p no:cacheprovider — Windows Defender occasionally holds a handle on
# .pytest_cache between runs, causing pytest to exit 255 with a cache-write
# warning even when all tests pass. Disabling the cache plugin makes the
# exit code reliably reflect test results.
test:
	$(PYTEST) -p no:cacheprovider --tb=short

test-verbose:
	$(PYTEST) -p no:cacheprovider -v

# ── Pipeline ─────────────────────────────────────────────────────────────
# scripts/_make_run.py is the existing CJK/space-safe arg parser that
# make.cmd already delegates to; we reuse it verbatim. NAME is optional
# (helper defaults it to the SRC basename).
run:
	$(PY) scripts/_make_run.py $(SRC) $(NAME)

rerender:
	$(PY) -m script.main "(rerender)" --name $(NAME) --rerender

open:
	@if not exist "out\$(NAME)\minutes.html" (echo ERROR: out\$(NAME)\minutes.html not found. Run the pipeline first. & exit /b 1)
	@start "" "out\$(NAME)\minutes.html"

# ── Clean ────────────────────────────────────────────────────────────────
clean:
	@for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
	@if exist .pytest_cache rd /s /q .pytest_cache
	@if exist .mypy_cache rd /s /q .mypy_cache
	@if exist .ruff_cache rd /s /q .ruff_cache
	@echo Removed __pycache__ + .pytest_cache + .mypy_cache + .ruff_cache

clean-out:
	@if exist out rd /s /q out
	@echo Removed out\

clean-logs:
	@if exist log rd /s /q log
	@echo Removed log\

clean-all: clean clean-out clean-logs
