# Transcript-to-Minutes Architecture Change — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the audio→ASR→diarization front of the pipeline with a user-supplied timestamped transcript loader, while keeping speaker plumbing intact for a future speaker-labeled variant.

**Architecture:** A new `transcript_loader` normalizes `MM:SS`-block input into the existing internal `[HH:MM:SS] text` format, so chunker/agents/writers stay untouched. Audio-bound modules (`media`, `transcribe`, `diarize`, `sample_extractor`) and their config/tests are deleted. Speaker schema/prompt/`speaker_map`/review-report layout are kept.

**Tech Stack:** Python, pytest, typer, pydantic-settings, jinja2.

Spec: `doc/specs/2026-05-18-transcript-to-minutes-design.md`. Work on branch `feat/transcript-to-minutes`.

Each task ends with the full suite green so deletions never break collection. Run all pytest from repo root `D:\GitRepo\AudioVideoToMeetingMinutes-transcription2meeting` using `.venv\Scripts\python.exe -m pytest`.

---

### Task 1: transcript_loader module (new core logic, TDD)

**Files:**
- Create: `script/transcript_loader.py`
- Test: `tests/test_transcript_loader.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_transcript_loader.py`:

```python
from script.transcript_loader import normalize, load_transcript


def test_mmss_block_normalized_to_hhmmss():
    raw = "00:00\n第一段內容\n00:10\n第二段內容\n"
    assert normalize(raw) == (
        "[00:00:00] 第一段內容\n"
        "[00:00:10] 第二段內容\n"
    )


def test_h_mm_ss_timestamp_supported():
    raw = "1:02:03\n跨小時內容\n"
    assert normalize(raw) == "[01:02:03] 跨小時內容\n"


def test_multiline_block_collapsed_to_single_line():
    raw = "00:05\n第一行\n\n第二行   有空白\n"
    assert normalize(raw) == "[00:00:05] 第一行 第二行 有空白\n"


def test_leading_text_without_timestamp_gets_zero():
    raw = "開頭沒有時間戳的文字\n00:10\n後續\n"
    assert normalize(raw) == (
        "[00:00:00] 開頭沒有時間戳的文字\n"
        "[00:00:10] 後續\n"
    )


def test_timestamp_with_empty_block_is_skipped():
    raw = "00:00\n有內容\n00:10\n\n00:20\n再次有內容\n"
    assert normalize(raw) == (
        "[00:00:00] 有內容\n"
        "[00:00:20] 再次有內容\n"
    )


def test_output_compatible_with_chunker_ts_regex():
    import re
    out = normalize("3:07\nabc\n")
    assert re.match(r"^\[(\d{2}:\d{2}:\d{2})\]", out)


def test_load_transcript_reads_utf8_and_writes_dst(tmp_path):
    src = tmp_path / "in.txt"
    src.write_text("00:00\n你好\n", encoding="utf-8")
    dst = tmp_path / "out" / "transcript.md"
    load_transcript(str(src), str(dst))
    assert dst.read_text(encoding="utf-8") == "[00:00:00] 你好\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_transcript_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'script.transcript_loader'`

- [ ] **Step 3: Write minimal implementation**

Create `script/transcript_loader.py`:

```python
import re
from pathlib import Path

# Timestamp on its own line: "MM:SS" or "H:MM:SS"/"HH:MM:SS".
_TS_LINE = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$")


def _fmt(h: int, m: int, s: int) -> str:
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def normalize(text: str) -> str:
    """Normalize an MM:SS-block transcript into internal [HH:MM:SS] lines.

    EXTENSION POINT (speaker-labeled transcripts, deferred): when a real
    speaker sample is available, parse the speaker here and emit
    "[HH:MM:SS] <speaker>: <text>" — the format write_review_report_md and
    the minutes prompts already understand. Not implemented yet.
    """
    out: list[str] = []
    cur_ts = "[00:00:00]"           # leading text before any timestamp
    buf: list[str] = []

    def flush() -> None:
        joined = " ".join(" ".join(buf).split())
        if joined:
            out.append(f"{cur_ts} {joined}")
        buf.clear()

    for line in text.splitlines():
        m = _TS_LINE.match(line)
        if m:
            flush()
            g1, g2, g3 = m.group(1), m.group(2), m.group(3)
            if g3 is not None:                       # H:MM:SS
                h, mm, ss = int(g1), int(g2), int(g3)
            else:                                    # MM:SS
                h, mm, ss = 0, int(g1), int(g2)
            cur_ts = _fmt(h, mm, ss)
            continue
        if line.strip():
            buf.append(line.strip())
    flush()
    return "\n".join(out) + ("\n" if out else "")


def load_transcript(src: str, dst: str) -> None:
    raw = Path(src).read_text(encoding="utf-8", errors="replace")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_text(normalize(raw), encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_transcript_loader.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add script/transcript_loader.py tests/test_transcript_loader.py
git commit -m "feat: add transcript_loader (MM:SS blocks -> internal [HH:MM:SS])"
```

