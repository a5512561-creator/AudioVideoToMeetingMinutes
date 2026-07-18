# P2 — Entry Point + Privacy Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Force an explicit "company LLM vs Claude LLM" choice at the start of every minutes run, and mechanically guarantee that in company-LLM mode the transcript/audio are never read by the cloud Claude session.

**Architecture:** Three layers of defense plus a privacy-safe validator. (1) A `/minutes` project skill whose HARD-GATE asks the LLM-choice question before anything else. (2) A CLI backstop: `process` refuses to run its LLM full-run without an explicit `--llm company` acknowledgment. (3) A PreToolUse hook that blocks the cloud session from reading files registered as protected while a company-mode lock is active. The format/content check (design point 2) is done by a pure-Python validator that prints only metadata to stdout — never transcript content — so the check itself leaks nothing.

**Tech Stack:** Python 3.11+, pydantic v2, typer, pytest. Claude Code harness (project skill markdown + settings.json PreToolUse hook).

**Design reference:** `docs/superpowers/specs/2026-07-18-minutes-workflow-design.md` §2. Depends on P1 (already merged to main): schemas, pipeline, audit stage.

**SECURITY-CRITICAL:** In company-LLM mode the transcript and audio must never be ingested by any cloud LLM (the Claude session). Layers 1–3 each enforce this independently so no single miss breaks the guarantee.

---

## File Structure

- **Create** `script/validate_source.py` — pure-Python format/content validator over a transcript file + sibling audio. Emits a metadata-only report (counts, booleans, first/last timestamp). NEVER returns or prints transcript content. One responsibility: readiness checking without LLM.
- **Create** `hooks/minutes_privacy_guard.py` — PreToolUse hook. A pure decision function `should_block(tool_name, tool_input, lock)` + a thin stdin→stdout `main()`. One responsibility: deny tool calls that would read protected paths while the company-mode lock is active.
- **Create** `.claude/skills/minutes/SKILL.md` — the `/minutes` project skill with the HARD-GATE LLM-choice question and the two routes (company / claude).
- **Create/Modify** `.claude/settings.json` — register the PreToolUse hook (this file is committed; `settings.local.json` stays user-local).
- **Modify** `script/main.py` — add a `validate` command (runs the validator) and add the required `--llm` backstop to `process`.
- **Test** `tests/test_validate_source.py` (new), `tests/test_minutes_privacy_guard.py` (new), `tests/test_main.py` (extend).

**Lock convention (shared contract across layers):** company mode writes a lock file `.minutes-company-lock.json` in the meeting folder (the folder holding the transcript + audio). It contains `{"protected": ["<abs-or-cwd-relative path>", ...]}` listing the transcript and audio files. The `/minutes` skill writes it when the user picks company mode; the PreToolUse hook reads it to decide what to block; `process --llm company` also writes/refreshes it. Picking `claude` mode does NOT create a lock (the session is allowed to read).

---

## Task 1: Pure-Python source validator (privacy-safe)

**Files:**
- Create: `script/validate_source.py`
- Test: `tests/test_validate_source.py`

The validator answers "is this transcript ready to process?" using only Python
— no LLM. Crucially, its report contains only metadata, so the cloud session
may read the report's stdout without ever seeing transcript text.

- [ ] **Step 1: Write the failing test**

Create `tests/test_validate_source.py`:

