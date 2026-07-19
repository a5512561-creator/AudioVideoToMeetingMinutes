# P5 — Engine B Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "engine B" (the Claude session writing the intermediate JSON by hand, then calling `--rerender`) robust: a friendly preflight that validates the three hand-written JSON files against the schemas and reports exactly what's wrong, instead of a raw pydantic traceback — plus a dedicated CLI check and a schema pointer for the session.

**Architecture:** A small LLM-free validator loads `intermediate/{minutes,review,synthesized}.json`, validates each against its pydantic schema, and returns a per-file OK/error report. A `check-json` CLI command surfaces it for the session to run before `--rerender`. The `--rerender` path itself gains a preflight so a shape mistake produces a clear message and clean non-zero exit rather than a stack trace. The `/meetingminutes` claude-route doc is updated to use it.

**Tech Stack:** Python 3.11+, pydantic v2, typer, pytest. No new dependencies.

**Design reference:** `docs/superpowers/specs/2026-07-18-minutes-workflow-design.md` §1 (two-engine architecture; engine B = the Claude session writes JSON then `--rerender`). Depends on P1 (schemas, audit) and the existing `--rerender` path in `script/pipeline.py`.

---

## Context: what engine B is (and what P5 adds)

Engine B is NOT Python calling a cloud API. It is the Claude Code session itself: in "claude" mode the session reads `transcript.md`, writes `intermediate/minutes.json` (`MeetingMinutes`), `intermediate/review.json` (`ReviewResult`), and `intermediate/synthesized.json` (`SynthesizedMinutes`) to match `script/schemas.py`, then runs `process <src> --rerender` (which is LLM-free: it re-renders HTML + rebuilds the mechanical audit from those cached files).

The gap P5 closes: hand-written JSON can be the wrong shape (a missing required field, a list serialized as `{items:[...]}`, a bad `priority` enum). Today `--rerender` calls `MeetingMinutes.model_validate_json(...)` directly, so a mistake crashes with a raw `pydantic.ValidationError` traceback. P5 gives the session a clean preflight + a friendly failure.

---

## File Structure

- **Create** `script/intermediate_check.py` — `validate_intermediate(out_dir) -> dict`: validate the three JSON files against their schemas, return a per-file report. One responsibility, LLM-free, no I/O beyond reading the files.
- **Modify** `script/main.py` — add a `check-json` command.
- **Modify** `script/pipeline.py` — preflight the `--rerender` path with `validate_intermediate` for a clean error.
- **Modify** `.claude/skills/meetingminutes/SKILL.md` — claude route: run `check-json` before `--rerender`; point at `script/schemas.py`.
- **Test** `tests/test_intermediate_check.py` (new), `tests/test_main.py`, `tests/test_pipeline.py`.

**Reused:** `script/schemas.py` (`MeetingMinutes`, `ReviewResult`, `SynthesizedMinutes`).

---

## Task 1: Intermediate JSON validator

**Files:**
- Create: `script/intermediate_check.py`
- Test: `tests/test_intermediate_check.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_intermediate_check.py`:

```python
from pathlib import Path

from script.schemas import (
    MeetingMinutes, ReviewResult, SynthesizedMinutes, SynthTopic,
    Conclusion, Action,
)
from script.intermediate_check import validate_intermediate


def _conc():
    return Conclusion(text="c", is_inferred=False, source_quote="q",
                      source_timestamp="00:00:01", source_speaker=None)


def _act():
    return Action(task="t", owner="o", due="d", priority="high",
                  source_quote="q", source_timestamp="00:00:02",
                  source_speaker=None, rationale="r", is_inferred=False,
                  owner_inferred=False, due_inferred=False, priority_inferred=False)


def _write_all_valid(inter: Path):
    inter.mkdir(parents=True, exist_ok=True)
    (inter / "minutes.json").write_text(
        MeetingMinutes(conclusions=[_conc()], actions=[_act()]).model_dump_json(),
        encoding="utf-8")
    (inter / "review.json").write_text(ReviewResult(notes=[]).model_dump_json(),
                                       encoding="utf-8")
    (inter / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="A", summary="s")]).model_dump_json(),
        encoding="utf-8")


def test_all_valid(tmp_path):
    inter = tmp_path / "out" / "t" / "intermediate"
    _write_all_valid(inter)
    r = validate_intermediate(tmp_path / "out" / "t")
    assert r["ok"] is True
    assert all(f["ok"] for f in r["files"].values())


def test_missing_file_reported(tmp_path):
    inter = tmp_path / "out" / "t" / "intermediate"
    _write_all_valid(inter)
    (inter / "synthesized.json").unlink()
    r = validate_intermediate(tmp_path / "out" / "t")
    assert r["ok"] is False
    assert r["files"]["synthesized"]["ok"] is False
    assert "找不到" in r["files"]["synthesized"]["error"]


def test_wrong_shape_reported(tmp_path):
    inter = tmp_path / "out" / "t" / "intermediate"
    _write_all_valid(inter)
    # minutes.json wraps the list as {items:[...]} — the exact engine-B mistake
    (inter / "minutes.json").write_text('{"conclusions": {"items": []}, "actions": []}',
                                         encoding="utf-8")
    r = validate_intermediate(tmp_path / "out" / "t")
    assert r["ok"] is False
    assert r["files"]["minutes"]["ok"] is False
    assert r["files"]["minutes"]["error"]  # a non-empty pydantic message


def test_bad_json_reported(tmp_path):
    inter = tmp_path / "out" / "t" / "intermediate"
    _write_all_valid(inter)
    (inter / "review.json").write_text("{not json", encoding="utf-8")
    r = validate_intermediate(tmp_path / "out" / "t")
    assert r["ok"] is False
    assert r["files"]["review"]["ok"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_intermediate_check.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'script.intermediate_check'`

