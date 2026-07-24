---
name: meetingminutes
description: Convert a prepared meeting transcript + audio in a folder into structured meeting minutes. Use when the user wants to turn a transcript/recording into minutes, or says "轉會議記錄" / "做會議記錄" / "/meetingminutes". ALWAYS asks which LLM (company on-prem vs the Claude session) before touching anything.
---

# Meeting Minutes — Entry Skill

<HARD-GATE>
Before reading, opening, catting, or grepping ANY transcript or audio file, and
before running any pipeline command, you MUST ask the user this question and
wait for an answer:

  「本次會議轉檔要使用公司 LLM（default，地端、機密安全）還是 Claude 目前使用的 LLM？」

Do not skip it, do not assume a default, do not read the transcript "just to
check first". The answer determines whether you are even ALLOWED to open the
files. Asking is the first action every time, including when resuming.
</HARD-GATE>

## After the user answers

### If "company" (公司 LLM) — SECURITY-CRITICAL

The transcript and audio must NEVER be read by you (the cloud session).

1. Write the privacy lock so the PreToolUse hook enforces this mechanically.
   In the meeting folder, create `.minutes-company-lock.json` listing the
   transcript and audio as ABSOLUTE paths:
   `{"protected": ["<absolute transcript path>", "<absolute audio path if present>"]}`
   Determine the paths from a directory listing (listing a folder is allowed) —
   do NOT open the files. Absolute paths are required so the hook matches them
   regardless of how a later tool call spells the path.
   The "audio" is whatever same-stem recording sits next to the transcript: a
   plain audio file (`.m4a/.mp3/.wav/.ogg/.aac`) OR a video container
   (`.mp4/.mov/.mkv` — Teams/Zoom exports). List that recording in the lock.
   The pipeline auto-extracts the audio track from a video (never copies the
   whole video), so a Teams `.mp4` yields the ▶ clips just like an `.m4a`.

2. **(New) Auto-generate `run.bat`** in the meeting folder so the user can
   double-click instead of copying commands manually.
   Detect ffmpeg's bin dir first via `Get-Command ffmpeg` (PowerShell), then
   write `run.bat` with ffmpeg's path hardcoded. The `.bat` must:
   - Use `set "PATH=%PATH%;<ffmpeg-bin>"` at the top so ffmpeg is available
   - Check if `out/<name>/intermediate/synthesized.json` exists → skip `process`
   - Run: validate → process (--llm company) → edit
   - Use `start ""` for edit so it opens in a new window
   - `pause` at the end so the window stays open
   - Handle `%` signs correctly (use `%%` in `.bat` files for literal `%`)
   - Use `enabledelayedexpansion` and `!var!` for dynamic variable access
   Reference the existing `run.bat` at the bottom of this file for the exact
   template to follow — keep the structure in sync when updating the skill.

3. After writing both files, tell the user:
   「隱私鎖已建立 ✅
   請到會議資料夾 **雙擊 `run.bat`** 即可依序完成驗證、管線、開編輯頁。
   （亦可手動：`python -m script.main process ... --llm company`）
   完成後告訴我，我幫您確認產出。」

### If "claude" (Claude 目前的 LLM) — engine B

You are allowed to read the transcript. Do NOT create the lock file.

1. Read the transcript yourself.
2. Produce the intermediate JSON the pipeline expects, writing to
   `out/<name>/intermediate/`: `minutes.json` (MeetingMinutes),
   `review.json` (ReviewResult), `synthesized.json` (SynthesizedMinutes),
   matching the pydantic schemas in `script/schemas.py`.
2b. Validate the three files against the schemas BEFORE rendering (LLM-free):
   `python -m script.main check-json "<name>"`
   Fix any file it reports as ❌ — common mistakes: a required field missing, a
   wrong type (e.g. a list written as a string), or a JSON syntax error (it
   reports the line/column). Re-run check-json until all three are OK. (The
   `--rerender` in the next step also preflights this and refuses with the same
   check on a bad file, so a mistake never reaches a raw traceback.)
3. Re-render + audit without calling any LLM:
   `python -m script.main process "<transcript path>" --name "<name>" --rerender`
   (The `--rerender` path recomputes the mechanical audit and re-renders HTML.)
4. Open the editable page: `python -m script.main edit "<name>"` (same as the
   company route — edit in the browser, then export to an Outlook draft).

## Notes
- The CLI refuses a full run without `--llm` (backstop). The PreToolUse hook
  blocks reads of locked files (mechanical isolation): it finds the lock by
  walking up from the file being read, so it works even when your working
  directory is the repo root and the meeting folder is elsewhere. This skill
  asking first is the primary gate. All three must agree before confidential
  content moves.