```python
from pathlib import Path
from script.validate_source import validate_source, SourceReport


def _write(p: Path, text: str) -> Path:
    p.write_text(text, encoding="utf-8")
    return p


def test_valid_transcript_reports_ok(tmp_path):
    src = _write(tmp_path / "mtg.txt",
                 "00:00 大家好\n00:12 開始討論 KPI\n01:05 結論\n")
    r = validate_source(str(src))
    assert isinstance(r, SourceReport)
    assert r.exists is True
    assert r.utf8 is True
    assert r.timestamp_lines >= 3
    assert r.first_timestamp == "00:00"
    assert r.last_timestamp == "01:05"
    assert r.non_empty is True
    assert r.ok is True
    assert r.problems == []


def test_missing_file_is_not_ok(tmp_path):
    r = validate_source(str(tmp_path / "nope.txt"))
    assert r.exists is False
    assert r.ok is False
    assert any("找不到" in p for p in r.problems)


def test_no_timestamps_flags_problem(tmp_path):
    src = _write(tmp_path / "flat.txt", "大家好\n開始討論\n沒有時間戳\n")
    r = validate_source(str(src))
    assert r.timestamp_lines == 0
    assert r.ok is False
    assert any("時間戳" in p for p in r.problems)


def test_report_contains_no_transcript_text(tmp_path):
    secret = "極機密專案代號 BLUEFALCON"
    src = _write(tmp_path / "s.txt", f"00:00 {secret}\n00:10 結束\n")
    r = validate_source(str(src))
    dumped = r.model_dump_json()
    # Metadata only — the report must never carry transcript content.
    assert secret not in dumped
    assert "BLUEFALCON" not in dumped


def test_detects_sibling_audio(tmp_path):
    _write(tmp_path / "mtg.txt", "00:00 hi\n00:10 bye\n")
    (tmp_path / "mtg.m4a").write_bytes(b"\x00\x01\x02")
    r = validate_source(str(tmp_path / "mtg.txt"))
    assert r.has_sibling_audio is True
    assert r.audio_ext == ".m4a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_validate_source.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'script.validate_source'`

- [ ] **Step 3: Write minimal implementation**

Create `script/validate_source.py`:

```python
"""Privacy-safe, LLM-free readiness check for a meeting transcript + audio.

Answers "is this source ready to process?" using pure Python. The returned
SourceReport carries ONLY metadata (counts, booleans, first/last timestamp) —
never transcript text — so the check can run and its stdout be read by the
cloud session without exposing any confidential content.
"""
import re
from pathlib import Path

from pydantic import BaseModel

from script.audio_assets import find_sibling_audio

# MM:SS or HH:MM:SS at the start of a line (optionally bracketed), matching the
# recorder.google.com transcript style the pipeline already relies on.
_TS_RE = re.compile(r"^\s*\[?(\d{1,2}:\d{2}(?::\d{2})?)\b")

# A meeting with almost no content is not worth processing; guards against a
# user pointing at an empty or near-empty file.
_MIN_TIMESTAMP_LINES = 1


class SourceReport(BaseModel):
    path: str
    exists: bool = False
    utf8: bool = False
    non_empty: bool = False
    timestamp_lines: int = 0
    first_timestamp: str = ""
    last_timestamp: str = ""
    has_sibling_audio: bool = False
    audio_ext: str = ""
    ok: bool = False
    problems: list[str] = []


def validate_source(src: str) -> SourceReport:
    p = Path(src)
    report = SourceReport(path=str(src))
    problems: list[str] = []

    if not p.exists():
        problems.append(f"找不到檔案：{src}")
        report.problems = problems
        return report
    report.exists = True

    try:
        text = p.read_text(encoding="utf-8")
        report.utf8 = True
    except (UnicodeDecodeError, OSError):
        problems.append("檔案不是 UTF-8 編碼或無法讀取")
        report.problems = problems
        return report

    report.non_empty = bool(text.strip())
    if not report.non_empty:
        problems.append("檔案是空的")

    stamps: list[str] = []
    for line in text.splitlines():
        m = _TS_RE.match(line)
        if m:
            stamps.append(m.group(1))
    report.timestamp_lines = len(stamps)
    if stamps:
        report.first_timestamp = stamps[0]
        report.last_timestamp = stamps[-1]
    if report.timestamp_lines < _MIN_TIMESTAMP_LINES:
        problems.append("找不到任何時間戳（MM:SS / HH:MM:SS）— 格式可能不正確")

    audio = find_sibling_audio(src)
    if audio is not None:
        report.has_sibling_audio = True
        report.audio_ext = audio.suffix.lower()

    report.ok = report.exists and report.utf8 and report.non_empty and bool(stamps)
    report.problems = problems
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_validate_source.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```
git add script/validate_source.py tests/test_validate_source.py
git commit -m "feat: privacy-safe LLM-free source validator (metadata-only report)"
```

---

## Task 2: `validate` CLI command

**Files:**
- Modify: `script/main.py` (add a `validate` command)
- Test: `tests/test_main.py` (extend)

Gives the user (and the skill) a one-liner to run the readiness check:
`python -m script.main validate <src>`. Prints the metadata report; exits
non-zero when not ok so the skill/hook flow can branch on it.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_main.py`:

```python
def test_cli_validate_ok(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    src = tmp_path / "mtg.txt"
    src.write_text("00:00 hi\n00:10 bye\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 0, result.output
    assert "OK" in result.output
    # metadata only — no transcript text echoed
    assert "hi" not in result.output


def test_cli_validate_bad_exits_nonzero(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    src = tmp_path / "flat.txt"
    src.write_text("沒有時間戳\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code != 0
    assert "時間戳" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main.py::test_cli_validate_ok -v`
Expected: FAIL (no `validate` command → non-zero exit / usage error)

- [ ] **Step 3: Write minimal implementation**

In `script/main.py`, add the import near the top:

```python
from script.validate_source import validate_source
```

And add this command (after the `process` command, before `finalize`):

```python
@app.command()
def validate(
    src: str = typer.Argument(..., help="Path to the transcript file to check."),
) -> None:
    """Check a transcript is ready to process — LLM-free, metadata only.

    Prints readiness metadata (never transcript content) and exits non-zero
    when the source is not ready. Safe to run in either LLM mode: the output
    exposes no confidential text.
    """
    r = validate_source(src)
    typer.echo(f"檔案：{r.path}")
    typer.echo(f"存在：{r.exists}  UTF-8：{r.utf8}  非空：{r.non_empty}")
    typer.echo(f"時間戳行數：{r.timestamp_lines}  範圍：{r.first_timestamp}–{r.last_timestamp}")
    typer.echo(f"同名音檔：{r.has_sibling_audio} {r.audio_ext}")
    if r.ok:
        typer.echo("結果：OK ✅")
    else:
        typer.echo("結果：NOT OK ❌")
        for p in r.problems:
            typer.echo(f"  - {p}")
        raise typer.Exit(code=1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main.py -v`
Expected: PASS (new validate tests + all existing main tests green)

- [ ] **Step 5: Commit**

```
git add script/main.py tests/test_main.py
git commit -m "feat: add `validate` CLI command (LLM-free readiness check)"
```

---

## Task 3: CLI backstop — required `--llm` on `process`

**Files:**
- Modify: `script/main.py` (`process` command)
- Test: `tests/test_main.py` (extend + update existing process tests)