---

### Task 2: Rewire pipeline.py to the loader; remove audio stages

**Files:**
- Modify: `script/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Replace test_pipeline.py with transcript-entry tests**

Overwrite `tests/test_pipeline.py` entirely with:

```python
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from script.config import Settings
from script.schemas import (
    Conclusion, Action, ChunkExtract, MeetingMinutes, ReviewResult, ReviewNote,
)
from script.pipeline import run_pipeline


def _settings(tmp_path, **over):
    base = dict(
        OPENAI_API_KEY="sk-x", OPENAI_API_BASE="https://x/v1", OPENAI_MODEL="m",
        OUT_DIR=str(tmp_path / "out"), LOG_DIR=str(tmp_path / "log"),
        ENABLE_PROPER_NOUN_CORRECTION="false",
    )
    base.update(over)
    return Settings(**base)


def _conc(): return Conclusion(text="c", is_inferred=False, source_quote="q",
                                source_timestamp="00:00:01", source_speaker=None)
def _act(): return Action(task="t", owner="o", due="d", priority="medium",
                          source_quote="q", source_timestamp="00:00:02",
                          source_speaker=None, rationale="r", is_inferred=False,
                          owner_inferred=False, due_inferred=False, priority_inferred=True)


def _src(tmp_path):
    p = tmp_path / "transcript_in.txt"
    p.write_text("00:00\n大家好\n", encoding="utf-8")
    return str(p)


@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.load_transcript")
def test_pipeline_runs_from_transcript(
    load_m, chunk_m, MAm, RAm, write_r, write_x, tmp_path,
):
    settings = _settings(tmp_path)
    out_dir = Path(settings.out_dir) / "t"

    def _fake_load(src, dst):
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_text("[00:00:00] 大家好\n", encoding="utf-8")
    load_m.side_effect = _fake_load

    chunk_m.return_value = [MagicMock(text="x", first_timestamp="00:00:00",
                                       last_timestamp="00:00:01", token_estimate=5)]
    MAm.return_value.map_chunks.return_value = [
        ChunkExtract(topics=[], conclusions=[_conc()], actions=[_act()])
    ]
    MAm.return_value.reduce.return_value = MeetingMinutes(
        conclusions=[_conc()], actions=[_act()],
    )
    RAm.return_value.review.return_value = ReviewResult(notes=[
        ReviewNote(target_section="conclusion", target_id="C1",
                   category="ok", severity="info", note="", suggestion=""),
        ReviewNote(target_section="action", target_id="A1",
                   category="ok", severity="info", note="", suggestion=""),
    ])

    run_pipeline(_src(tmp_path), settings=settings, name="t")

    load_m.assert_called_once()
    write_x.assert_called_once()
    write_r.assert_called_once()
    assert write_x.call_args.kwargs["diarization_enabled"] is False
    assert write_x.call_args.kwargs["speakers_detected"] == 0


@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.load_transcript")
def test_pipeline_uses_cached_transcript(
    load_m, chunk_m, MAm, RAm, write_r, write_x, tmp_path,
):
    settings = _settings(tmp_path)
    out_dir = Path(settings.out_dir) / "t"
    out_dir.mkdir(parents=True)
    (out_dir / "transcript.md").write_text("[00:00:00] cached\n", encoding="utf-8")

    chunk_m.return_value = [MagicMock(text="x", first_timestamp="00:00:00",
                                       last_timestamp="00:00:01", token_estimate=5)]
    MAm.return_value.map_chunks.return_value = [
        ChunkExtract(topics=[], conclusions=[_conc()], actions=[])
    ]
    MAm.return_value.reduce.return_value = MeetingMinutes(conclusions=[_conc()], actions=[])
    RAm.return_value.review.return_value = ReviewResult(notes=[
        ReviewNote(target_section="conclusion", target_id="C1",
                   category="ok", severity="info", note="", suggestion=""),
    ])

    run_pipeline(_src(tmp_path), settings=settings, name="t", force=False)

    load_m.assert_not_called()