- The ▶ audio clips (audio extraction from `.mp4` and per-anchor cutting) need
  `ffmpeg` on PATH. Without it the minutes still generate fully; only the clips
  are skipped (`stage.audio_asset` warns error=`audio-track extraction failed` /
  `audio_clips count=0`).
- GOTCHA — background runs don't inherit your interactive PATH. `ffmpeg -version`
  can succeed in your terminal yet the `process` run still fails extraction,
  because the pipeline was launched in a fresh/background shell that never saw
  ffmpeg's directory. So checking `ffmpeg -version` alone is NOT enough. Instead,
  prepend ffmpeg's bin dir to PATH **in the very same command** that runs the
  pipeline, e.g. (Windows PowerShell):
  `$env:Path += ";<path-to-ffmpeg-bin>"; python -m script.main process ...`
  (bash: `PATH="$PATH:<path-to-ffmpeg-bin>" python -m script.main process ...`).
  Find `<path-to-ffmpeg-bin>` from the machine's ffmpeg install (do not hardcode
  one person's path — each colleague may install it elsewhere). If a run already
  produced `count=0` with `audio-track extraction failed`, just re-run `process`
  with ffmpeg prepended to PATH; the LLM stages re-run but the ▶ clips then cut.
- 會議記錄**不輸出「決議」區塊**（team 的偏好：多數決議沒內容，只保留議題標題＋討論摘要＋
  Action）。決議已從所有 render 模板（minutes / 兩個 email / edit 頁）與機械稽核
  （`decision_nonempty` gate）移除；`decisions` 欄位仍留在 schema/合成輸出裡（不顯示、
  不稽核，向後相容舊 JSON）。不要重新加回決議區塊，除非使用者明確要求。
- 音檔 zip ＋ co-locate：**edit 頁匯出成功後會自動**把已審閱的 `email.html` ＋
  `minutes_audio.zip` 放回會議資料夾（逐字稿旁），不需再手動跑 `audiozip`。機制：`process`/
  `--rerender` 會把逐字稿絕對路徑寫進 `out/<name>/source.json`；`edit_server.handle_export`
  匯出後讀它、best-effort 建 zip 並 co-locate（失敗不影響匯出）。zip 內是
  `email_with_audio.html`（相對引用 ＋ 每段 clip）——切 clip 需要 ffmpeg 在 PATH（啟動 `edit`
  時就要有），否則 zip 仍產出但無 ▶。核心 `script/audio_zip.py`。
- `python -m script.main audiozip "<逐字稿路徑>"`：**手動**版本，額外跑完整 `verify_zip`
  （ffprobe 可聽性 ＋ Playwright 每段可播放 E2E，`script/audio_verify.py`）。匯出時的自動
  co-locate 為求穩健**略過**這個瀏覽器 E2E；要嚴格驗證每段可播放時才用這支獨立指令。

## `run.bat` 模板

使用公司 LLM 時，Claude 會在會議資料夾自動產生此檔。雙擊執行即可依序完成驗證、管線、
開編輯頁。修改時請同步更新 Step 2 的規範。

```bat
@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

title 會議管線 - <NAME>
set REPO_ROOT=<D:\path\to\repo>
set NAME=<MEETING_NAME>
set TRANSCRIPT=%~dp0%NAME%.vtt

:: ── ffmpeg PATH（Claude 自動偵測寫入）──
set "PATH=%PATH%;<D:\path\to\ffmpeg\bin>"

:: ── Python ──
set PY=%REPO_ROOT%\.venv\Scripts\python.exe

:CHECK
if exist "%REPO_ROOT%\out\%NAME%\intermediate\synthesized.json" (
    echo [SKIP] synthesized.json 已存在，跳過 process
    goto :EDIT
)

echo [1/3] 驗證逐字稿…
"%PY%" -m script.main validate "%TRANSCRIPT%"
if !ERRORLEVEL! neq 0 (
    echo [錯誤] validate 失敗 & pause & exit /b !ERRORLEVEL!
)

echo [2/3] 執行管線（公司 LLM）…
"%PY%" -m script.main process "%TRANSCRIPT%" --name "%NAME%" --llm company
if !ERRORLEVEL! neq 0 (
    echo [錯誤] process 失敗 & pause & exit /b !ERRORLEVEL!
)

:EDIT
echo [開啟] 編輯頁…
start "" "%PY%" -m script.main edit "%NAME%"
echo.
pause
```