The full-run `process` must not proceed without an explicit LLM-choice
acknowledgment. `--llm company` proceeds with the on-prem engine A. `--llm
claude` errors, directing the user to the engine-B flow (let the session write
the JSON, then `--rerender`). `--rerender` runs no LLM, so it is exempt.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_main.py`:

```python
def test_cli_process_requires_llm_choice(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline"):
        result = runner.invoke(app, ["process", "transcript.txt", "--name", "t"])
    # no --llm on a full run -> refuse
    assert result.exit_code != 0
    assert "--llm" in result.output


def test_cli_process_company_proceeds(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(
            app, ["process", "transcript.txt", "--name", "t", "--llm", "company"])
    assert result.exit_code == 0, result.output
    run.assert_called_once()


def test_cli_process_claude_refuses_fullrun(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(
            app, ["process", "transcript.txt", "--name", "t", "--llm", "claude"])
    assert result.exit_code != 0
    assert "rerender" in result.output.lower() or "engine" in result.output.lower()
    run.assert_not_called()


def test_cli_rerender_exempt_from_llm_choice(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(
            app, ["process", "transcript.txt", "--name", "t", "--rerender"])
    # --rerender calls no LLM -> allowed without --llm
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["rerender_only"] is True
```

You must also update the existing full-run process tests that now need
`--llm company` to reach `run_pipeline`: `test_cli_passes_basic_args`,
`test_cli_model_override`, `test_cli_no_model_keeps_env_default`. Add
`"--llm", "company"` to their `runner.invoke(app, [...])` arg lists.
(`test_cli_rerender_flag` uses `--rerender` so it stays exempt;
`test_cli_rejects_removed_diarize_flag` still errors for a different reason and
needs no change.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main.py::test_cli_process_requires_llm_choice -v`
Expected: FAIL (process currently has no `--llm` and proceeds without it)

- [ ] **Step 3: Write minimal implementation**

In `script/main.py`, add near the top:

```python
from enum import Enum


class LlmChoice(str, Enum):
    company = "company"
    claude = "claude"
```

Change the `process` signature to add the option (place it after `model`):

```python
    llm: LlmChoice | None = typer.Option(
        None, "--llm",
        help="Which LLM will process this meeting: 'company' (on-prem, "
             "confidential-safe) or 'claude' (the Claude session writes the "
             "JSON itself — use the /minutes engine-B flow, not this full run). "
             "Required for a full run; not needed with --rerender.",
    ),
```

Then at the start of the `process` body (before building `settings`), insert
the backstop:

```python
    if not rerender:
        if llm is None:
            typer.echo(
                "拒絕執行：整檔轉換必須明確指定 --llm。\n"
                "  --llm company  用公司地端 LLM（機密安全，逐字稿不出公司）\n"
                "  --llm claude   改走 /minutes 的 engine-B 流程（由 Claude 本人寫 JSON 後 --rerender）",
                err=False,
            )
            raise typer.Exit(code=2)
        if llm is LlmChoice.claude:
            typer.echo(
                "--llm claude 不經由本 full-run 路徑。請用 /minutes skill 的 "
                "engine-B 流程：讓 Claude 讀逐字稿、寫出 intermediate JSON，"
                "再執行 `process <src> --rerender`。",
                err=False,
            )
            raise typer.Exit(code=2)
```

Leave the rest of `process` unchanged (it already builds `settings` and calls
`run_pipeline`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main.py -v`
Expected: PASS (new backstop tests + updated existing tests all green)

- [ ] **Step 5: Commit**

```
git add script/main.py tests/test_main.py
git commit -m "feat: require explicit --llm choice on process full run (privacy backstop)"
```

---

## Task 4: PreToolUse privacy-guard hook (decision core)

**Files:**
- Create: `hooks/minutes_privacy_guard.py`
- Test: `tests/test_minutes_privacy_guard.py`

The hook denies any tool call that would read a protected file while a
company-mode lock is active. The pure decision function is fully unit-tested;
the stdin/stdout `main()` is a thin adapter the harness invokes.

- [ ] **Step 1: Write the failing test**

Create `tests/test_minutes_privacy_guard.py`:

```python
from hooks.minutes_privacy_guard import should_block


LOCK = {"protected": ["/proj/mtg/mtg.vtt", "/proj/mtg/mtg.m4a"]}


def test_blocks_read_of_protected_transcript():
    blocked, reason = should_block("Read", {"file_path": "/proj/mtg/mtg.vtt"}, LOCK)
    assert blocked is True
    assert "company" in reason.lower() or "公司" in reason


def test_blocks_bash_command_touching_protected_audio():
    blocked, _ = should_block(
        "Bash", {"command": "cat /proj/mtg/mtg.m4a | base64"}, LOCK)
    assert blocked is True


def test_allows_unrelated_read():
    blocked, _ = should_block("Read", {"file_path": "/proj/other/readme.md"}, LOCK)
    assert blocked is False


def test_allows_everything_when_no_lock():
    blocked, _ = should_block("Read", {"file_path": "/proj/mtg/mtg.vtt"}, None)
    assert blocked is False
    blocked, _ = should_block("Read", {"file_path": "/proj/mtg/mtg.vtt"}, {"protected": []})
    assert blocked is False


def test_grep_and_glob_over_protected_path_blocked():
    blocked, _ = should_block("Grep", {"path": "/proj/mtg/mtg.vtt"}, LOCK)
    assert blocked is True


def test_path_normalisation_matches_mixed_separators():
    lock = {"protected": ["C:/proj/mtg/mtg.vtt"]}
    blocked, _ = should_block("Read", {"file_path": "C:\\proj\\mtg\\mtg.vtt"}, lock)
    assert blocked is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_minutes_privacy_guard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hooks.minutes_privacy_guard'`

(If needed, create an empty `hooks/__init__.py` so the package imports.)

- [ ] **Step 3: Write minimal implementation**

Create `hooks/__init__.py` (empty), then create `hooks/minutes_privacy_guard.py`:

```python
"""PreToolUse hook: block the cloud session from reading protected files while
a company-mode lock is active.

Company mode writes `.minutes-company-lock.json` ({"protected": [paths]}) into
the meeting folder. This hook denies any Read / Grep / Glob / Bash tool call
that targets one of those paths, so the confidential transcript/audio can never
be ingested by the cloud LLM. Absent lock -> never blocks.
"""
import json
import sys
from pathlib import Path

_READ_TOOLS = ("Read", "Grep", "Glob")


def _norm(p: str) -> str:
    """Normalise a path for comparison (resolve separators + case on Windows)."""
    try:
        return str(Path(p)).replace("\\", "/").casefold()
    except (TypeError, ValueError):
        return str(p or "").replace("\\", "/").casefold()


def should_block(tool_name: str, tool_input: dict, lock) -> tuple[bool, str]:
    """Return (blocked, reason). `lock` is the parsed lock dict or None."""
    protected = list((lock or {}).get("protected", []))
    if not protected:
        return False, ""
    protected_norm = {_norm(p) for p in protected}

    reason = (
        "隱私鎖：本次會議選擇公司地端 LLM，逐字稿／錄音檔不得被雲端 LLM 讀取。"
        "此檔案在保護清單中，已封鎖。"
    )

    if tool_name in _READ_TOOLS:
        target = tool_input.get("file_path") or tool_input.get("path") or ""
        if _norm(target) in protected_norm:
            return True, reason
        return False, ""

    if tool_name == "Bash":
        cmd = _norm(tool_input.get("command", ""))
        # Block if any protected path (by normalised full path or basename)
        # appears in the command string.
        for pn in protected_norm:
            if pn in cmd or Path(pn).name.casefold() in cmd:
                return True, reason
        return False, ""

    return False, ""


def _load_lock() -> dict | None:
    lock_path = Path.cwd() / ".minutes-company-lock.json"
    if not lock_path.exists():
        return None
    try:
        return json.loads(lock_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Fail CLOSED: a corrupt lock in a company-mode folder must not silently
        # disable protection. Treat as "everything protected in this folder".
        return {"protected": ["*"]}


def main() -> int:
    """Harness entry: read the tool call from stdin, block if needed.

    PreToolUse contract: exit code 2 blocks the tool call and shows stderr to
    Claude; exit code 0 allows it.
    """
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # can't parse -> don't interfere
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    lock = _load_lock()

    # Wildcard lock (corrupt file, fail-closed): block all read-ish tools.
    if lock == {"protected": ["*"]} and tool_name in _READ_TOOLS + ("Bash",):
        sys.stderr.write("隱私鎖檔毀損，為安全起見封鎖所有讀取。請檢查 .minutes-company-lock.json。")
        return 2

    blocked, reason = should_block(tool_name, tool_input, lock)
    if blocked:
        sys.stderr.write(reason)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_minutes_privacy_guard.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```
git add hooks/__init__.py hooks/minutes_privacy_guard.py tests/test_minutes_privacy_guard.py
git commit -m "feat: PreToolUse privacy-guard hook decision core + fail-closed lock"
```

---

## Task 5: Wire the harness — `/minutes` skill + settings.json hook (integration + manual verify)

**Files:**
- Create: `.claude/skills/minutes/SKILL.md`
- Create/Modify: `.claude/settings.json`

This task wires the two harness pieces. There is no pytest for skill triggering
or live hook execution — those are verified manually (steps at the end). Keep
the content exactly as specified.

- [ ] **Step 1: Create the `/minutes` skill**

Create `.claude/skills/minutes/SKILL.md`:

```markdown
---
name: minutes
description: Convert a prepared meeting transcript + audio in a folder into structured meeting minutes. Use when the user wants to turn a transcript/recording into minutes, or says "轉會議記錄" / "做會議記錄" / "/minutes". ALWAYS asks which LLM (company on-prem vs the Claude session) before touching anything.
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
   In the meeting folder, create `.minutes-company-lock.json`:
   `{"protected": ["<transcript path>", "<audio path if present>"]}`
   (Use the actual file paths. If you cannot determine them without reading the
   folder listing, list the folder — directory listing is allowed — but do NOT
   open the files.)
2. Run the LLM-free readiness check and read only its metadata output:
   `python -m script.main validate "<transcript path>"`
3. If it reports OK, run the on-prem pipeline:
   `python -m script.main process "<transcript path>" --name "<name>" --llm company`
4. Everything (map/reduce/review/synth/audit) runs on the company endpoint. You
   never open the transcript; you only read command stdout.

### If "claude" (Claude 目前的 LLM) — engine B

You are allowed to read the transcript. Do NOT create the lock file.

1. Read the transcript yourself.
2. Produce the intermediate JSON the pipeline expects, writing to
   `out/<name>/intermediate/`: `minutes.json` (MeetingMinutes),
   `review.json` (ReviewResult), `synthesized.json` (SynthesizedMinutes),
   matching the pydantic schemas in `script/schemas.py`.
3. Re-render + audit without calling any LLM:
   `python -m script.main process "<transcript path>" --name "<name>" --rerender`
   (The `--rerender` path recomputes the mechanical audit and re-renders HTML.)

## Notes
- The CLI refuses a full run without `--llm` (backstop). The PreToolUse hook
  blocks reads of locked files (mechanical isolation). This skill asking first
  is the primary gate. All three must agree before confidential content moves.
```

- [ ] **Step 2: Register the PreToolUse hook in `.claude/settings.json`**

If `.claude/settings.json` does not exist, create it with exactly:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Grep|Glob|Bash",
        "hooks": [
          {
            "type": "command",
            "command": ".venv/Scripts/python.exe hooks/minutes_privacy_guard.py"
          }
        ]
      }
    ]
  }
}
```

If it already exists, merge this `PreToolUse` entry into the existing `hooks`
object without dropping any current keys. (Do NOT put this in
`settings.local.json` — the hook must be shared/committed so it protects every
checkout.)

- [ ] **Step 3: Sanity-check the hook runs**

Simulate a blocked call manually (PowerShell):

```
cd <a temp folder>
'{"protected": ["' + (Resolve-Path .).Path.Replace('\','/') + '/secret.vtt"]}' | Out-File -Encoding utf8 .minutes-company-lock.json
'{"tool_name":"Read","tool_input":{"file_path":"' + (Resolve-Path .).Path.Replace('\','/') + '/secret.vtt"}}' | .venv\Scripts\python.exe <repo>\hooks\minutes_privacy_guard.py; echo "exit=$LASTEXITCODE"
```

Expected: prints the 隱私鎖 reason to stderr and `exit=2`. Remove the temp lock
file afterward.

- [ ] **Step 4: Commit**

```
git add .claude/skills/minutes/SKILL.md .claude/settings.json
git commit -m "feat: /minutes skill (HARD-GATE LLM choice) + PreToolUse privacy hook wiring"
```

- [ ] **Step 5: Manual verification checklist (for the user, next session)**

These require the live Claude Code harness and cannot be pytest-automated:

1. In a session, type `/minutes` (or "幫我轉會議記錄") → confirm Claude asks the
   company-vs-claude question BEFORE reading anything.
2. Answer "company" → confirm a `.minutes-company-lock.json` appears in the
   meeting folder, and that asking Claude to `Read` the transcript is BLOCKED by
   the hook (隱私鎖 message).
3. Confirm `python -m script.main validate <src>` prints metadata only.
4. Confirm `python -m script.main process <src> --name x` (no `--llm`) refuses.
5. Answer "claude" in a fresh run → confirm NO lock file is created and Claude
   can read the transcript for engine B.

---

## Notes for the Implementer

- **Three independent layers.** Skill asks (primary), CLI refuses without `--llm`
  (backstop), hook blocks locked-file reads (mechanical). Do not weaken any one
  because another exists — the security guarantee is their conjunction.
- **Fail closed.** A corrupt lock file must block, never silently allow (Task 4
  `_load_lock`). A parse failure of the hook stdin allows (can't identify a
  target), which is safe because the lock-based block is the real guard.
- **Metadata-only stays metadata-only.** Never add transcript text to
  `SourceReport` or the `validate` output — its whole purpose is to be readable
  by the cloud session without leaking content.
- **Windows paths.** The hook normalises separators + case; keep that when
  editing (the repo runs on Windows; lock paths may be written with either
  separator).
- **Tasks 1–4 are pytest-verified; Task 5 is harness/manual.** Do not claim
  Task 5 "passes tests" — it has none; report it as wired + manually checked.
```