@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.load_transcript")
@patch("script.pipeline.correct_transcript")
@patch("script.pipeline.CorrectorAgent")
def test_pipeline_invokes_corrector_when_enabled(
    CAm, correct_m, load_m, chunk_m, MAm, RAm, write_r, write_x, tmp_path,
):
    settings = _settings(tmp_path, ENABLE_PROPER_NOUN_CORRECTION="true")

    def _fake_load(src, dst):
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_text("[00:00:00] 大家好\n", encoding="utf-8")
    load_m.side_effect = _fake_load

    chunk_m.return_value = [MagicMock(text="x", first_timestamp="00:00:00",
                                       last_timestamp="00:00:01", token_estimate=5)]
    MAm.return_value.map_chunks.return_value = [
        ChunkExtract(topics=[], conclusions=[_conc()], actions=[])
    ]
    MAm.return_value.reduce.return_value = MeetingMinutes(conclusions=[_conc()], actions=[])
    RAm.return_value.review.return_value = ReviewResult(notes=[
        ReviewNote(target_section="conclusion", target_id="C1",
                   category="ok", severity="info", note="", suggestion=""),
    ])

    run_pipeline(_src(tmp_path), settings=settings, name="t")

    correct_m.assert_called_once()
    CAm.assert_called_once()


@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
def test_pipeline_rerender_only_skips_llm_and_uses_cached(
    write_r, write_x, tmp_path,
):
    settings = _settings(tmp_path)
    out_dir = Path(settings.out_dir) / "t"
    inter_dir = out_dir / "intermediate"
    inter_dir.mkdir(parents=True)
    cached_minutes = MeetingMinutes(conclusions=[_conc()], actions=[_act()])
    (inter_dir / "minutes.json").write_text(cached_minutes.model_dump_json(), encoding="utf-8")
    cached_review = ReviewResult(notes=[
        ReviewNote(target_section="conclusion", target_id="C1",
                   category="ok", severity="info", note="", suggestion=""),
        ReviewNote(target_section="action", target_id="A1",
                   category="ok", severity="info", note="", suggestion=""),
    ])
    (inter_dir / "review.json").write_text(cached_review.model_dump_json(), encoding="utf-8")
    (out_dir / "speaker_map.json").write_text('{"SPEAKER_00": "Albert"}', encoding="utf-8")

    run_pipeline(_src(tmp_path), settings=settings, name="t", rerender_only=True)

    write_x.assert_called_once()
    write_r.assert_called_once()
    assert write_x.call_args.kwargs["speaker_map"] == {"SPEAKER_00": "Albert"}
    assert write_x.call_args.kwargs["diarization_enabled"] is False


def test_pipeline_rerender_only_raises_without_cache(tmp_path):
    settings = _settings(tmp_path)
    with pytest.raises(RuntimeError, match="cached"):
        run_pipeline(_src(tmp_path), settings=settings, name="missing", rerender_only=True)
```

- [ ] **Step 2: Run pipeline tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -v`
Expected: FAIL — `cannot import name 'load_transcript' from 'script.pipeline'` (and audio stages still present).

- [ ] **Step 3: Rewrite pipeline.py**

Replace the import block (lines 1-21) of `script/pipeline.py` with:

```python
import dataclasses
import json
from pathlib import Path
from openai import OpenAI

from script.config import Settings
from script.logger import setup_logger, log_kv
from script.transcript_loader import load_transcript
from script.chunker import chunk_transcript
from script.markdown_writer import write_review_report_md
from script.html_writer import write_minutes_html
from script.agents.base import probe_instructor_mode, usage_summary, estimate_cost
from script.agents.minutes_agent import MinutesAgent
from script.agents.reviewer_agent import ReviewerAgent
from script.transcript_corrector import correct_transcript
from script.agents.corrector_agent import CorrectorAgent
from script.schemas import MeetingMinutes, ReviewResult
from script import speaker_map as _spk_map
```

Replace the `run_pipeline` signature (lines 32-41) with:

```python
def run_pipeline(
    src: str,
    *,
    settings: Settings,
    name: str | None = None,
    force: bool = False,
    rerender_only: bool = False,
) -> None:
```