- [ ] **Step 3: Write minimal implementation**

Create `script/intermediate_check.py`:

```python
"""LLM-free validation of the hand-written intermediate JSON (engine B).

Engine B (the Claude session) writes minutes.json / review.json /
synthesized.json to match the schemas, then runs `--rerender`. This validates
each file up front and returns a friendly per-file report so a shape mistake
surfaces clearly instead of a raw pydantic traceback.
"""
from pathlib import Path

from pydantic import ValidationError

from script.schemas import MeetingMinutes, ReviewResult, SynthesizedMinutes

# filename stem -> schema
_SCHEMAS = {
    "minutes": MeetingMinutes,
    "review": ReviewResult,
    "synthesized": SynthesizedMinutes,
}


def validate_intermediate(out_dir) -> dict:
    """Validate intermediate/{minutes,review,synthesized}.json against schemas.

    Returns {"ok": bool, "files": {stem: {"ok": bool, "error": str}}}.
    """
    inter = Path(out_dir) / "intermediate"
    files: dict[str, dict] = {}
    for stem, schema in _SCHEMAS.items():
        path = inter / f"{stem}.json"
        if not path.exists():
            files[stem] = {"ok": False, "error": f"找不到 {path}"}
            continue
        try:
            schema.model_validate_json(path.read_text(encoding="utf-8"))
            files[stem] = {"ok": True, "error": ""}
        except ValidationError as e:
            files[stem] = {"ok": False, "error": str(e)}
        except (ValueError, OSError) as e:
            files[stem] = {"ok": False, "error": f"JSON 解析失敗：{e}"}
    return {"ok": all(f["ok"] for f in files.values()), "files": files}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_intermediate_check.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```
git add script/intermediate_check.py tests/test_intermediate_check.py
git commit -m "feat: LLM-free validator for engine-B intermediate JSON"
```

---

## Task 2: `check-json` CLI command

**Files:**
- Modify: `script/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_main.py`:

```python
def test_cli_check_json_ok(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    from script.schemas import (MeetingMinutes, ReviewResult, SynthesizedMinutes,
                                SynthTopic, Conclusion, Action)
    inter = tmp_path / "out" / "t" / "intermediate"
    inter.mkdir(parents=True)
    (inter / "minutes.json").write_text(MeetingMinutes(conclusions=[], actions=[]).model_dump_json(), encoding="utf-8")
    (inter / "review.json").write_text(ReviewResult(notes=[]).model_dump_json(), encoding="utf-8")
    (inter / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="A", summary="s")]).model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["check-json", "t"])
    assert result.exit_code == 0, result.output
    assert "OK" in result.output


