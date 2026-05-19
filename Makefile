# Meeting Minutes pipeline — common workflows.
#
# This Makefile uses the GNU make standard KEY=VALUE syntax. On native
# Windows cmd/PowerShell without GNU make, use ./make.cmd instead, which
# uses POSITIONAL args (CMD's KEY=VALUE handling is fragile with quoted
# paths containing spaces / non-ASCII characters).
#
#   GNU make:   make run FILE="src/transcript.txt" NAME=q2
#   Windows:    .\make.cmd run "src\transcript.txt" q2
#
# Requires (for this Makefile): GNU Make + bash. On Windows, install via:
#   - Git for Windows (ships make+bash)
#   - scoop install make
#
# Usage examples:
#   make help                                  # list all targets
#   make install                               # set up .venv + runtime deps
#   make install-dev                           # + test deps
#   make test                                  # run pytest
#   make run FILE="src/transcript.txt"         # full pipeline (auto-name from basename)
#   make run FILE="transcript.txt" NAME=q2     # explicit output folder name
#   make rerender NAME=q2_planning             # re-render outputs from cached JSON (no LLM)
#   make open NAME=q2_planning                 # open the HTML output in default browser
#   make clean                                 # remove pycache + .pytest_cache
#   make clean-out                             # remove out/  (DESTRUCTIVE: all meeting results)
#   make clean-logs                            # remove log/

PY     := .venv/Scripts/python
PIP    := .venv/Scripts/pip
PYTEST := .venv/Scripts/pytest

.DEFAULT_GOAL := help
.PHONY: help install install-dev test test-verbose run rerender open \
        clean clean-out clean-logs clean-all show-cost-summary

help:
	@echo "Meeting Minutes pipeline — make targets"
	@echo ""
	@echo "Setup:"
	@echo "  install         Create .venv and install runtime deps"
	@echo "  install-dev     Install runtime + test deps"
	@echo ""
	@echo "Run:"
	@echo "  test                              Run all pytest"
	@echo "  test-verbose                      pytest with -v"
	@echo "  run FILE=path [NAME=...]"
	@echo "                                    Full pipeline. NAME defaults to FILE basename."
	@echo "  rerender NAME=...                 Re-render outputs (HTML + MD) from cached"
	@echo "                                    minutes.json + review.json (no LLM)"
	@echo "  open NAME=...                     Open out/<NAME>/minutes.html in browser"
	@echo ""
	@echo "Clean (DESTRUCTIVE):"
	@echo "  clean        Remove pycache + .pytest_cache"
	@echo "  clean-out    Remove out/  (every meeting's transcript/minutes/etc)"
	@echo "  clean-logs   Remove log/"
	@echo "  clean-all    All three above"

# ---------- Setup ----------

install:
	python -m venv .venv
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt

install-dev:
	python -m venv .venv
	$(PIP) install -U pip
	$(PIP) install -r requirements-dev.txt

# ---------- Test ----------

test:
	$(PYTEST) --tb=short

test-verbose:
	$(PYTEST) -v

# ---------- Pipeline ----------

# Build optional --name flag
NAME_FLAG    := $(if $(NAME),--name $(NAME),)

run:
	@if [ -z "$(FILE)" ]; then \
		echo "ERROR: FILE is required."; \
		echo "Usage: make run FILE=path/to/transcript.txt [NAME=...]"; \
		exit 1; \
	fi
	$(PY) -m script.main "$(FILE)" $(NAME_FLAG)

rerender:
	@if [ -z "$(NAME)" ]; then \
		echo "ERROR: NAME is required."; \
		echo "Usage: make rerender NAME=<output_folder_name>"; \
		exit 1; \
	fi
	$(PY) -m script.main "(rerender)" --name $(NAME) --rerender

open:
	@if [ -z "$(NAME)" ]; then \
		echo "ERROR: NAME is required."; \
		echo "Usage: make open NAME=<output_folder_name>"; \
		exit 1; \
	fi
	@if [ ! -f "out/$(NAME)/minutes.html" ]; then \
		echo "ERROR: out/$(NAME)/minutes.html not found. Run the pipeline first."; \
		exit 1; \
	fi
	@start "" "out/$(NAME)/minutes.html" 2>/dev/null || \
		open "out/$(NAME)/minutes.html" 2>/dev/null || \
		xdg-open "out/$(NAME)/minutes.html" 2>/dev/null || \
		echo "Open manually: out/$(NAME)/minutes.html"

# ---------- Cleanup ----------

clean:
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache .mypy_cache .ruff_cache
	@echo "Removed __pycache__ + .pytest_cache + .mypy_cache + .ruff_cache"

clean-out:
	@rm -rf out/
	@echo "Removed out/  (all meeting results gone)"

clean-logs:
	@rm -rf log/
	@echo "Removed log/"

clean-all: clean clean-out clean-logs
