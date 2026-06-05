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
.PHONY: help install install-dev test test-verbose run rerender open finalize all \
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
#
# NOTE: SRC must be ASCII. GNU make.exe (MinGW) on a Big5 Windows mangles
# CJK in both argv and its child env block, so a Chinese-named transcript
# path cannot survive `make run`. Use run.ps1 for CJK paths (see make.md).
ifeq (run,$(filter run,$(MAKECMDGOALS)))
ifndef SRC
$(error SRC is required. ASCII path: make run SRC="path" NAME=foo. CJK path: use .\run.ps1 "path" NAME)
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
ifeq (finalize,$(filter finalize,$(MAKECMDGOALS)))
ifndef NAME
$(error NAME is required. Usage: make finalize NAME=foo [REUSE=1])
endif
endif
ifeq (all,$(filter all,$(MAKECMDGOALS)))
ifndef SRC
$(error SRC is required. Usage: make all SRC="path" NAME=foo. ASCII path only — make.exe mangles CJK; rename the file to ASCII first.)
endif
ifndef NAME
$(error NAME is required. Usage: make all SRC="path" NAME=foo)
endif
endif

# ── Help ─────────────────────────────────────────────────────────────────
# 第一行 chcp 65001 把主控台切到 UTF-8，否則下面的繁體中文在 cp950
# 主控台會變成亂碼（make.exe / cmd 預設用系統 ANSI 編碼）。Makefile 本身存成 UTF-8。
help:
	@chcp 65001 >nul
	@echo ============================================================
	@echo   會議記錄 Pipeline -- Makefile 指令說明
	@echo ============================================================
	@echo.
	@echo 【一次性安裝】
	@echo   make install            建立 .venv 並安裝執行套件
	@echo   make install-dev        安裝執行 + 測試套件
	@echo.
	@echo 【主要流程】
	@echo   make all SRC="檔案" NAME=名稱 [MODEL=模型]
	@echo       一鍵完成：先跑 LLM 產生會議記錄，再進入互動 Q^&A，最後開 Outlook 草稿。
	@echo       範例:  make all SRC="src\mtg.txt" NAME=2026q2_sync
	@echo.
	@echo   make run SRC="檔案" [NAME=名稱] [MODEL=模型]
	@echo       只跑 LLM pipeline，產生 minutes.html 與 minutes_email.html。
	@echo       自動辨識 Android(.txt, MM:SS) 與 Teams(.vtt) 格式；NAME 省略時取檔名。
	@echo       範例:  make run SRC="src\mtg.txt" NAME=2026q2_sync
	@echo       範例:  make run SRC="src\mtg.txt" NAME=demo MODEL=claude-opus-4-8
	@echo.
	@echo   make finalize NAME=名稱 [REUSE=1]
	@echo       互動 Q^&A（不跑 LLM）：逐項確認會議資訊與每條決議 / action，
	@echo       未知欄位留白不推論；最後開啟可編輯的 Outlook 草稿（不寄出）。
	@echo       REUSE=1 沿用上次 finalized.json 的答案當預設。
	@echo       範例:  make finalize NAME=2026q2_sync
	@echo.
	@echo   make rerender NAME=名稱  重新產生輸出檔（讀快取，不跑 LLM）
	@echo   make open NAME=名稱      用瀏覽器開啟 out\^<名稱^>\minutes.html
	@echo.
	@echo 【路徑注意（重要）】
	@echo   SRC 必須是英文(ASCII)路徑；make.exe 會弄亂中文路徑。
	@echo   請先把逐字稿改成英文檔名；中文路徑請改用 PowerShell:
	@echo       .\run.ps1 "中文路徑.txt" 名稱
	@echo.
	@echo 【測試】
	@echo   make test               執行 pytest
	@echo   make test-verbose       pytest -v
	@echo.
	@echo 【清理（會刪檔）】
	@echo   make clean              刪除 __pycache__ 與各種快取
	@echo   make clean-out          刪除 out\（所有產出）
	@echo   make clean-logs         刪除 log\（日誌）
	@echo   make clean-all          以上全部

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
# scripts/_make_run.py is the space-safe arg parser. SRC is quoted because
# even ASCII paths may contain spaces. CJK paths can't come through make
# (make.exe mangles them) — use .\run.ps1 instead.
# MODEL is optional: overrides .env's medium (on-prem) for this run, e.g.
# `make run SRC="x.txt" NAME=foo MODEL=claude-opus-4-7` for a cloud model.
run:
	$(PY) scripts/_make_run.py "$(SRC)" $(NAME) $(if $(MODEL),MODEL=$(MODEL))

rerender:
	$(PY) -m script.main process "(rerender)" --name $(NAME) --rerender

open:
	@if not exist "out\$(NAME)\minutes.html" (echo ERROR: out\$(NAME)\minutes.html not found. Run the pipeline first. & exit /b 1)
	@start "" "out\$(NAME)\minutes.html"

# finalize is INTERACTIVE (terminal Q&A). It reads out\<NAME>\intermediate\
# synthesized.json from a prior `make run`, so it needs only NAME (ASCII) —
# the CJK transcript path is never passed, sidestepping make.exe's mangling.
# Subject defaults to NAME (override it in the Q&A). REUSE=1 reuses the
# previous finalized.json answers as defaults.
finalize:
	@if not exist "out\$(NAME)\intermediate\synthesized.json" (echo ERROR: out\$(NAME)\intermediate\synthesized.json not found. Run `make run` first. & exit /b 1)
	$(PY) -m script.main finalize "$(NAME)" --name "$(NAME)" $(if $(REUSE),--reuse)

# One-key: full LLM pipeline THEN interactive finalize (Q&A -> Outlook draft).
# Runs `run` then `finalize` in order; if the pipeline fails, make aborts
# before finalize. ASCII SRC only (make.exe mangles CJK — rename to ASCII).
# MODEL optional (forwarded to the run step). Both SRC and NAME are required
# so finalize can locate out\<NAME>\ deterministically.
all: run finalize

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