def test_cli_check_json_bad_exits_nonzero(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    inter = tmp_path / "out" / "t" / "intermediate"
    inter.mkdir(parents=True)
    (inter / "minutes.json").write_text("{not json", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["check-json", "t"])
    assert result.exit_code != 0
    assert "minutes" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main.py::test_cli_check_json_ok -v`
Expected: FAIL (no `check-json` command)

- [ ] **Step 3: Write minimal implementation**

In `script/main.py`, add after the `edit` command:

```python
@app.command(name="check-json")
def check_json(
    src: str = typer.Argument(..., help="Output folder name (or transcript path) under out/."),
    name: str | None = typer.Option(None, "--name"),
) -> None:
    """Validate the engine-B intermediate JSON against the schemas (LLM-free).

    Run this after writing minutes.json / review.json / synthesized.json by
    hand and before `process ... --rerender`.
    """
    from script.intermediate_check import validate_intermediate
    settings = Settings()
    base = name or Path(src).stem
    out_dir = Path(settings.out_dir) / base
    report = validate_intermediate(out_dir)
    for stem, res in report["files"].items():
        if res["ok"]:
            typer.echo(f"  {stem}.json：OK ✅")
        else:
            typer.echo(f"  {stem}.json：❌ {res['error'].splitlines()[0]}")
    if report["ok"]:
        typer.echo("結果：全部 OK — 可以跑 `process <src> --rerender`。")
    else:
        typer.echo("結果：有檔案不合 schema（見上）。修正後再跑一次 check-json。")
        raise typer.Exit(code=1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main.py -v`
Expected: PASS (check-json tests + all existing main tests green)

- [ ] **Step 5: Commit**

```
git add script/main.py tests/test_main.py
git commit -m "feat: add `check-json` CLI command for engine-B intermediate validation"
```

---

## Task 3: `--rerender` preflight (clean error, not a traceback)

**Files:**
- Modify: `script/pipeline.py` (the `if rerender_only:` block)
- Test: `tests/test_pipeline.py`

Before the rerender path loads the JSON, validate it and raise a clean
`RuntimeError` naming the offending file(s) instead of letting a raw
`ValidationError` traceback escape.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline.py`:

```python
def test_rerender_gives_clean_error_on_bad_intermediate(tmp_path):
    settings = _settings(tmp_path)
    inter = Path(settings.out_dir) / "t" / "intermediate"
    inter.mkdir(parents=True)
    # minutes.json wrong shape; review + synthesized valid
    (inter / "minutes.json").write_text('{"conclusions": {"items": []}, "actions": []}',
                                         encoding="utf-8")
    (inter / "review.json").write_text(ReviewResult(notes=[]).model_dump_json(), encoding="utf-8")
    (inter / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="t", summary="s")]).model_dump_json(),
        encoding="utf-8")
    with pytest.raises(RuntimeError, match="minutes.json"):
        run_pipeline(_src(tmp_path), settings=settings, name="t", rerender_only=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline.py::test_rerender_gives_clean_error_on_bad_intermediate -v`
Expected: FAIL — currently a raw `pydantic.ValidationError` escapes (not a `RuntimeError` matching "minutes.json").

- [ ] **Step 3: Write minimal implementation**

In `script/pipeline.py`, add the import near the top (with the other `from script...` imports):

```python
from script.intermediate_check import validate_intermediate
```

In the `if rerender_only:` block, AFTER the existing existence check that raises
`RuntimeError` for missing files and BEFORE the `minutes = MeetingMinutes.model_validate_json(...)`
loads, insert:

```python
        _report = validate_intermediate(out_dir)
        if not _report["ok"]:
            _bad = "; ".join(
                f"{stem}.json: {res['error'].splitlines()[0]}"
                for stem, res in _report["files"].items() if not res["ok"])
            raise RuntimeError(
                f"--rerender 前置檢查失敗（intermediate JSON 不合 schema）：{_bad}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -v`
Expected: PASS (new preflight test + all existing pipeline tests green — valid-JSON rerender tests still pass because the preflight passes)

- [ ] **Step 5: Commit**

```
git add script/pipeline.py tests/test_pipeline.py
git commit -m "feat: --rerender preflights intermediate JSON with a clean error"
```

---

## Task 4: Update the skill's claude route (doc)

**Files:**
- Modify: `.claude/skills/meetingminutes/SKILL.md`

No pytest — a documentation edit so engine B validates before rendering.

- [ ] **Step 1: Edit the skill**

In `.claude/skills/meetingminutes/SKILL.md`, in the "claude" route, between the
step that writes the intermediate JSON and the `--rerender` step, insert a
validation step and a schema pointer:

```markdown
2b. The exact shapes are the pydantic models in `script/schemas.py`
    (`MeetingMinutes`, `ReviewResult`, `SynthesizedMinutes`). After writing the
    three files, validate them before rendering:
    `python -m script.main check-json "<name>"`
    Fix any file it reports as ❌ (a common mistake is wrapping a list as
    `{"items": [...]}` instead of a bare array), then re-run check-json until
    all three are OK.
```

(Renumber the following `--rerender` step if needed so the sequence reads
naturally.)

- [ ] **Step 2: Commit**

```
git add .claude/skills/meetingminutes/SKILL.md
git commit -m "docs: engine-B route validates intermediate JSON before --rerender"
```

---

## Notes for the Implementer

- **LLM-free throughout.** None of P5 calls an LLM. `validate_intermediate` only reads + schema-validates the three JSON files.
- **`.claude/` is gitignored** — stage the SKILL.md edit with `git add -f`.
- **Engine B reads the schemas directly.** The session has `script/schemas.py`; `check-json` gives it a fast conformance check, and the `--rerender` preflight is the backstop so a mistake is a clean message, not a traceback.
- **Don't duplicate validation logic.** `check-json` (Task 2) and the `--rerender` preflight (Task 3) both call the single `validate_intermediate` (Task 1).
- **Windows/venv:** run pytest via `.venv\Scripts\python.exe`; use PowerShell for git (Bash is broken by an RTK hook here).
```