In the `rerender_only` block, replace the `diar_was_used` / `speakers_detected` lines and both writer calls so they pass fixed non-diarization values:

```python
    if rerender_only:
        minutes_path = inter_dir / "minutes.json"
        review_path = inter_dir / "review.json"
        if not minutes_path.exists() or not review_path.exists():
            raise RuntimeError(
                "--rerender requires cached intermediate/minutes.json and "
                "intermediate/review.json from a previous full run."
            )
        minutes = MeetingMinutes.model_validate_json(minutes_path.read_text(encoding="utf-8"))
        review = ReviewResult.model_validate_json(review_path.read_text(encoding="utf-8"))

        write_minutes_html(
            minutes, review, str(out_dir / "minutes.html"),
            meeting_file=src,
            diarization_enabled=False,
            speakers_detected=0,
            speaker_map=spk_map,
        )
        write_review_report_md(
            minutes, review, str(out_dir / "review_report.md"),
            meeting_file=src, diarization_enabled=False,
            speakers_detected=0, speaker_map=spk_map,
        )
        log_kv(logger, "INFO", "pipeline.done", out=str(out_dir), mode="rerender")
        return
```

Replace the entire Stage 1+2(+2.5) block (current lines 83-141, from `audio_path = ...` through the cached `else:` branch that sets `transcript_text`) with:

```python
    transcript_path = out_dir / "transcript.md"
    speakers_detected = 0

    # Stage 1: obtain transcript.md from the user-supplied transcript file
    if force or not transcript_path.exists():
        if not Path(src).exists():
            raise RuntimeError(f"transcript file not found: {src}")
        load_transcript(src, str(transcript_path))
        log_kv(logger, "INFO", "stage.load_transcript", output=str(transcript_path))
    else:
        log_kv(logger, "INFO", "stage.transcript.cached", path=str(transcript_path))
    transcript_text = transcript_path.read_text(encoding="utf-8")
```

In the final outputs block, replace `diarization_enabled=diar_enabled,` with `diarization_enabled=False,` in BOTH the `write_minutes_html(...)` and `write_review_report_md(...)` calls. Leave `speakers_detected=speakers_detected,` (it is 0) and `speaker_map=spk_map,` as-is. Delete no other lines in Stage 2.95 / chunk / minutes / review.

- [ ] **Step 4: Run pipeline tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the full suite (collection-impacting)**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: `test_main.py`, `test_config.py`, `test_markdown_writer.py` may still pass here (they still import the not-yet-deleted audio modules). transcript_loader + pipeline green. If anything else fails, it is fixed in later tasks — note failures and continue.

- [ ] **Step 6: Commit**

```bash
git add script/pipeline.py tests/test_pipeline.py
git commit -m "refactor: pipeline starts from transcript_loader, drop audio stages"
```

---

### Task 3: main.py CLI — src is the transcript path

**Files:**
- Modify: `script/main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Rewrite test_main.py**

Overwrite `tests/test_main.py` with:

```python
from unittest.mock import patch
from typer.testing import CliRunner
from script.main import app


def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("OPENAI_API_BASE", "https://x/v1")
    monkeypatch.setenv("OPENAI_MODEL", "m")
    monkeypatch.chdir(tmp_path)


