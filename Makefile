# Meeting Minutes pipeline — common workflows.
#
# Requires: GNU Make + bash. On Windows, install via:
#   - Git for Windows (ships make+bash) — recommended
#   - scoop install make
#
# Usage examples:
#   make help                                # list all targets
#   make install                             # set up .venv + runtime deps
#   make install-dev                         # + test deps
#   make test                                # run pytest (96 tests, ~1 min)
#   make run FILE="src/meeting.mp4"          # full pipeline (auto-name from basename)
#   make run FILE="x.ogg" NAME=q2_planning   # explicit output folder name
#   make run FILE="x.mp4" DIARIZE=1          # force --diarize on
#   make rerender NAME=q2_planning           # re-render outputs with current speaker_map (~13s, no LLM)
#   make samples NAME=q2_planning            # re-generate speaker mp3 samples
#   make open NAME=q2_planning               # open the HTML output in default browser
#   make clean                               # remove pycache + .pytest_cache
#   make clean-out                           # remove out/  (DESTRUCTIVE: all meeting results)
#   make clean-logs                          # remove log/

PY     := .venv/Scripts/python
PIP    := .venv/Scripts/pip
PYTEST := .venv/Scripts/pytest

.DEFAULT_GOAL := help
.PHONY: help install install-dev test test-verbose run rerender samples open \
        clean clean-out clean-logs clean-all show-cost-summary

help:
	@echo "Meeting Minutes pipeline — make targets"
	@echo ""
	@echo "Setup:"
	@echo "  install         Create .venv and install runtime deps"
	@echo "  install-dev     Install runtime + test deps"
	@echo ""
	@echo "Run:"
	@echo "  test                              Run all pytest (~1 min, 96 tests)"
	@echo "  test-verbose                      pytest with -v"
	@echo "  run FILE=path [NAME=...] [DIARIZE=1]"
	@echo "                                    Full pipeline. NAME defaults to FILE basename."
	@echo "                                    DIARIZE=1 → --diarize ; DIARIZE=0 → --no-diarize"
	@echo "  rerender NAME=...                 Re-render outputs (HTML + MD) from cached"
	@echo "                                    minutes.json + speaker_map.json (~13s, no LLM)"
	@echo "  samples NAME=...                  Re-generate per-speaker mp3 samples"
	@echo "  open NAME=...                     Open out/<NAME>/minutes.html in browser"
	@echo ""
	@echo "Clean (DESTRUCTIVE):"
	@echo "  clean        Remove pycache + .pytest_cache"
	@echo "  clean-out    Remove out/  (every meeting's transcript/minutes/audio/etc)"
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

# Build optional --name and --diarize/--no-diarize flags
NAME_FLAG    := $(if $(NAME),--name $(NAME),)
DIARIZE_FLAG := $(if $(filter 1,$(DIARIZE)),--diarize,$(if $(filter 0,$(DIARIZE)),--no-diarize,))

run:
	@if [ -z "$(FILE)" ]; then \
		echo "ERROR: FILE is required."; \
		echo "Usage: make run FILE=path/to/meeting.mp4 [NAME=...] [DIARIZE=0|1]"; \
		exit 1; \
	fi
	$(PY) -m script.main "$(FILE)" $(NAME_FLAG) $(DIARIZE_FLAG)

rerender:
	@if [ -z "$(NAME)" ]; then \
		echo "ERROR: NAME is required."; \
		echo "Usage: make rerender NAME=<output_folder_name>"; \
		exit 1; \
	fi
	$(PY) -m script.main "(rerender)" --name $(NAME) --rerender

# Regenerate speaker_samples/*.mp3 from cached audio + diarization.json
samples:
	@if [ -z "$(NAME)" ]; then \
		echo "ERROR: NAME is required."; \
		echo "Usage: make samples NAME=<output_folder_name>"; \
		exit 1; \
	fi
	@if [ ! -f "out/$(NAME)/intermediate/diarization.json" ]; then \
		echo "ERROR: out/$(NAME)/intermediate/diarization.json not found."; \
		echo "Run the pipeline with --diarize first."; \
		exit 1; \
	fi
	$(PY) -c "import json; from pathlib import Path; from script.diarize import SpeakerSegment; from script.sample_extractor import extract_speaker_samples; b = Path('out/$(NAME)'); diar = json.load(open(b/'intermediate/diarization.json', encoding='utf-8')); segs = [SpeakerSegment(**s) for s in diar]; out = extract_speaker_samples(audio_path=str(b/'intermediate/audio.wav'), speakers=segs, out_dir=str(b/'speaker_samples')); print(f'wrote {len(out)} samples to out/$(NAME)/speaker_samples/')"

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