def test_cli_passes_basic_args(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(app, ["transcript.txt", "--name", "test", "--force"])
    assert result.exit_code == 0, result.output
    args, kwargs = run.call_args
    assert args[0] == "transcript.txt"
    assert kwargs["name"] == "test"
    assert kwargs["force"] is True
    assert kwargs["rerender_only"] is False


def test_cli_rerender_flag(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(app, ["transcript.txt", "--name", "t", "--rerender"])
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["rerender_only"] is True


def test_cli_rejects_removed_diarize_flag(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline"):
        result = runner.invoke(app, ["transcript.txt", "--diarize"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main.py -v`
Expected: FAIL — `--diarize` still accepted / `skip_transcribe` kwarg path mismatch.

- [ ] **Step 3: Rewrite main.py**

Overwrite `script/main.py` with:

```python
import typer
from script.config import Settings
from script.pipeline import run_pipeline


app = typer.Typer(help="Convert a prepared meeting transcript to structured minutes.")


@app.command()
def process(
    src: str = typer.Argument(..., help="Path to the prepared transcript file (UTF-8, MM:SS blocks)."),
    name: str | None = typer.Option(None, "--name", help="Output folder name (defaults to src basename)."),
    force: bool = typer.Option(False, "--force", help="Ignore stage cache, re-run all stages."),
    rerender: bool = typer.Option(
        False, "--rerender",
        help="Skip LLM stages; re-render minutes.html + review_report.md "
             "from cached intermediate/minutes.json + review.json.",
    ),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
) -> None:
    settings = Settings()
    if verbose:
        settings.log_level = "DEBUG"
    run_pipeline(
        src,
        settings=settings,
        name=name,
        force=force,
        rerender_only=rerender,
    )


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add script/main.py tests/test_main.py
git commit -m "refactor: CLI src is transcript path; drop --skip-transcribe/--diarize"
```

---

### Task 4: config.py — remove audio settings

**Files:**
- Modify: `script/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Rewrite test_config.py**

Overwrite `tests/test_config.py` with:

```python
import pytest
from pydantic import ValidationError
from script.config import Settings


def test_required_fields_raise_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError) as exc:
        Settings()
    msg = str(exc.value)
    assert "OPENAI_API_KEY" in msg
    assert "OPENAI_API_BASE" in msg
    assert "OPENAI_MODEL" in msg


def test_defaults_when_only_required_provided(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_BASE", "https://x.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.llm_chunk_tokens == 4000
    assert s.llm_chunk_overlap_ratio == 0.10
    assert s.llm_parallel_map == 3
    assert s.out_dir == "out"


def test_no_audio_settings_remain():
    for attr in (
        "whisper_model", "whisper_device", "enable_diarization",
        "hf_token", "diarization_model", "alignment_model",
    ):
        assert not hasattr(Settings, attr) and attr not in Settings.model_fields


def test_proper_noun_correction_default_false(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_BASE", "https://x.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.enable_proper_noun_correction is False
    assert s.glossary_file == "script/prompts/glossary.md"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: FAIL — `test_no_audio_settings_remain` fails (fields still present).

- [ ] **Step 3: Edit config.py**

In `script/config.py`:

Change line 1 from:
```python
from pydantic import Field, model_validator
```
to:
```python
from pydantic import Field
```

Delete the entire `# === ASR ===` block and the `# === Diarization (optional) ===` block (current lines 18-41 — every `whisper_*`, `enable_diarization`, `hf_token`, `diarization_model`, `alignment_model` field).

Delete the validator at the end (current lines 68-72):
```python
    @model_validator(mode="after")
    def _check_diarization_token(self):
        if self.enable_diarization and not self.hf_token:
            raise ValueError("HF_TOKEN is required when ENABLE_DIARIZATION=true")
        return self
```

Leave the required LLM block, `# === Transcript Correction (Stage 2.95) ===`, `# === Chunking / LLM ===`, `# === Pricing ===`, and `# === I/O ===` blocks unchanged.

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add script/config.py tests/test_config.py
git commit -m "refactor: drop whisper/diarization settings from config"
```

---

### Task 5: Trim dead write_transcript_md from markdown_writer

**Files:**
- Modify: `script/markdown_writer.py`
- Modify: `tests/test_markdown_writer.py`

Rationale: `write_transcript_md` and its `Segment`/`TranscribedSegment` imports are only used by the removed audio path; they reference modules deleted in Task 6. `write_review_report_md` and all speaker/remap logic stay.

- [ ] **Step 1: Edit markdown_writer.py**

In `script/markdown_writer.py`, delete the top block (current lines 1-26): the
`from script.transcribe import Segment`, `from script.diarize import TranscribedSegment`,
the `_fmt_ts` function, and the entire `write_transcript_md` function.

The file must now START at the remaining import line:
```python
from pathlib import Path

from script.schemas import MeetingMinutes, ReviewResult, ReviewNote
from script.speaker_map import remap as _remap, remap_text as _remap_text
```
(Add `from pathlib import Path` at the top — it was previously imported on line 1 and is still used by `write_review_report_md` via `Path(dst)`.) Keep `write_review_report_md`, `_lookup`, `_ok_label`, `_render_note` exactly as they are.

- [ ] **Step 2: Edit test_markdown_writer.py**

In `tests/test_markdown_writer.py`, delete lines 1-31 (the `Segment`/`TranscribedSegment`/`write_transcript_md` imports and the two `test_transcript_*` tests). The file must now START at:
```python
from script.schemas import (
    Conclusion,
    Action,
    KeyPoint,
    MeetingMinutes,
    ReviewNote,
    ReviewResult,
)
from script.markdown_writer import write_review_report_md
```
Keep the remaining `_c`/`_a`/`_k` helpers and the three `test_review_report_*` tests unchanged.

- [ ] **Step 3: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_markdown_writer.py -v`
Expected: PASS (3 passed)

- [ ] **Step 4: Commit**

```bash
git add script/markdown_writer.py tests/test_markdown_writer.py
git commit -m "refactor: remove dead write_transcript_md (audio-path only)"
```

---

### Task 6: Delete audio-bound modules and their tests

**Files:**
- Delete: `script/media.py`, `script/transcribe.py`, `script/diarize.py`, `script/sample_extractor.py`
- Delete: `tests/test_transcribe.py`, `tests/test_sample_extractor.py`

- [ ] **Step 1: Confirm nothing still imports them**

Run: `.venv\Scripts\python.exe -m pytest -q --collect-only`
Expected: collection succeeds with no import of `script.media/transcribe/diarize/sample_extractor`. If a collection error names one of these, fix that residual import before deleting.

- [ ] **Step 2: Delete the files**

```bash
git rm script/media.py script/transcribe.py script/diarize.py script/sample_extractor.py tests/test_transcribe.py tests/test_sample_extractor.py
```

- [ ] **Step 3: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: PASS — all remaining tests green (no collection errors).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: delete audio-bound modules (media/transcribe/diarize/sample_extractor) + tests"
```

---

### Task 7: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Inspect current README usage section**

Run: `.venv\Scripts\python.exe -c "print(open('README.md', encoding='utf-8').read())"`
Identify sections describing audio input, Whisper, diarization, `--skip-transcribe`, `--diarize`.

- [ ] **Step 2: Edit README.md**

- Replace the input description: the program now takes a prepared UTF-8 transcript file in `MM:SS`-block format (timestamp on its own line, then the spoken text); show the 2-line example from the spec §2.
- Update the run command to `python -m script.main process <transcript.txt> [--name N] [--force] [--rerender] [-v]`.
- Remove Whisper / diarization / `HF_TOKEN` / `ENABLE_DIARIZATION` / `WHISPER_*` setup and the `--skip-transcribe` / `--diarize` flag docs.
- Add a one-line note: speaker-labeled transcript support is planned (see `doc/specs/2026-05-18-transcript-to-minutes-design.md` §8); `ENABLE_PROPER_NOUN_CORRECTION` stays as an optional, default-off stage.
- Do not alter unrelated README sections.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README reflects transcript-input pipeline"
```

---

### Task 8: Final verification + end-to-end smoke

**Files:** none (verification only)

- [ ] **Step 1: Full suite green**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass, 0 errors, 0 collection errors.

- [ ] **Step 2: Loader smoke against a real-shaped transcript**

Create `D:\Meeting\20260518_leadersync\sample_ts.txt` (UTF-8) with a few `MM:SS` blocks (use the spec §2 example content), then run:

```bash
.venv\Scripts\python.exe -c "from script.transcript_loader import load_transcript; load_transcript(r'D:\Meeting\20260518_leadersync\sample_ts.txt', r'.\_smoke\transcript.md'); print(open(r'.\_smoke\transcript.md', encoding='utf-8').read())"
```
Expected: output lines all start with `[HH:MM:SS] ` and content is intact Chinese text. Delete `_smoke\` afterward (`Remove-Item -Recurse -Force _smoke`).

- [ ] **Step 3: Confirm no stale references remain**

Run: `.venv\Scripts\python.exe -c "import script.pipeline, script.main, script.config, script.markdown_writer, script.html_writer; print('imports ok')"`
Expected: `imports ok` (no ModuleNotFoundError for deleted modules).

- [ ] **Step 4: Final commit (if any verification fixups were needed)**

```bash
git add -A && git commit -m "chore: post-refactor verification fixups" || echo "nothing to commit"
```

---

## Notes for the implementer

- Keep `source_speaker` in `schemas.py`, `script/speaker_map.py` + `tests/test_speaker_map.py`, all speaker references in `script/prompts/`, and `write_review_report_md`'s speaker layout **unchanged** — they are the deliberate extension surface for the deferred speaker-labeled transcript feature (spec §4.7, §8).
- The `.m4a` recording in `D:\Meeting\20260518_leadersync\` is intentionally ignored — no ASR.
- Run all commands from repo root with the project venv: `.venv\Scripts\python.exe`.
