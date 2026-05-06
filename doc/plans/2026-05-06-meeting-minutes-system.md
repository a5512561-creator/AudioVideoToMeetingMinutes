# Meeting Minutes System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI Python pipeline that converts long meeting audio/video (30 min – several hours) into a structured Excel meeting minutes file plus a Markdown review report, using on-prem OpenAI-compatible LLM, faster-whisper for ASR, and optional pyannote diarization.

**Architecture:** 5-stage pipeline (media → transcribe → optional diarize → minutes map-reduce → review). Each stage reads/writes files so any stage can be re-run alone. LLM calls go through Instructor + Pydantic for typed retries. Prompts live as Jinja2 files for easy editing and few-shot extension.

**Tech Stack:** Python 3.11+, faster-whisper, whisperx, pyannote.audio, openai+instructor, pydantic+pydantic-settings, jinja2, openpyxl, typer, stamina, pytest.

**Spec:** `doc/specs/2026-05-06-meeting-minutes-design.md` — read this first if any task is ambiguous.

---

## File Structure (locked)

```
script/
├── main.py                    # Task 18 — typer CLI entry
├── pipeline.py                # Task 17 — orchestrator + stage cache
├── config.py                  # Task 2  — pydantic-settings
├── logger.py                  # Task 3  — structured logger
├── schemas.py                 # Task 4  — Pydantic models
├── media.py                   # Task 5  — ffmpeg wrapper
├── transcribe.py              # Task 6  — faster-whisper wrapper
├── diarize.py                 # Task 7  — WhisperX + pyannote
├── chunker.py                 # Task 9  — recursive chunking
├── markdown_writer.py         # Task 8 + 16 — transcript.md + review_report.md
├── excel_writer.py            # Task 15 — minutes.xlsx
├── agents/
│   ├── __init__.py
│   ├── base.py                # Task 10 — LLMAgent base + probe_instructor_mode
│   ├── minutes_agent.py       # Task 12 — map-reduce
│   └── reviewer_agent.py      # Task 14
└── prompts/
    ├── background.md          # Task 11
    ├── minutes_system.j2      # Task 11
    ├── minutes_map.j2         # Task 11
    ├── minutes_reduce.j2      # Task 11
    ├── reviewer_system.j2     # Task 13
    ├── reviewer_user.j2       # Task 13
    └── few_shot/
        ├── minutes/example_001.json    # Task 11
        └── reviewer/example_001.json   # Task 13

tests/
├── conftest.py                # Task 1  — global fixtures + heavy lib mocks
├── test_config.py             # Task 2
├── test_logger.py             # Task 3
├── test_schemas.py            # Task 4
├── test_media.py              # Task 5
├── test_transcribe.py         # Task 6
├── test_diarize.py            # Task 7
├── test_markdown_writer.py    # Task 8 + 16
├── test_chunker.py            # Task 9
├── test_agents_base.py        # Task 10
├── test_minutes_agent.py      # Task 12
├── test_reviewer_agent.py     # Task 14
├── test_excel_writer.py       # Task 15
├── test_pipeline.py           # Task 17
└── fixtures/
    ├── short.wav              # provided by user; tiny test audio
    └── transcript_short.md    # canned transcript for chunker/agent tests
```

---

## Task 1: Repo bootstrap

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `README.md`
- Create: `script/__init__.py`
- Create: `script/agents/__init__.py`
- Create: `script/prompts/few_shot/minutes/.gitkeep`
- Create: `script/prompts/few_shot/reviewer/.gitkeep`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/.gitkeep`
- Create: `pytest.ini`

- [ ] **Step 1: git init**

```bash
cd d:/GitRep/AudioVideoToMeetingMinutes
git init -b main
```

Expected: `Initialized empty Git repository`

- [ ] **Step 2: Create `.gitignore`**

```gitignore
# venv
.venv/
venv/

# secrets / runtime
.env
out/
log/

# python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 3: Create `.env.example`**

Copy verbatim from spec §6.6 (`doc/specs/2026-05-06-meeting-minutes-design.md`). Do not fill in real secrets.

- [ ] **Step 4: Create `requirements.txt`**

```
openai>=1.40.0,<2.0
instructor>=1.5.0,<2.0
pydantic>=2.5.0,<3.0
pydantic-settings>=2.4.0,<3.0
faster-whisper>=1.0.0,<2.0
whisperx>=3.1.0,<4.0
pyannote.audio>=3.3.0,<4.0
openpyxl>=3.1.0,<4.0
jinja2>=3.1.0,<4.0
typer>=0.12.0,<1.0
stamina>=24.0.0
python-dotenv>=1.0.0
tiktoken>=0.7.0
```

- [ ] **Step 5: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest>=8.0
pytest-mock>=3.12
```

- [ ] **Step 6: Create venv + install dev deps**

```bash
python -m venv .venv
.venv/Scripts/pip install --upgrade pip
.venv/Scripts/pip install -r requirements-dev.txt
```

Expected: All packages install without error. (Whisper/pyannote model files are NOT downloaded yet; that happens on first model instantiation.)

- [ ] **Step 7: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v --tb=short
```

- [ ] **Step 8: Create empty package files**

```bash
mkdir -p script/agents script/prompts/few_shot/minutes script/prompts/few_shot/reviewer tests/fixtures
type nul > script/__init__.py
type nul > script/agents/__init__.py
type nul > tests/__init__.py
type nul > script/prompts/few_shot/minutes/.gitkeep
type nul > script/prompts/few_shot/reviewer/.gitkeep
type nul > tests/fixtures/.gitkeep
```

- [ ] **Step 9: Create `tests/conftest.py`** (mock heavy ML libs at session scope so unit tests never download models)

```python
import sys
from unittest.mock import MagicMock
import pytest


@pytest.fixture(autouse=True)
def _mock_heavy_libs(monkeypatch):
    """Prevent any test from accidentally instantiating real ML models."""
    fake_whisper = MagicMock()
    fake_whisper.WhisperModel = MagicMock(name="WhisperModel")
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_whisper)

    fake_pyannote = MagicMock()
    fake_pyannote.Pipeline = MagicMock(name="Pipeline")
    monkeypatch.setitem(sys.modules, "pyannote.audio", fake_pyannote)
```

- [ ] **Step 10: Create `README.md` skeleton**

```markdown
# Meeting Minutes System

Convert meeting audio/video into structured Excel minutes via on-prem LLM.

## Setup

1. Install ffmpeg and put it on PATH.
2. `python -m venv .venv && .venv/Scripts/pip install -r requirements.txt`
3. `cp .env.example .env` and fill in `OPENAI_*` values.
4. (Optional) For speaker diarization: apply for HuggingFace token and accept gated model terms — see `doc/specs/`.

## Usage

```bash
python script/main.py path/to/meeting.mp4
```

See `doc/specs/2026-05-06-meeting-minutes-design.md` for full design.
```

- [ ] **Step 11: Verify pytest discovers nothing yet**

```bash
.venv/Scripts/pytest
```

Expected: `no tests ran` (zero collected, zero failed) — confirms test infra works.

- [ ] **Step 12: Commit**

```bash
git add .gitignore .env.example requirements.txt requirements-dev.txt pytest.ini README.md script/ tests/
git commit -m "chore: bootstrap meeting-minutes project skeleton"
```

---

## Task 2: Config (pydantic-settings)

**Files:**
- Create: `script/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config.py`:

```python
import pytest
from pydantic import ValidationError
from script.config import Settings


def test_required_fields_raise_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env present
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
    assert s.whisper_model == "large-v3"
    assert s.enable_diarization is False
    assert s.llm_chunk_tokens == 4000
    assert s.llm_chunk_overlap_ratio == 0.10
    assert s.llm_parallel_map == 3


def test_diarization_requires_hf_token_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_BASE", "https://x.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("ENABLE_DIARIZATION", "true")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError, match="HF_TOKEN"):
        Settings()
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
.venv/Scripts/pytest tests/test_config.py -v
```

Expected: `ImportError` or fail at collection — `script.config` doesn't exist.

- [ ] **Step 3: Implement `script/config.py`**

```python
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # === Required: company LLM ===
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_api_base: str = Field(..., alias="OPENAI_API_BASE")
    openai_model: str = Field(..., alias="OPENAI_MODEL")

    # === ASR ===
    whisper_model: str = Field("large-v3", alias="WHISPER_MODEL")
    whisper_device: str = Field("auto", alias="WHISPER_DEVICE")
    whisper_compute_type: str = Field("auto", alias="WHISPER_COMPUTE_TYPE")
    whisper_language: str = Field("zh", alias="WHISPER_LANGUAGE")
    whisper_initial_prompt: str = Field(
        "以下是繁體中文會議記錄，可能包含英文技術名詞如 API、Roadmap、Sprint。",
        alias="WHISPER_INITIAL_PROMPT",
    )
    whisper_vad_filter: bool = Field(True, alias="WHISPER_VAD_FILTER")

    # === Diarization (optional) ===
    enable_diarization: bool = Field(False, alias="ENABLE_DIARIZATION")
    hf_token: str = Field("", alias="HF_TOKEN")
    diarization_model: str = Field(
        "pyannote/speaker-diarization-community-1", alias="DIARIZATION_MODEL"
    )
    alignment_model: str = Field(
        "jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn", alias="ALIGNMENT_MODEL"
    )

    # === Chunking / LLM ===
    llm_chunk_tokens: int = Field(4000, alias="LLM_CHUNK_TOKENS")
    llm_chunk_overlap_ratio: float = Field(0.10, alias="LLM_CHUNK_OVERLAP_RATIO")
    llm_temperature: float = Field(0.2, alias="LLM_TEMPERATURE")
    llm_max_retries: int = Field(3, alias="LLM_MAX_RETRIES")
    llm_timeout_secs: int = Field(180, alias="LLM_TIMEOUT_SECS")
    llm_parallel_map: int = Field(3, alias="LLM_PARALLEL_MAP")

    # === I/O ===
    out_dir: str = Field("out", alias="OUT_DIR")
    log_dir: str = Field("log", alias="LOG_DIR")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    keep_intermediate: bool = Field(True, alias="KEEP_INTERMEDIATE")

    @model_validator(mode="after")
    def _check_diarization_token(self):
        if self.enable_diarization and not self.hf_token:
            raise ValueError("HF_TOKEN is required when ENABLE_DIARIZATION=true")
        return self
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
.venv/Scripts/pytest tests/test_config.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add script/config.py tests/test_config.py
git commit -m "feat: pydantic-settings config with diarization gate"
```

---

## Task 3: Structured logger

**Files:**
- Create: `script/logger.py`
- Create: `tests/test_logger.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_logger.py`:

```python
import logging
import re
from script.logger import setup_logger, log_kv


def test_log_kv_format(caplog):
    logger = setup_logger("test", log_dir=None, level="INFO")
    with caplog.at_level(logging.INFO, logger="test"):
        log_kv(logger, "INFO", "stage.start", file="x.mp4", duration=1.2)
    assert len(caplog.records) == 1
    msg = caplog.records[0].getMessage()
    assert msg == "stage.start file=x.mp4 duration=1.2"


def test_setup_logger_writes_to_file(tmp_path):
    logger = setup_logger("test_file", log_dir=str(tmp_path), level="INFO")
    log_kv(logger, "INFO", "hello", k="v")
    for h in logger.handlers:
        h.flush()
    files = list(tmp_path.glob("run_*.log"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "hello k=v" in content
    assert re.search(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]", content)
```

- [ ] **Step 2: Run tests — fail**

```bash
.venv/Scripts/pytest tests/test_logger.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `script/logger.py`**

```python
import logging
import os
from datetime import datetime
from pathlib import Path


def setup_logger(name: str, log_dir: str | None, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level))
    logger.handlers.clear()

    fmt = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        fh = logging.FileHandler(
            os.path.join(log_dir, f"run_{ts}.log"), encoding="utf-8"
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


def log_kv(logger: logging.Logger, level: str, event: str, **kv) -> None:
    """Emit a structured `event k1=v1 k2=v2` log line."""
    parts = [event] + [f"{k}={v}" for k, v in kv.items()]
    logger.log(getattr(logging, level), " ".join(parts))
```

- [ ] **Step 4: Run — pass**

```bash
.venv/Scripts/pytest tests/test_logger.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add script/logger.py tests/test_logger.py
git commit -m "feat: structured key=value logger with file + stream handlers"
```

---

## Task 4: Pydantic schemas

**Files:**
- Create: `script/schemas.py`
- Create: `tests/test_schemas.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_schemas.py`:

```python
import pytest
from pydantic import ValidationError
from script.schemas import (
    Conclusion,
    Action,
    ChunkExtract,
    MeetingMinutes,
    ReviewNote,
)


def _conclusion(**over):
    base = dict(
        text="x",
        is_inferred=False,
        source_quote="y",
        source_timestamp="00:00:01",
        source_speaker=None,
    )
    base.update(over)
    return Conclusion(**base)


def _action(**over):
    base = dict(
        task="t",
        owner="o",
        due="2026-05-15",
        priority="medium",
        source_quote="q",
        source_timestamp="00:00:02",
        source_speaker=None,
        rationale="r",
        is_inferred=False,
        owner_inferred=False,
        due_inferred=False,
        priority_inferred=True,
    )
    base.update(over)
    return Action(**base)


def test_conclusion_speaker_optional():
    c = _conclusion(source_speaker="SPEAKER_1")
    assert c.source_speaker == "SPEAKER_1"
    c2 = _conclusion(source_speaker=None)
    assert c2.source_speaker is None


def test_action_priority_must_be_enum():
    with pytest.raises(ValidationError):
        _action(priority="urgent")  # not in enum


def test_meeting_minutes_holds_lists():
    m = MeetingMinutes(conclusions=[_conclusion()], actions=[_action()])
    assert len(m.conclusions) == 1 and len(m.actions) == 1


def test_review_note_target_section_enum():
    ReviewNote(
        target_section="conclusion",
        target_id="C1",
        category="ok",
        severity="info",
        note="",
        suggestion="",
    )
    with pytest.raises(ValidationError):
        ReviewNote(
            target_section="結論",  # must be english enum
            target_id="C1",
            category="ok",
            severity="info",
            note="",
            suggestion="",
        )


def test_chunk_extract_holds_topics_conclusions_actions():
    ce = ChunkExtract(topics=["t1"], conclusions=[_conclusion()], actions=[_action()])
    assert ce.topics == ["t1"]
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `script/schemas.py`**

```python
from typing import Literal
from pydantic import BaseModel


class Conclusion(BaseModel):
    text: str
    is_inferred: bool
    source_quote: str
    source_timestamp: str
    source_speaker: str | None = None


class Action(BaseModel):
    task: str
    owner: str
    due: str
    priority: Literal["high", "medium", "low"]
    source_quote: str
    source_timestamp: str
    source_speaker: str | None = None
    rationale: str
    is_inferred: bool
    owner_inferred: bool
    due_inferred: bool
    priority_inferred: bool


class ChunkExtract(BaseModel):
    topics: list[str]
    conclusions: list[Conclusion]
    actions: list[Action]


class MeetingMinutes(BaseModel):
    conclusions: list[Conclusion]
    actions: list[Action]


class ReviewNote(BaseModel):
    target_section: Literal["conclusion", "action"]
    target_id: str
    category: Literal["conflict", "ambiguity", "unreasonable", "ok"]
    severity: Literal["info", "warn", "error"]
    note: str
    suggestion: str


class ReviewResult(BaseModel):
    notes: list[ReviewNote]
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git add script/schemas.py tests/test_schemas.py
git commit -m "feat: pydantic schemas for minutes, actions, reviews"
```

---

## Task 5: media.py — ffmpeg wrapper

**Files:**
- Create: `script/media.py`
- Create: `tests/test_media.py`

- [ ] **Step 1: Write tests**

Create `tests/test_media.py`:

```python
import subprocess
from unittest.mock import patch
import pytest
from script.media import extract_audio, FFmpegMissingError, FFmpegFailedError


def test_extract_audio_builds_correct_command(tmp_path):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    dst = tmp_path / "out.wav"

    with patch("script.media.shutil.which", return_value="ffmpeg"), \
         patch("script.media.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        extract_audio(str(src), str(dst))

    args = run.call_args[0][0]
    assert args[0] == "ffmpeg"
    assert "-i" in args and str(src) in args
    assert "-vn" in args
    assert "-ac" in args and "1" in args
    assert "-ar" in args and "16000" in args
    assert "-c:a" in args and "pcm_s16le" in args
    assert str(dst) in args


def test_extract_audio_raises_when_ffmpeg_missing(tmp_path):
    with patch("script.media.shutil.which", return_value=None):
        with pytest.raises(FFmpegMissingError):
            extract_audio(str(tmp_path / "in.mp4"), str(tmp_path / "out.wav"))


def test_extract_audio_raises_on_nonzero_exit(tmp_path):
    with patch("script.media.shutil.which", return_value="ffmpeg"), \
         patch("script.media.subprocess.run") as run:
        run.return_value.returncode = 1
        run.return_value.stderr = "boom"
        with pytest.raises(FFmpegFailedError, match="boom"):
            extract_audio(str(tmp_path / "in.mp4"), str(tmp_path / "out.wav"))
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `script/media.py`**

```python
import shutil
import subprocess
from pathlib import Path


class FFmpegMissingError(RuntimeError):
    """ffmpeg not found on PATH."""


class FFmpegFailedError(RuntimeError):
    """ffmpeg exited non-zero."""


def extract_audio(src: str, dst: str) -> None:
    """Extract 16kHz mono PCM WAV from an audio/video file."""
    if shutil.which("ffmpeg") is None:
        raise FFmpegMissingError(
            "ffmpeg not found on PATH. Install ffmpeg and add it to PATH."
        )
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i", src,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        dst,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegFailedError(proc.stderr)
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git add script/media.py tests/test_media.py
git commit -m "feat: ffmpeg subprocess wrapper for audio extraction"
```

---

## Task 6: transcribe.py — faster-whisper wrapper

**Files:**
- Create: `script/transcribe.py`
- Create: `tests/test_transcribe.py`

- [ ] **Step 1: Write tests**

Create `tests/test_transcribe.py`:

```python
from unittest.mock import MagicMock, patch
from script.transcribe import transcribe, Segment


def test_transcribe_returns_segments_and_calls_whisper_with_config():
    fake_seg1 = MagicMock(start=0.0, end=2.5, text="你好")
    fake_seg2 = MagicMock(start=2.5, end=5.0, text="世界")
    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([fake_seg1, fake_seg2], MagicMock())

    with patch("script.transcribe.WhisperModel", return_value=fake_model) as ctor:
        segs = transcribe(
            "audio.wav",
            model="large-v3",
            device="cpu",
            compute_type="int8",
            language="zh",
            initial_prompt="prompt",
            vad_filter=True,
        )

    ctor.assert_called_once_with("large-v3", device="cpu", compute_type="int8")
    fake_model.transcribe.assert_called_once_with(
        "audio.wav",
        language="zh",
        initial_prompt="prompt",
        vad_filter=True,
    )
    assert segs == [
        Segment(start=0.0, end=2.5, text="你好"),
        Segment(start=2.5, end=5.0, text="世界"),
    ]
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `script/transcribe.py`**

```python
from dataclasses import dataclass
from faster_whisper import WhisperModel


@dataclass(frozen=True)
class Segment:
    start: float    # seconds
    end: float      # seconds
    text: str


def transcribe(
    audio_path: str,
    *,
    model: str,
    device: str,
    compute_type: str,
    language: str,
    initial_prompt: str,
    vad_filter: bool,
) -> list[Segment]:
    m = WhisperModel(model, device=device, compute_type=compute_type)
    raw_segs, _info = m.transcribe(
        audio_path,
        language=language,
        initial_prompt=initial_prompt,
        vad_filter=vad_filter,
    )
    return [Segment(start=s.start, end=s.end, text=s.text.strip()) for s in raw_segs]
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git add script/transcribe.py tests/test_transcribe.py
git commit -m "feat: faster-whisper transcribe wrapper returning Segment list"
```

---

## Task 7: diarize.py — pyannote + speaker assignment

**Files:**
- Create: `script/diarize.py`
- Create: `tests/test_diarize.py`

- [ ] **Step 1: Write tests**

Create `tests/test_diarize.py`:

```python
from unittest.mock import MagicMock, patch
from script.transcribe import Segment
from script.diarize import (
    SpeakerSegment,
    TranscribedSegment,
    assign_speakers,
    diarize,
)


def test_assign_speakers_picks_max_overlap_speaker():
    segs = [
        Segment(start=0.0, end=2.0, text="你好"),
        Segment(start=2.0, end=5.0, text="世界 大家好"),
    ]
    speakers = [
        SpeakerSegment(start=0.0, end=2.5, label="SPEAKER_1"),
        SpeakerSegment(start=2.5, end=5.0, label="SPEAKER_2"),
    ]
    out = assign_speakers(segs, speakers)
    assert out == [
        TranscribedSegment(start=0.0, end=2.0, text="你好", speaker="SPEAKER_1"),
        TranscribedSegment(start=2.0, end=5.0, text="世界 大家好", speaker="SPEAKER_2"),
    ]


def test_assign_speakers_handles_no_overlap_with_unknown():
    segs = [Segment(start=0.0, end=1.0, text="x")]
    speakers = [SpeakerSegment(start=10.0, end=11.0, label="SPEAKER_1")]
    out = assign_speakers(segs, speakers)
    assert out[0].speaker == "UNKNOWN"


def test_diarize_invokes_pipeline_with_hf_token():
    fake_pipeline = MagicMock()
    fake_pipeline.return_value = MagicMock(
        itertracks=lambda yield_label: iter([
            (MagicMock(start=0.0, end=2.5), None, "SPEAKER_1"),
            (MagicMock(start=2.5, end=5.0), None, "SPEAKER_2"),
        ])
    )
    with patch("script.diarize.Pipeline.from_pretrained", return_value=fake_pipeline) as ctor:
        out = diarize(
            "audio.wav",
            model="pyannote/speaker-diarization-community-1",
            hf_token="hf_x",
        )
    ctor.assert_called_once_with(
        "pyannote/speaker-diarization-community-1", use_auth_token="hf_x"
    )
    fake_pipeline.assert_called_once_with("audio.wav")
    assert out == [
        SpeakerSegment(start=0.0, end=2.5, label="SPEAKER_1"),
        SpeakerSegment(start=2.5, end=5.0, label="SPEAKER_2"),
    ]
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `script/diarize.py`**

```python
from dataclasses import dataclass
from pyannote.audio import Pipeline
from script.transcribe import Segment


@dataclass(frozen=True)
class SpeakerSegment:
    start: float
    end: float
    label: str   # e.g. "SPEAKER_1"


@dataclass(frozen=True)
class TranscribedSegment:
    start: float
    end: float
    text: str
    speaker: str   # "SPEAKER_N" or "UNKNOWN"


def diarize(audio_path: str, *, model: str, hf_token: str) -> list[SpeakerSegment]:
    pipeline = Pipeline.from_pretrained(model, use_auth_token=hf_token)
    annotation = pipeline(audio_path)
    out: list[SpeakerSegment] = []
    for turn, _track, label in annotation.itertracks(yield_label=True):
        out.append(SpeakerSegment(start=turn.start, end=turn.end, label=label))
    return out


def _overlap(a_start, a_end, b_start, b_end) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def assign_speakers(
    segments: list[Segment],
    speakers: list[SpeakerSegment],
) -> list[TranscribedSegment]:
    out: list[TranscribedSegment] = []
    for s in segments:
        best: SpeakerSegment | None = None
        best_ov = 0.0
        for sp in speakers:
            ov = _overlap(s.start, s.end, sp.start, sp.end)
            if ov > best_ov:
                best_ov = ov
                best = sp
        label = best.label if best else "UNKNOWN"
        out.append(TranscribedSegment(start=s.start, end=s.end, text=s.text, speaker=label))
    return out
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git add script/diarize.py tests/test_diarize.py
git commit -m "feat: pyannote diarization wrapper + max-overlap speaker assignment"
```

---

## Task 8: markdown_writer.py — transcript output

**Files:**
- Create: `script/markdown_writer.py`
- Create: `tests/test_markdown_writer.py`

- [ ] **Step 1: Write tests**

Create `tests/test_markdown_writer.py`:

```python
from script.transcribe import Segment
from script.diarize import TranscribedSegment
from script.markdown_writer import write_transcript_md


def test_transcript_without_speaker(tmp_path):
    segs = [
        Segment(start=5.0, end=8.0, text="那我們先講第一個議題。"),
        Segment(start=12.5, end=20.0, text="上週會議達成共識。"),
    ]
    dst = tmp_path / "transcript.md"
    write_transcript_md(segs, str(dst))
    text = dst.read_text(encoding="utf-8")
    assert text == (
        "[00:00:05] 那我們先講第一個議題。\n"
        "[00:00:12] 上週會議達成共識。\n"
    )


def test_transcript_with_speaker(tmp_path):
    segs = [
        TranscribedSegment(start=5.0, end=8.0, text="第一個議題。", speaker="SPEAKER_1"),
        TranscribedSegment(start=12.5, end=20.0, text="達成共識。", speaker="SPEAKER_2"),
    ]
    dst = tmp_path / "transcript.md"
    write_transcript_md(segs, str(dst))
    text = dst.read_text(encoding="utf-8")
    assert text == (
        "[00:00:05] SPEAKER_1: 第一個議題。\n"
        "[00:00:12] SPEAKER_2: 達成共識。\n"
    )
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `script/markdown_writer.py`**

```python
from pathlib import Path
from typing import Iterable, Union
from script.transcribe import Segment
from script.diarize import TranscribedSegment


def _fmt_ts(secs: float) -> str:
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def write_transcript_md(
    segments: Iterable[Union[Segment, TranscribedSegment]],
    dst: str,
) -> None:
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for seg in segments:
        ts = _fmt_ts(seg.start)
        if isinstance(seg, TranscribedSegment):
            lines.append(f"{ts} {seg.speaker}: {seg.text}")
        else:
            lines.append(f"{ts} {seg.text}")
    Path(dst).write_text("\n".join(lines) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git add script/markdown_writer.py tests/test_markdown_writer.py
git commit -m "feat: transcript markdown writer with optional speaker labels"
```

---

## Task 9: chunker.py — recursive chunking

**Files:**
- Create: `script/chunker.py`
- Create: `tests/test_chunker.py`

- [ ] **Step 1: Write tests**

Create `tests/test_chunker.py`:

```python
import pytest
from script.chunker import chunk_transcript, Chunk


def _md(lines):
    return "\n".join(lines) + "\n"


def test_single_short_chunk_returned_intact():
    text = _md([
        "[00:00:01] 短句一。",
        "[00:00:05] 短句二。",
    ])
    chunks = chunk_transcript(text, max_tokens=1000, overlap_ratio=0.1)
    assert len(chunks) == 1
    assert chunks[0].text.strip() == text.strip()
    assert chunks[0].first_timestamp == "00:00:01"
    assert chunks[0].last_timestamp == "00:00:05"


def test_chunk_split_when_exceeding_max_tokens():
    # 50 sentences, each ~10 chars; with max_tokens=20 (worst-case=30 chars) → multiple chunks
    sentences = [f"[00:00:{i:02d}] 句子第{i}個結尾。" for i in range(50)]
    text = _md(sentences)
    chunks = chunk_transcript(text, max_tokens=20, overlap_ratio=0.1)
    assert len(chunks) >= 2
    # No chunk exceeds limit (allow some slack as we cut at sentence boundary)
    for c in chunks:
        assert c.token_estimate <= 20 * 1.5


def test_overlap_repeats_last_lines_of_previous_chunk():
    sentences = [f"[00:00:{i:02d}] 句子{i}。" for i in range(40)]
    text = _md(sentences)
    chunks = chunk_transcript(text, max_tokens=15, overlap_ratio=0.20)
    assert len(chunks) >= 2
    # Second chunk should start with some content also present at end of first
    first_lines = set(chunks[0].text.splitlines()[-3:])
    second_lines = set(chunks[1].text.splitlines()[:3])
    assert first_lines & second_lines, "expected overlap between adjacent chunks"


def test_token_estimate_uses_char_x_15_when_tiktoken_unavailable(monkeypatch):
    # Force the fallback path
    monkeypatch.setattr("script.chunker._tiktoken_count", lambda s: None)
    chunks = chunk_transcript("[00:00:01] 你好。\n", max_tokens=1000, overlap_ratio=0.1)
    assert chunks[0].token_estimate == int(len("[00:00:01] 你好。") * 1.5)


def test_first_and_last_timestamp_extracted():
    text = _md([
        "[00:01:30] A",
        "[00:02:45] B",
        "[01:23:45] C",
    ])
    chunks = chunk_transcript(text, max_tokens=1000, overlap_ratio=0.1)
    assert chunks[0].first_timestamp == "00:01:30"
    assert chunks[0].last_timestamp == "01:23:45"
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `script/chunker.py`**

```python
import re
from dataclasses import dataclass

try:
    import tiktoken
    _enc = tiktoken.get_encoding("o200k_base")

    def _tiktoken_count(s: str) -> int | None:
        try:
            return len(_enc.encode(s))
        except Exception:
            return None
except Exception:    # tiktoken not importable
    def _tiktoken_count(s: str) -> int | None:    # type: ignore[no-redef]
        return None


_TS_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]")


@dataclass(frozen=True)
class Chunk:
    text: str
    first_timestamp: str
    last_timestamp: str
    token_estimate: int


def estimate_tokens(s: str) -> int:
    n = _tiktoken_count(s)
    if n is not None:
        return n
    return int(len(s) * 1.5)


def _first_ts(line: str) -> str | None:
    m = _TS_RE.match(line)
    return m.group(1) if m else None


def chunk_transcript(text: str, *, max_tokens: int, overlap_ratio: float) -> list[Chunk]:
    """Split a [HH:MM:SS]-prefixed transcript into recursive sentence-bounded chunks."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []

    chunks: list[Chunk] = []
    overlap_lines = max(1, int(len(lines) * overlap_ratio / max(1, len(lines)) * 10))
    # Simpler: overlap = ceil(overlap_ratio * lines_in_prev_chunk) computed per-chunk

    i = 0
    while i < len(lines):
        buf: list[str] = []
        buf_tokens = 0
        j = i
        while j < len(lines):
            tentative = buf_tokens + estimate_tokens(lines[j]) + 1
            if buf and tentative > max_tokens:
                break
            buf.append(lines[j])
            buf_tokens = tentative
            j += 1
        # Build chunk
        first = _first_ts(buf[0]) or ""
        last = _first_ts(buf[-1]) or first
        chunks.append(
            Chunk(
                text="\n".join(buf),
                first_timestamp=first,
                last_timestamp=last,
                token_estimate=buf_tokens,
            )
        )
        if j >= len(lines):
            break
        # Overlap: step back by ratio of buf length
        back = max(1, int(len(buf) * overlap_ratio))
        i = max(i + 1, j - back)

    return chunks
```

- [ ] **Step 4: Run — pass**

```bash
.venv/Scripts/pytest tests/test_chunker.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add script/chunker.py tests/test_chunker.py
git commit -m "feat: recursive chunker with sentence-bounded splitting + token fallback"
```

---

## Task 10: agents/base.py — LLMAgent + Instructor + Jinja2

**Files:**
- Create: `script/agents/base.py`
- Create: `tests/test_agents_base.py`

- [ ] **Step 1: Write tests**

Create `tests/test_agents_base.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from pydantic import BaseModel
from script.agents.base import LLMAgent, probe_instructor_mode, FewShot


class Out(BaseModel):
    msg: str


@pytest.fixture
def prompt_dir(tmp_path):
    """Create a minimal prompts/ tree for tests."""
    p = tmp_path / "prompts"
    (p / "few_shot/test").mkdir(parents=True)
    (p / "background.md").write_text("BG_CONTENT", encoding="utf-8")
    (p / "test_system.j2").write_text("SYS {{ background }}", encoding="utf-8")
    (p / "test_user.j2").write_text(
        "{% for s in few_shots %}EX:{{ s.input }}={{ s.output }}\n{% endfor %}USER {{ payload }}",
        encoding="utf-8",
    )
    (p / "few_shot/test/ex1.json").write_text(
        json.dumps({"input": "i1", "output": "o1", "comment": "c"}),
        encoding="utf-8",
    )
    return p


def test_load_few_shots_excludes_comment(prompt_dir):
    agent = LLMAgent(
        name="test",
        prompts_dir=str(prompt_dir),
        client=MagicMock(),
        model="m",
        instructor_mode="JSON",
    )
    assert len(agent.few_shots) == 1
    assert agent.few_shots[0] == FewShot(input="i1", output="o1")


def test_render_injects_background_and_few_shots(prompt_dir):
    agent = LLMAgent(
        name="test",
        prompts_dir=str(prompt_dir),
        client=MagicMock(),
        model="m",
        instructor_mode="JSON",
    )
    sys_text = agent.render("test_system.j2")
    assert sys_text == "SYS BG_CONTENT"
    user_text = agent.render("test_user.j2", payload="P")
    assert "EX:i1=o1" in user_text
    assert "USER P" in user_text


def test_call_invokes_instructor_with_response_model(prompt_dir):
    raw_client = MagicMock()
    fake_resp = Out(msg="ok")
    with patch("script.agents.base.instructor.from_openai") as ifo:
        patched_client = MagicMock()
        patched_client.chat.completions.create.return_value = fake_resp
        ifo.return_value = patched_client
        agent = LLMAgent(
            name="test",
            prompts_dir=str(prompt_dir),
            client=raw_client,
            model="m",
            instructor_mode="JSON",
        )
        out = agent.call(system="S", user="U", response_model=Out, max_retries=2)

    assert out is fake_resp
    kwargs = patched_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "m"
    assert kwargs["response_model"] is Out
    assert kwargs["max_retries"] == 2
    assert kwargs["messages"] == [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "U"},
    ]


def test_probe_instructor_mode_returns_json_schema_when_supported():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = MagicMock()  # no exception
    mode = probe_instructor_mode(fake_client, model="m")
    assert mode == "JSON_SCHEMA"


def test_probe_instructor_mode_falls_back_to_json_on_error():
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = Exception("400 unsupported")
    mode = probe_instructor_mode(fake_client, model="m")
    assert mode == "JSON"
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `script/agents/base.py`**

```python
import json
from dataclasses import dataclass
from pathlib import Path
import instructor
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel


@dataclass(frozen=True)
class FewShot:
    input: str
    output: str


class LLMAgent:
    def __init__(
        self,
        *,
        name: str,
        prompts_dir: str,
        client,
        model: str,
        instructor_mode: str,
    ) -> None:
        self.name = name
        self.prompts_dir = Path(prompts_dir)
        self.model = model
        self.llm = instructor.from_openai(
            client, mode=getattr(instructor.Mode, instructor_mode)
        )
        self.jinja = Environment(
            loader=FileSystemLoader(str(self.prompts_dir)),
            keep_trailing_newline=False,
            autoescape=False,
        )
        self.background = (self.prompts_dir / "background.md").read_text(encoding="utf-8")
        self.few_shots = self._load_few_shots()

    def _load_few_shots(self) -> list[FewShot]:
        d = self.prompts_dir / "few_shot" / self.name
        if not d.is_dir():
            return []
        out: list[FewShot] = []
        for path in sorted(d.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append(FewShot(input=data["input"], output=data["output"]))
        return out

    def render(self, template: str, **ctx) -> str:
        ctx.setdefault("background", self.background)
        ctx.setdefault("few_shots", self.few_shots)
        return self.jinja.get_template(template).render(**ctx)

    def call(
        self,
        *,
        system: str,
        user: str,
        response_model: type[BaseModel],
        max_retries: int = 3,
    ):
        return self.llm.chat.completions.create(
            model=self.model,
            response_model=response_model,
            max_retries=max_retries,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )


def probe_instructor_mode(client, *, model: str) -> str:
    """Probe the OpenAI-compat server for strict JSON_SCHEMA support.

    Returns "JSON_SCHEMA" if a tiny request succeeds with response_format json_schema,
    else "JSON" (broadly compatible fallback).
    """
    try:
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "probe",
                    "strict": True,
                    "schema": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            },
            max_tokens=4,
        )
        return "JSON_SCHEMA"
    except Exception:
        return "JSON"
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git add script/agents/base.py tests/test_agents_base.py
git commit -m "feat: LLMAgent base with Instructor, Jinja2 prompts, few-shot loader, mode probe"
```

---

## Task 11: Minutes prompts + first few-shot

**Files:**
- Create: `script/prompts/background.md`
- Create: `script/prompts/minutes_system.j2`
- Create: `script/prompts/minutes_map.j2`
- Create: `script/prompts/minutes_reduce.j2`
- Create: `script/prompts/few_shot/minutes/example_001.json`

This task has no code tests — prompt content is validated indirectly by Task 12's agent tests using these files.

- [ ] **Step 1: Create `script/prompts/background.md`**

```markdown
# 公司背景知識

（這是給 LLM 看的背景知識檔。請維護人員依公司實情更新。）

- 公司名稱：（請填）
- 常見部門縮寫：（請填，例如 RD = 研發部、QA = 品保部、PMO = 專案管理辦公室）
- 常見產品代號：（請填）
- 常見會議類型：週會、月會、季度規劃、產品 review、客戶 demo 後檢討
- 常見技術術語：API、Roadmap、Sprint、PR、CI、deploy、staging、prod
```

- [ ] **Step 2: Create `script/prompts/minutes_system.j2`**

```jinja
你是一個專業的會議記錄助手。請從會議逐字稿中抽取「會議結論」與「Action Items」，輸出嚴格符合 schema 的 JSON。

# 規則
1. 來源原句必須是逐字稿中真實出現的句子（可以是片段）。
2. `is_inferred` 旗標：如果該欄位是你從上下文推論而非逐字稿中明確寫出的，設為 true。
3. 找不到的欄位（如 owner 沒有人指派）填「未明」並把對應的 `*_inferred` 設為 true。
4. priority 通常需要推論，故 `priority_inferred` 多為 true。
5. `rationale` 欄位用一句話說明你為何認為這是個 action / 為何給這個 priority，方便人類審查。
6. 如果有 speaker 標籤（SPEAKER_N），把它放進 `source_speaker`；沒有則 null。
7. 不要捏造未在逐字稿中出現的內容。

# 公司背景
{{ background }}
```

- [ ] **Step 3: Create `script/prompts/minutes_map.j2`**

```jinja
{% for s in few_shots %}
範例輸入：
{{ s.input }}

範例輸出：
{{ s.output }}

---
{% endfor %}

請從以下會議逐字稿片段抽取 topics、conclusions、actions（JSON 格式，符合 ChunkExtract schema）：

逐字稿片段（時間 {{ first_timestamp }} ~ {{ last_timestamp }}）：
{{ chunk_text }}
```

- [ ] **Step 4: Create `script/prompts/minutes_reduce.j2`**

```jinja
以下是同一場會議切成多段後，每段個別抽取出的會議資訊。請合併為一份完整、去重、跨段串連的 MeetingMinutes JSON。

合併規則：
- 內容相同的 conclusion / action 視為同一條，合併
- 跨段提到同一個 task 但細節在不同段落出現（如後段才補充 due date），合併資訊
- 保留所有 *_inferred 旗標：只要任何來源段是 inferred，合併後仍為 inferred
- 保留來源原句：選用最完整的一句

各段抽取結果：
{{ chunk_extracts_json }}
```

- [ ] **Step 5: Create `script/prompts/few_shot/minutes/example_001.json`**

```json
{
  "input": "[00:05:12] 那關於下週的 demo，我覺得 API 規格還沒定，這樣動不了。\n[00:05:20] 對，我覺得這個是 blocker，小王你能不能下週五前出 spec？\n[00:05:25] 沒問題我來。\n[00:05:30] OK 那就這樣決定，roadmap 部分我們就照 A 案走。",
  "output": "{\"topics\": [\"API 規格\", \"Roadmap 決議\"], \"conclusions\": [{\"text\": \"下季度 roadmap 採用 A 案\", \"is_inferred\": false, \"source_quote\": \"roadmap 部分我們就照 A 案走\", \"source_timestamp\": \"00:05:30\", \"source_speaker\": null}], \"actions\": [{\"task\": \"完成 API 規格\", \"owner\": \"小王\", \"due\": \"下週五\", \"priority\": \"high\", \"source_quote\": \"小王你能不能下週五前出 spec\", \"source_timestamp\": \"00:05:20\", \"source_speaker\": null, \"rationale\": \"任務由發言直接指定；priority=high 因發言中提到「動不了」、為下週 demo 的 blocker\", \"is_inferred\": false, \"owner_inferred\": false, \"due_inferred\": false, \"priority_inferred\": true}]}",
  "comment": "示範：明示的 conclusion 與 action，priority 由 'blocker' 字眼推論為 high。"
}
```

- [ ] **Step 6: Sanity check — render templates with the test agent**

```bash
.venv/Scripts/python -c "from script.agents.base import LLMAgent; from unittest.mock import MagicMock; a = LLMAgent(name='minutes', prompts_dir='script/prompts', client=MagicMock(), model='m', instructor_mode='JSON'); print(a.render('minutes_system.j2')[:80]); print('---'); print(a.render('minutes_map.j2', chunk_text='X', first_timestamp='00:00:00', last_timestamp='00:01:00')[:200])"
```

Expected: prints two non-empty rendered prompts (system + map). No exception.

- [ ] **Step 7: Commit**

```bash
git add script/prompts/background.md script/prompts/minutes_system.j2 script/prompts/minutes_map.j2 script/prompts/minutes_reduce.j2 script/prompts/few_shot/minutes/example_001.json
git commit -m "feat: minutes agent prompt templates + first few-shot example"
```

---

## Task 12: minutes_agent.py — map-reduce

**Files:**
- Create: `script/agents/minutes_agent.py`
- Create: `tests/test_minutes_agent.py`

- [ ] **Step 1: Write tests**

Create `tests/test_minutes_agent.py`:

```python
from unittest.mock import MagicMock, patch
from script.chunker import Chunk
from script.schemas import (
    Conclusion,
    Action,
    ChunkExtract,
    MeetingMinutes,
)
from script.agents.minutes_agent import MinutesAgent


def _conc(text="c", **over):
    base = dict(
        text=text, is_inferred=False, source_quote="q",
        source_timestamp="00:00:01", source_speaker=None,
    )
    base.update(over)
    return Conclusion(**base)


def _act(task="t", **over):
    base = dict(
        task=task, owner="o", due="d", priority="medium",
        source_quote="q", source_timestamp="00:00:02", source_speaker=None,
        rationale="r", is_inferred=False, owner_inferred=False,
        due_inferred=False, priority_inferred=True,
    )
    base.update(over)
    return Action(**base)


def _make_agent():
    with patch("script.agents.minutes_agent.LLMAgent.__init__", return_value=None):
        a = MinutesAgent.__new__(MinutesAgent)
        a.render = MagicMock(side_effect=lambda tpl, **ctx: f"R({tpl})")
        a.call = MagicMock()
        return a


def test_map_calls_llm_per_chunk():
    a = _make_agent()
    a.call.side_effect = [
        ChunkExtract(topics=["t1"], conclusions=[_conc("c1")], actions=[]),
        ChunkExtract(topics=["t2"], conclusions=[], actions=[_act("a1")]),
    ]
    chunks = [
        Chunk(text="x", first_timestamp="00:00:00", last_timestamp="00:00:10", token_estimate=10),
        Chunk(text="y", first_timestamp="00:00:11", last_timestamp="00:00:20", token_estimate=10),
    ]
    out = a.map_chunks(chunks, parallel=1)
    assert len(out) == 2
    assert out[0].conclusions[0].text == "c1"
    assert out[1].actions[0].task == "a1"
    assert a.call.call_count == 2


def test_reduce_merges_extracts():
    a = _make_agent()
    merged = MeetingMinutes(conclusions=[_conc("merged_c")], actions=[_act("merged_a")])
    a.call.return_value = merged
    extracts = [
        ChunkExtract(topics=[], conclusions=[_conc("c1")], actions=[]),
        ChunkExtract(topics=[], conclusions=[_conc("c2")], actions=[]),
    ]
    out = a.reduce(extracts, max_input_chars=1_000_000)
    assert out is merged
    assert a.call.call_count == 1


def test_reduce_falls_back_to_tree_when_input_too_big():
    a = _make_agent()
    # First two pairwise reductions, then final merge → 3 calls
    a.call.side_effect = [
        MeetingMinutes(conclusions=[_conc("p1")], actions=[]),
        MeetingMinutes(conclusions=[_conc("p2")], actions=[]),
        MeetingMinutes(conclusions=[_conc("final")], actions=[]),
    ]
    extracts = [
        ChunkExtract(topics=[], conclusions=[_conc(f"c{i}")], actions=[])
        for i in range(4)
    ]
    out = a.reduce(extracts, max_input_chars=20)  # tiny limit forces tree
    assert out.conclusions[0].text == "final"
    assert a.call.call_count == 3


def test_assign_ids_after_reduce():
    a = _make_agent()
    minutes = MeetingMinutes(
        conclusions=[_conc("c1"), _conc("c2")],
        actions=[_act("a1"), _act("a2"), _act("a3")],
    )
    ided = a.assign_ids(minutes)
    assert ided["C1"].text == "c1"
    assert ided["C2"].text == "c2"
    assert ided["A1"].task == "a1"
    assert ided["A3"].task == "a3"
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `script/agents/minutes_agent.py`**

```python
import json
from concurrent.futures import ThreadPoolExecutor
from script.agents.base import LLMAgent
from script.chunker import Chunk
from script.schemas import ChunkExtract, MeetingMinutes


class MinutesAgent(LLMAgent):
    def __init__(self, *, prompts_dir: str, client, model: str, instructor_mode: str):
        super().__init__(
            name="minutes",
            prompts_dir=prompts_dir,
            client=client,
            model=model,
            instructor_mode=instructor_mode,
        )

    def map_chunks(self, chunks: list[Chunk], *, parallel: int) -> list[ChunkExtract]:
        sys = self.render("minutes_system.j2")

        def _one(c: Chunk) -> ChunkExtract:
            user = self.render(
                "minutes_map.j2",
                chunk_text=c.text,
                first_timestamp=c.first_timestamp,
                last_timestamp=c.last_timestamp,
            )
            return self.call(system=sys, user=user, response_model=ChunkExtract)

        if parallel <= 1:
            return [_one(c) for c in chunks]
        with ThreadPoolExecutor(max_workers=parallel) as ex:
            return list(ex.map(_one, chunks))

    def reduce(
        self,
        extracts: list[ChunkExtract],
        *,
        max_input_chars: int,
    ) -> MeetingMinutes:
        sys = self.render("minutes_system.j2")
        return self._reduce_recursive(extracts, sys=sys, max_input_chars=max_input_chars)

    def _reduce_recursive(
        self,
        extracts: list[ChunkExtract],
        *,
        sys: str,
        max_input_chars: int,
    ) -> MeetingMinutes:
        payload = json.dumps([e.model_dump() for e in extracts], ensure_ascii=False)
        if len(payload) <= max_input_chars or len(extracts) <= 1:
            user = self.render("minutes_reduce.j2", chunk_extracts_json=payload)
            return self.call(system=sys, user=user, response_model=MeetingMinutes)
        # Tree reduce: pairwise merge then recurse
        partials: list[ChunkExtract] = []
        for i in range(0, len(extracts), 2):
            pair = extracts[i:i + 2]
            sub_payload = json.dumps([e.model_dump() for e in pair], ensure_ascii=False)
            user = self.render("minutes_reduce.j2", chunk_extracts_json=sub_payload)
            mm = self.call(system=sys, user=user, response_model=MeetingMinutes)
            partials.append(
                ChunkExtract(topics=[], conclusions=mm.conclusions, actions=mm.actions)
            )
        return self._reduce_recursive(partials, sys=sys, max_input_chars=max_input_chars)

    @staticmethod
    def assign_ids(minutes: MeetingMinutes) -> dict:
        out: dict = {}
        for i, c in enumerate(minutes.conclusions, start=1):
            out[f"C{i}"] = c
        for i, a in enumerate(minutes.actions, start=1):
            out[f"A{i}"] = a
        return out
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git add script/agents/minutes_agent.py tests/test_minutes_agent.py
git commit -m "feat: MinutesAgent map-reduce with auto tree-reduce + ID assignment"
```

---

## Task 13: Reviewer prompts + first few-shot

**Files:**
- Create: `script/prompts/reviewer_system.j2`
- Create: `script/prompts/reviewer_user.j2`
- Create: `script/prompts/few_shot/reviewer/example_001.json`

- [ ] **Step 1: Create `script/prompts/reviewer_system.j2`**

```jinja
你是一個會議記錄品質審查員。給你一份結構化的會議記錄（含 ID 編號），請逐條檢查：

# 檢查項目
1. **conflict 衝突**：是否有兩條結論或 action 互相矛盾？
2. **ambiguity 語意不明**：是否有結論/任務的關鍵資訊（owner、due、金額、條件）模糊不清？
3. **unreasonable 不合理**：是否有任務的 owner、due、priority 在會議情境下顯得不合理？

# 輸出規則
- **每一條** conclusion 與 action 都要回一筆 ReviewNote，即使是 OK（用 category="ok", severity="info"）
- target_section 用英文 enum：conclusion / action
- target_id 用會議記錄上的 ID（如 C1, A2）
- severity：info（OK）/ warn（建議修正）/ error（嚴重，建議重審）
- note 寫問題描述，suggestion 寫建議的修正方向

# 公司背景
{{ background }}
```

- [ ] **Step 2: Create `script/prompts/reviewer_user.j2`**

```jinja
{% for s in few_shots %}
範例輸入：
{{ s.input }}

範例輸出：
{{ s.output }}

---
{% endfor %}

請審查以下會議記錄（含 ID）：

{{ minutes_with_ids_json }}

對每條 conclusion 與每條 action 回一筆 ReviewNote，輸出 ReviewResult JSON。
```

- [ ] **Step 3: Create `script/prompts/few_shot/reviewer/example_001.json`**

```json
{
  "input": "{\"conclusions\": [{\"id\": \"C1\", \"text\": \"預算上限 500 萬\", \"is_inferred\": true, \"source_quote\": \"大概五百萬左右吧\"}], \"actions\": [{\"id\": \"A1\", \"task\": \"完成 API 規格\", \"owner\": \"小王\", \"due\": \"下週五\", \"priority\": \"high\"}]}",
  "output": "{\"notes\": [{\"target_section\": \"conclusion\", \"target_id\": \"C1\", \"category\": \"ambiguity\", \"severity\": \"warn\", \"note\": \"「左右」一詞讓 500 萬究竟是上限或浮動範圍未明確\", \"suggestion\": \"與會者書面確認此數字含義\"}, {\"target_section\": \"action\", \"target_id\": \"A1\", \"category\": \"ok\", \"severity\": \"info\", \"note\": \"\", \"suggestion\": \"\"}]}",
  "comment": "示範：對 ambiguity 給 warn + 修正建議；對 OK 項目仍要回一筆 info。"
}
```

- [ ] **Step 4: Sanity render**

```bash
.venv/Scripts/python -c "from script.agents.base import LLMAgent; from unittest.mock import MagicMock; a = LLMAgent(name='reviewer', prompts_dir='script/prompts', client=MagicMock(), model='m', instructor_mode='JSON'); print(a.render('reviewer_system.j2')[:80])"
```

Expected: prints rendered system prompt, no exception.

- [ ] **Step 5: Commit**

```bash
git add script/prompts/reviewer_system.j2 script/prompts/reviewer_user.j2 script/prompts/few_shot/reviewer/example_001.json
git commit -m "feat: reviewer agent prompt templates + first few-shot example"
```

---

## Task 14: reviewer_agent.py

**Files:**
- Create: `script/agents/reviewer_agent.py`
- Create: `tests/test_reviewer_agent.py`

- [ ] **Step 1: Write tests**

Create `tests/test_reviewer_agent.py`:

```python
from unittest.mock import MagicMock, patch
from script.schemas import (
    Conclusion,
    Action,
    MeetingMinutes,
    ReviewNote,
    ReviewResult,
)
from script.agents.reviewer_agent import ReviewerAgent


def _conc():
    return Conclusion(
        text="c", is_inferred=False, source_quote="q",
        source_timestamp="00:00:01", source_speaker=None,
    )


def _act():
    return Action(
        task="t", owner="o", due="d", priority="medium",
        source_quote="q", source_timestamp="00:00:02", source_speaker=None,
        rationale="r", is_inferred=False, owner_inferred=False,
        due_inferred=False, priority_inferred=True,
    )


def _make_agent():
    with patch("script.agents.reviewer_agent.LLMAgent.__init__", return_value=None):
        a = ReviewerAgent.__new__(ReviewerAgent)
        a.render = MagicMock(side_effect=lambda tpl, **ctx: f"R({tpl})")
        a.call = MagicMock()
        return a


def test_review_passes_minutes_with_ids_to_llm():
    a = _make_agent()
    notes = ReviewResult(notes=[
        ReviewNote(target_section="conclusion", target_id="C1",
                   category="ok", severity="info", note="", suggestion=""),
        ReviewNote(target_section="action", target_id="A1",
                   category="ok", severity="info", note="", suggestion=""),
    ])
    a.call.return_value = notes
    minutes = MeetingMinutes(conclusions=[_conc()], actions=[_act()])
    out = a.review(minutes)
    assert out is notes
    rendered_user = a.render.call_args_list[1].kwargs["minutes_with_ids_json"]
    assert '"id": "C1"' in rendered_user
    assert '"id": "A1"' in rendered_user
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `script/agents/reviewer_agent.py`**

```python
import json
from script.agents.base import LLMAgent
from script.schemas import MeetingMinutes, ReviewResult


class ReviewerAgent(LLMAgent):
    def __init__(self, *, prompts_dir: str, client, model: str, instructor_mode: str):
        super().__init__(
            name="reviewer",
            prompts_dir=prompts_dir,
            client=client,
            model=model,
            instructor_mode=instructor_mode,
        )

    def review(self, minutes: MeetingMinutes) -> ReviewResult:
        # Embed IDs into the JSON the LLM sees
        payload = {
            "conclusions": [
                {"id": f"C{i+1}", **c.model_dump()}
                for i, c in enumerate(minutes.conclusions)
            ],
            "actions": [
                {"id": f"A{i+1}", **a.model_dump()}
                for i, a in enumerate(minutes.actions)
            ],
        }
        sys = self.render("reviewer_system.j2")
        user = self.render(
            "reviewer_user.j2",
            minutes_with_ids_json=json.dumps(payload, ensure_ascii=False),
        )
        return self.call(system=sys, user=user, response_model=ReviewResult)
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git add script/agents/reviewer_agent.py tests/test_reviewer_agent.py
git commit -m "feat: ReviewerAgent with ID-embedded minutes payload"
```

---

## Task 15: excel_writer.py

**Files:**
- Create: `script/excel_writer.py`
- Create: `tests/test_excel_writer.py`

- [ ] **Step 1: Write tests**

Create `tests/test_excel_writer.py`:

```python
from openpyxl import load_workbook
from script.schemas import (
    Conclusion,
    Action,
    MeetingMinutes,
    ReviewNote,
    ReviewResult,
)
from script.excel_writer import write_minutes_xlsx


INFERRED_FILL_HEX = "FFFFF2CC"  # light yellow


def _conc(text="C-text", inferred=False, speaker=None):
    return Conclusion(
        text=text, is_inferred=inferred, source_quote="q",
        source_timestamp="00:00:01", source_speaker=speaker,
    )


def _act(task="A-task", owner="o", inferred=False, speaker=None):
    return Action(
        task=task, owner=owner, due="2026-05-15", priority="high",
        source_quote="q", source_timestamp="00:00:02", source_speaker=speaker,
        rationale="r", is_inferred=inferred, owner_inferred=False,
        due_inferred=False, priority_inferred=True,
    )


def _ok_note(section, tid):
    return ReviewNote(target_section=section, target_id=tid,
                      category="ok", severity="info", note="", suggestion="")


def _warn_note(section, tid, note="msg"):
    return ReviewNote(target_section=section, target_id=tid,
                      category="ambiguity", severity="warn", note=note, suggestion="fix")


def test_xlsx_has_two_sheets(tmp_path):
    minutes = MeetingMinutes(conclusions=[_conc()], actions=[_act()])
    review = ReviewResult(notes=[_ok_note("conclusion", "C1"), _ok_note("action", "A1")])
    dst = tmp_path / "minutes.xlsx"
    write_minutes_xlsx(minutes, review, str(dst))
    wb = load_workbook(dst)
    assert wb.sheetnames == ["會議記錄", "Review摘要"]


def test_inferred_conclusion_gets_prefix_and_yellow_fill(tmp_path):
    minutes = MeetingMinutes(conclusions=[_conc(text="預算 500 萬", inferred=True)], actions=[])
    review = ReviewResult(notes=[_ok_note("conclusion", "C1")])
    dst = tmp_path / "m.xlsx"
    write_minutes_xlsx(minutes, review, str(dst))
    wb = load_workbook(dst)
    ws = wb["會議記錄"]
    # find the conclusion content cell — col B, first data row
    found = False
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("[LLM推論]"):
                assert "預算 500 萬" in c.value
                assert c.fill.fgColor.rgb == INFERRED_FILL_HEX
                found = True
    assert found, "expected at least one [LLM推論]-prefixed yellow cell"


def test_review_column_filled_per_row(tmp_path):
    minutes = MeetingMinutes(
        conclusions=[_conc(text="c1"), _conc(text="c2")],
        actions=[_act(task="a1")],
    )
    review = ReviewResult(notes=[
        _ok_note("conclusion", "C1"),
        _warn_note("conclusion", "C2", note="模糊"),
        _ok_note("action", "A1"),
    ])
    dst = tmp_path / "m.xlsx"
    write_minutes_xlsx(minutes, review, str(dst))
    ws = load_workbook(dst)["會議記錄"]
    # Pull all cell strings, ensure both warn and ok markers present
    all_strs = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str)]
    assert any("✅" in s for s in all_strs)
    assert any("⚠️" in s and "模糊" in s for s in all_strs)


def test_review_summary_sheet_contains_only_warn_or_error(tmp_path):
    minutes = MeetingMinutes(
        conclusions=[_conc(text="c1"), _conc(text="c2")],
        actions=[],
    )
    review = ReviewResult(notes=[
        _ok_note("conclusion", "C1"),
        _warn_note("conclusion", "C2", note="模糊"),
    ])
    dst = tmp_path / "m.xlsx"
    write_minutes_xlsx(minutes, review, str(dst))
    ws = load_workbook(dst)["Review摘要"]
    all_strs = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str)]
    # Only the C2 warn entry should appear (plus header row)
    assert any("C2" in s for s in all_strs)
    assert not any(isinstance(s, str) and "C1" in s for s in all_strs)
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `script/excel_writer.py`**

```python
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from script.schemas import (
    MeetingMinutes,
    ReviewResult,
    ReviewNote,
)


_INFERRED_PREFIX = "[LLM推論] "
_INFERRED_FILL = PatternFill("solid", fgColor="FFFFF2CC")
_HEADER_FILL = PatternFill("solid", fgColor="FF305496")
_HEADER_FONT = Font(bold=True, color="FFFFFFFF")
_COL_HEADER_FILL = PatternFill("solid", fgColor="FFD9E1F2")
_COL_HEADER_FONT = Font(bold=True)

_SEV_ICON = {"info": "✅", "warn": "⚠️", "error": "❌"}


def _prefix(text: str, inferred: bool) -> str:
    return f"{_INFERRED_PREFIX}{text}" if inferred else text


def _format_review(note: ReviewNote | None) -> str:
    if note is None:
        return ""
    icon = _SEV_ICON.get(note.severity, "")
    if note.category == "ok":
        return f"{icon} OK"
    return f"{icon} {note.category}：{note.note}"


def _index_review(review: ReviewResult) -> dict[tuple[str, str], ReviewNote]:
    return {(n.target_section, n.target_id): n for n in review.notes}


def write_minutes_xlsx(minutes: MeetingMinutes, review: ReviewResult, dst: str) -> None:
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    review_ix = _index_review(review)

    wb = Workbook()
    ws = wb.active
    ws.title = "會議記錄"

    # ---- Section: 會議結論 ----
    conc_headers = ["編號", "結論內容", "來源原句", "時間戳", "發言者", "Review檢查結果"]
    _write_section_header(ws, row=1, title="會議結論", span=len(conc_headers))
    _write_column_headers(ws, row=2, headers=conc_headers)
    next_row = 3
    for i, c in enumerate(minutes.conclusions, start=1):
        cid = f"C{i}"
        rev = review_ix.get(("conclusion", cid))
        text_cell = _prefix(c.text, c.is_inferred)
        ws.cell(row=next_row, column=1, value=cid)
        cell_text = ws.cell(row=next_row, column=2, value=text_cell)
        if c.is_inferred:
            cell_text.fill = _INFERRED_FILL
        ws.cell(row=next_row, column=3, value=c.source_quote)
        ws.cell(row=next_row, column=4, value=c.source_timestamp)
        ws.cell(row=next_row, column=5, value=c.source_speaker or "")
        ws.cell(row=next_row, column=6, value=_format_review(rev))
        next_row += 1

    # blank separator row
    next_row += 1

    # ---- Section: Action Items ----
    act_headers = [
        "編號", "任務", "負責人", "期限", "優先度",
        "來源原句", "時間戳", "發言者", "LLM判斷依據", "Review檢查結果",
    ]
    _write_section_header(ws, row=next_row, title="Action Items", span=len(act_headers))
    _write_column_headers(ws, row=next_row + 1, headers=act_headers)
    next_row += 2
    for i, a in enumerate(minutes.actions, start=1):
        aid = f"A{i}"
        rev = review_ix.get(("action", aid))
        ws.cell(row=next_row, column=1, value=aid)

        task_cell = ws.cell(row=next_row, column=2, value=_prefix(a.task, a.is_inferred))
        if a.is_inferred:
            task_cell.fill = _INFERRED_FILL

        owner_cell = ws.cell(row=next_row, column=3, value=_prefix(a.owner, a.owner_inferred))
        if a.owner_inferred:
            owner_cell.fill = _INFERRED_FILL

        due_cell = ws.cell(row=next_row, column=4, value=_prefix(a.due, a.due_inferred))
        if a.due_inferred:
            due_cell.fill = _INFERRED_FILL

        prio_cell = ws.cell(
            row=next_row, column=5, value=_prefix(a.priority, a.priority_inferred)
        )
        if a.priority_inferred:
            prio_cell.fill = _INFERRED_FILL

        ws.cell(row=next_row, column=6, value=a.source_quote)
        ws.cell(row=next_row, column=7, value=a.source_timestamp)
        ws.cell(row=next_row, column=8, value=a.source_speaker or "")
        ws.cell(row=next_row, column=9, value=a.rationale)
        ws.cell(row=next_row, column=10, value=_format_review(rev))
        next_row += 1

    # column widths
    for col in range(1, 11):
        ws.column_dimensions[get_column_letter(col)].width = 18
    ws.freeze_panes = "A3"

    # ---- Sheet 2: Review 摘要 ----
    ws2 = wb.create_sheet("Review摘要")
    sum_headers = ["對應位置", "編號", "類型", "嚴重度", "說明", "建議修正"]
    _write_column_headers(ws2, row=1, headers=sum_headers)
    sec_label = {"conclusion": "結論", "action": "Action"}
    r = 2
    for n in review.notes:
        if n.severity in ("warn", "error"):
            ws2.cell(row=r, column=1, value=sec_label[n.target_section])
            ws2.cell(row=r, column=2, value=n.target_id)
            ws2.cell(row=r, column=3, value=n.category)
            ws2.cell(row=r, column=4, value=n.severity)
            ws2.cell(row=r, column=5, value=n.note)
            ws2.cell(row=r, column=6, value=n.suggestion)
            r += 1
    for col in range(1, 7):
        ws2.column_dimensions[get_column_letter(col)].width = 22

    wb.save(dst)


def _write_section_header(ws, *, row: int, title: str, span: int) -> None:
    ws.cell(row=row, column=1, value=title)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    cell = ws.cell(row=row, column=1)
    cell.font = _HEADER_FONT
    cell.fill = _HEADER_FILL
    cell.alignment = Alignment(horizontal="left", vertical="center")


def _write_column_headers(ws, *, row: int, headers: list[str]) -> None:
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=i, value=h)
        c.font = _COL_HEADER_FONT
        c.fill = _COL_HEADER_FILL
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git add script/excel_writer.py tests/test_excel_writer.py
git commit -m "feat: excel writer with two sections, inferred styling, review column"
```

---

## Task 16: markdown_writer.py — review_report.md

**Files:**
- Modify: `script/markdown_writer.py`
- Modify: `tests/test_markdown_writer.py`

- [ ] **Step 1: Add tests** to `tests/test_markdown_writer.py`:

```python
from script.schemas import (
    Conclusion,
    Action,
    MeetingMinutes,
    ReviewNote,
    ReviewResult,
)
from script.markdown_writer import write_review_report_md


def _c(text="c"):
    return Conclusion(
        text=text, is_inferred=False, source_quote="q",
        source_timestamp="00:00:01", source_speaker="SPEAKER_1",
    )


def _a(task="a"):
    return Action(
        task=task, owner="o", due="2026-05-15", priority="high",
        source_quote="q", source_timestamp="00:00:02", source_speaker=None,
        rationale="r", is_inferred=False, owner_inferred=False,
        due_inferred=False, priority_inferred=True,
    )


def test_review_report_groups_warn_and_ok(tmp_path):
    minutes = MeetingMinutes(conclusions=[_c("c1"), _c("c2")], actions=[_a("a1")])
    review = ReviewResult(notes=[
        ReviewNote(target_section="conclusion", target_id="C1",
                   category="ok", severity="info", note="", suggestion=""),
        ReviewNote(target_section="conclusion", target_id="C2",
                   category="ambiguity", severity="warn", note="模糊", suggestion="確認"),
        ReviewNote(target_section="action", target_id="A1",
                   category="ok", severity="info", note="", suggestion=""),
    ])
    dst = tmp_path / "review_report.md"
    write_review_report_md(
        minutes, review, str(dst),
        meeting_file="x.mp4", diarization_enabled=True, speakers_detected=2,
    )
    text = dst.read_text(encoding="utf-8")
    assert "# Meeting Review Report" in text
    assert "**會議檔案**: x.mp4" in text
    assert "**Diarization**: enabled (2 speakers detected)" in text
    assert "1 warn / 0 error / 2 OK" in text
    assert "C2 — ambiguity" in text
    assert "模糊" in text
    assert "## ✅ OK (2)" in text
    assert "C1: c1" in text
    assert "A1: a1" in text
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Add to `script/markdown_writer.py`** (append, do not remove the transcript writer):

```python
from script.schemas import MeetingMinutes, ReviewResult, ReviewNote


def write_review_report_md(
    minutes: MeetingMinutes,
    review: ReviewResult,
    dst: str,
    *,
    meeting_file: str,
    diarization_enabled: bool,
    speakers_detected: int,
) -> None:
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    notes = review.notes
    warns = [n for n in notes if n.severity == "warn"]
    errors = [n for n in notes if n.severity == "error"]
    oks = [n for n in notes if n.severity == "info"]

    diar_str = (
        f"enabled ({speakers_detected} speakers detected)"
        if diarization_enabled else "disabled"
    )
    lines: list[str] = [
        "# Meeting Review Report",
        f"**會議檔案**: {meeting_file}",
        f"**Diarization**: {diar_str}",
        f"**Review 結果**: {len(warns)} warn / {len(errors)} error / {len(oks)} OK",
        "",
        "---",
        "",
    ]

    if errors:
        lines.append(f"## ❌ Error ({len(errors)})")
        for n in errors:
            lines.extend(_render_note(n, minutes))
        lines.append("")

    if warns:
        lines.append(f"## ⚠️ Warning ({len(warns)})")
        for n in warns:
            lines.extend(_render_note(n, minutes))
        lines.append("")

    if oks:
        lines.append(f"## ✅ OK ({len(oks)})")
        for n in oks:
            label = _ok_label(n, minutes)
            lines.append(f"- {n.target_id}: {label}")

    Path(dst).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _lookup(minutes: MeetingMinutes, n: ReviewNote):
    if n.target_section == "conclusion":
        idx = int(n.target_id[1:]) - 1
        return minutes.conclusions[idx] if 0 <= idx < len(minutes.conclusions) else None
    idx = int(n.target_id[1:]) - 1
    return minutes.actions[idx] if 0 <= idx < len(minutes.actions) else None


def _ok_label(n: ReviewNote, minutes: MeetingMinutes) -> str:
    item = _lookup(minutes, n)
    if item is None:
        return "(missing)"
    if n.target_section == "conclusion":
        return item.text
    return f"{item.task} ({item.owner} / {item.due})"


def _render_note(n: ReviewNote, minutes: MeetingMinutes) -> list[str]:
    item = _lookup(minutes, n)
    section_label = "結論" if n.target_section == "conclusion" else "Action"
    out = [f"### {section_label} {n.target_id} — {n.category}"]
    if item is not None:
        if n.target_section == "conclusion":
            prefix = "[LLM推論] " if item.is_inferred else ""
            out.append(f"> {prefix}{item.text}")
            sp = f", {item.source_speaker}" if item.source_speaker else ""
            out.append(f"> 來源：「{item.source_quote}」({item.source_timestamp}{sp})")
        else:
            prefix = "[LLM推論] " if item.is_inferred else ""
            out.append(f"> {prefix}{item.task}（{item.owner} / {item.due}）")
            sp = f", {item.source_speaker}" if item.source_speaker else ""
            out.append(f"> 來源：「{item.source_quote}」({item.source_timestamp}{sp})")
    out.append("")
    out.append(f"**問題**：{n.note}")
    out.append(f"**建議**：{n.suggestion}")
    out.append("")
    return out
```

- [ ] **Step 4: Run — pass (full file)**

```bash
.venv/Scripts/pytest tests/test_markdown_writer.py -v
```

Expected: 3 passed (2 transcript + 1 review report).

- [ ] **Step 5: Commit**

```bash
git add script/markdown_writer.py tests/test_markdown_writer.py
git commit -m "feat: review_report.md writer with warn/error/ok grouping"
```

---

## Task 17: pipeline.py — orchestrator with stage cache

**Files:**
- Create: `script/pipeline.py`
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write tests**

Create `tests/test_pipeline.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from script.config import Settings
from script.transcribe import Segment
from script.diarize import SpeakerSegment, TranscribedSegment
from script.schemas import (
    Conclusion, Action, ChunkExtract, MeetingMinutes, ReviewResult, ReviewNote,
)
from script.pipeline import run_pipeline


def _settings(tmp_path, **over):
    base = dict(
        OPENAI_API_KEY="sk-x", OPENAI_API_BASE="https://x/v1", OPENAI_MODEL="m",
        OUT_DIR=str(tmp_path / "out"), LOG_DIR=str(tmp_path / "log"),
    )
    base.update(over)
    return Settings(**base)


def _conc(): return Conclusion(text="c", is_inferred=False, source_quote="q",
                                source_timestamp="00:00:01", source_speaker=None)
def _act(): return Action(task="t", owner="o", due="d", priority="medium",
                          source_quote="q", source_timestamp="00:00:02",
                          source_speaker=None, rationale="r", is_inferred=False,
                          owner_inferred=False, due_inferred=False, priority_inferred=True)


@patch("script.pipeline.write_minutes_xlsx")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_transcript_md")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.transcribe")
@patch("script.pipeline.extract_audio")
def test_pipeline_runs_all_stages_diarization_off(
    extract, transcribe_m, chunk_m, MAm, RAm,
    write_t, write_r, write_x, tmp_path,
):
    settings = _settings(tmp_path)
    transcribe_m.return_value = [Segment(0.0, 1.0, "hi")]
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

    run_pipeline("in.mp4", settings=settings, name="t")

    extract.assert_called_once()
    transcribe_m.assert_called_once()
    write_t.assert_called_once()
    write_x.assert_called_once()
    write_r.assert_called_once()


@patch("script.pipeline.write_minutes_xlsx")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_transcript_md")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.diarize")
@patch("script.pipeline.assign_speakers")
@patch("script.pipeline.transcribe")
@patch("script.pipeline.extract_audio")
def test_pipeline_invokes_diarize_when_enabled(
    extract, transcribe_m, assign_m, diarize_m, chunk_m, MAm, RAm,
    write_t, write_r, write_x, tmp_path,
):
    settings = _settings(tmp_path, ENABLE_DIARIZATION="true", HF_TOKEN="hf_x")
    transcribe_m.return_value = [Segment(0.0, 1.0, "hi")]
    diarize_m.return_value = [SpeakerSegment(0.0, 1.0, "SPEAKER_1")]
    assign_m.return_value = [TranscribedSegment(0.0, 1.0, "hi", "SPEAKER_1")]
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

    run_pipeline("in.mp4", settings=settings, name="t")

    diarize_m.assert_called_once()
    assign_m.assert_called_once()


@patch("script.pipeline.write_minutes_xlsx")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_transcript_md")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.transcribe")
@patch("script.pipeline.extract_audio")
def test_pipeline_skips_transcribe_when_cache_exists(
    extract, transcribe_m, chunk_m, MAm, RAm,
    write_t, write_r, write_x, tmp_path,
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

    run_pipeline("in.mp4", settings=settings, name="t", force=False)

    extract.assert_not_called()
    transcribe_m.assert_not_called()
    write_t.assert_not_called()
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `script/pipeline.py`**

```python
import json
from pathlib import Path
from openai import OpenAI

from script.config import Settings
from script.logger import setup_logger, log_kv
from script.media import extract_audio
from script.transcribe import transcribe, Segment
from script.diarize import diarize, assign_speakers, TranscribedSegment
from script.chunker import chunk_transcript
from script.markdown_writer import write_transcript_md, write_review_report_md
from script.excel_writer import write_minutes_xlsx
from script.agents.base import probe_instructor_mode
from script.agents.minutes_agent import MinutesAgent
from script.agents.reviewer_agent import ReviewerAgent


def run_pipeline(
    src: str,
    *,
    settings: Settings,
    name: str | None = None,
    force: bool = False,
    skip_transcribe: bool = False,
    diarize_override: bool | None = None,
) -> None:
    base_name = name or Path(src).stem
    out_dir = Path(settings.out_dir) / base_name
    inter_dir = out_dir / "intermediate"
    out_dir.mkdir(parents=True, exist_ok=True)
    inter_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logger("pipeline", log_dir=settings.log_dir, level=settings.log_level)
    log_kv(logger, "INFO", "pipeline.start", file=src, name=base_name)

    audio_path = inter_dir / "audio.wav"
    transcript_path = out_dir / "transcript.md"

    diar_enabled = (
        diarize_override if diarize_override is not None else settings.enable_diarization
    )

    # Stage 1+2 (+optional 2.5): produce transcript.md
    if force or not transcript_path.exists():
        if force or not audio_path.exists():
            extract_audio(src, str(audio_path))
            log_kv(logger, "INFO", "stage.media", output=str(audio_path))
        if skip_transcribe and not transcript_path.exists():
            raise RuntimeError("--skip-transcribe used but no cached transcript.md exists")
        segments = transcribe(
            str(audio_path),
            model=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            language=settings.whisper_language,
            initial_prompt=settings.whisper_initial_prompt,
            vad_filter=settings.whisper_vad_filter,
        )
        log_kv(logger, "INFO", "stage.transcribe", segments=len(segments))

        speakers_detected = 0
        if diar_enabled:
            speaker_segs = diarize(
                str(audio_path),
                model=settings.diarization_model,
                hf_token=settings.hf_token,
            )
            speakers_detected = len({s.label for s in speaker_segs})
            log_kv(logger, "INFO", "stage.diarize", speakers=speakers_detected)
            (inter_dir / "diarization.json").write_text(
                json.dumps([s.__dict__ for s in speaker_segs], ensure_ascii=False),
                encoding="utf-8",
            )
            merged = assign_speakers(segments, speaker_segs)
            write_transcript_md(merged, str(transcript_path))
        else:
            write_transcript_md(segments, str(transcript_path))
    else:
        log_kv(logger, "INFO", "stage.transcribe.cached", path=str(transcript_path))
        speakers_detected = 0  # unknown when using cache; report as 0 in cache path

    # Stage 3: Minutes
    transcript_text = transcript_path.read_text(encoding="utf-8")
    chunks = chunk_transcript(
        transcript_text,
        max_tokens=settings.llm_chunk_tokens,
        overlap_ratio=settings.llm_chunk_overlap_ratio,
    )
    (inter_dir / "chunks.json").write_text(
        json.dumps([c.__dict__ for c in chunks], ensure_ascii=False), encoding="utf-8",
    )
    log_kv(logger, "INFO", "stage.chunk", chunks=len(chunks))

    client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_api_base)
    mode = probe_instructor_mode(client, model=settings.openai_model)
    log_kv(logger, "INFO", "instructor.mode", mode=mode)

    minutes_agent = MinutesAgent(
        prompts_dir="script/prompts", client=client,
        model=settings.openai_model, instructor_mode=mode,
    )
    extracts = minutes_agent.map_chunks(chunks, parallel=settings.llm_parallel_map)
    (inter_dir / "map_outputs.json").write_text(
        json.dumps([e.model_dump() for e in extracts], ensure_ascii=False),
        encoding="utf-8",
    )
    minutes = minutes_agent.reduce(
        extracts, max_input_chars=settings.llm_chunk_tokens * 2,
    )
    (inter_dir / "minutes.json").write_text(
        minutes.model_dump_json(), encoding="utf-8",
    )
    log_kv(logger, "INFO", "stage.minutes",
           conclusions=len(minutes.conclusions), actions=len(minutes.actions))

    # Stage 4: Review
    reviewer = ReviewerAgent(
        prompts_dir="script/prompts", client=client,
        model=settings.openai_model, instructor_mode=mode,
    )
    review = reviewer.review(minutes)
    (inter_dir / "review.json").write_text(
        review.model_dump_json(), encoding="utf-8",
    )
    warns = sum(1 for n in review.notes if n.severity == "warn")
    errors = sum(1 for n in review.notes if n.severity == "error")
    log_kv(logger, "INFO", "stage.review",
           items=len(review.notes), warns=warns, errors=errors)

    # Outputs
    write_minutes_xlsx(minutes, review, str(out_dir / "minutes.xlsx"))
    write_review_report_md(
        minutes, review, str(out_dir / "review_report.md"),
        meeting_file=src,
        diarization_enabled=diar_enabled,
        speakers_detected=speakers_detected,
    )
    log_kv(logger, "INFO", "pipeline.done", out=str(out_dir))
```

- [ ] **Step 4: Run — pass**

```bash
.venv/Scripts/pytest tests/test_pipeline.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add script/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline orchestrator with stage cache + optional diarization"
```

---

## Task 18: main.py — typer CLI

**Files:**
- Create: `script/main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write tests**

Create `tests/test_main.py`:

```python
from unittest.mock import patch
from typer.testing import CliRunner
from script.main import app


def test_cli_passes_basic_args(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("OPENAI_API_BASE", "https://x/v1")
    monkeypatch.setenv("OPENAI_MODEL", "m")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(app, ["meeting.mp4", "--name", "test", "--force"])
    assert result.exit_code == 0, result.output
    args, kwargs = run.call_args
    assert args[0] == "meeting.mp4"
    assert kwargs["name"] == "test"
    assert kwargs["force"] is True
    assert kwargs["skip_transcribe"] is False
    assert kwargs["diarize_override"] is None


def test_cli_diarize_flag_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("OPENAI_API_BASE", "https://x/v1")
    monkeypatch.setenv("OPENAI_MODEL", "m")
    monkeypatch.setenv("HF_TOKEN", "hf_x")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(app, ["meeting.mp4", "--diarize"])
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["diarize_override"] is True
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `script/main.py`**

```python
import typer
from script.config import Settings
from script.pipeline import run_pipeline


app = typer.Typer(help="Convert meeting audio/video to structured Excel minutes.")


@app.command()
def process(
    src: str = typer.Argument(..., help="Path to audio/video file."),
    name: str | None = typer.Option(None, "--name", help="Output folder name (defaults to src basename)."),
    force: bool = typer.Option(False, "--force", help="Ignore stage cache, re-run all stages."),
    skip_transcribe: bool = typer.Option(False, "--skip-transcribe", help="Reuse existing transcript.md only."),
    diarize: bool | None = typer.Option(
        None, "--diarize/--no-diarize",
        help="Override .env ENABLE_DIARIZATION for this run.",
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
        skip_transcribe=skip_transcribe,
        diarize_override=diarize,
    )


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run — pass**

```bash
.venv/Scripts/pytest tests/test_main.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Smoke check — print help**

```bash
.venv/Scripts/python script/main.py --help
```

Expected: typer-rendered help text listing `--name`, `--force`, `--skip-transcribe`, `--diarize/--no-diarize`, `-v`.

- [ ] **Step 6: Commit**

```bash
git add script/main.py tests/test_main.py
git commit -m "feat: typer CLI entry point with --diarize override"
```

---

## Task 19: README — install, ffmpeg, HF token, troubleshooting

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `README.md`** with full content:

````markdown
# Meeting Minutes System

Convert long meeting audio/video into a structured Excel minutes file plus a Markdown review report, using on-prem OpenAI-compatible LLM, faster-whisper for ASR, and optional pyannote diarization.

See `doc/specs/2026-05-06-meeting-minutes-design.md` for the full design.

## Prerequisites

- Python 3.11 or newer
- ffmpeg on PATH (download from https://ffmpeg.org/)
- (Optional) HuggingFace account + token if you want speaker diarization

## Install

```bash
git clone <this repo>
cd AudioVideoToMeetingMinutes
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows
# Linux/Mac: .venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` to fill in:
- `OPENAI_API_KEY` — your company LLM key
- `OPENAI_API_BASE` — your company LLM endpoint
- `OPENAI_MODEL` — model name on that endpoint

## (Optional) Enable Speaker Diarization

1. Create a HuggingFace account at https://huggingface.co/
2. Visit https://huggingface.co/pyannote/speaker-diarization-community-1 and accept the gated model terms
3. Create a token at https://huggingface.co/settings/tokens (read access is enough)
4. In `.env` set:
   - `ENABLE_DIARIZATION=true`
   - `HF_TOKEN=hf_...`
5. First run will download model files (~500 MB pyannote + ~1.2 GB wav2vec2 alignment) into `~/.cache/huggingface/`. After that, fully offline.

## Usage

```bash
# Basic
python script/main.py path/to/meeting.mp4

# Specify output folder name
python script/main.py meeting.mp4 --name 2026Q2_planning

# Force re-run all stages (ignore cached intermediates)
python script/main.py meeting.mp4 --force

# Reuse existing transcript.md (e.g. you hand-corrected it)
python script/main.py meeting.mp4 --skip-transcribe

# Override diarization for this run
python script/main.py meeting.mp4 --diarize       # turn on
python script/main.py meeting.mp4 --no-diarize    # turn off
```

Outputs land in `out/<basename>/`:
- `minutes.xlsx` — Sheet 1 (會議結論 + Action Items), Sheet 2 (Review 摘要)
- `review_report.md` — human-friendly review summary
- `transcript.md` — timestamped (with speaker labels if diarization enabled)
- `intermediate/` — chunks, raw map outputs, minutes JSON, review JSON, audio.wav (debug)

Logs land in `log/run_YYYYMMDD-HHMMSS.log`.

## Tests

```bash
.venv/Scripts/pytest
```

All unit tests use mocks — no models are downloaded.

## Troubleshooting

**`FFmpegMissingError`**: Install ffmpeg and ensure it's on PATH. On Windows you may need to log out / log back in after editing PATH.

**Whisper model download is slow / blocked**: Pre-download the model on a machine with internet:
```bash
python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3')"
```
The model lands in `~/.cache/huggingface/hub/`. Copy that directory to the target machine.

**Diarization fails with `401 unauthorized`**: HF token missing or you didn't accept the gated model terms. See "Enable Speaker Diarization" above.

**LLM keeps returning malformed JSON**: Lower `LLM_CHUNK_TOKENS` so each prompt is smaller, or check that `OPENAI_API_BASE` points to a server that supports `response_format=json_object` (most OpenAI-compatible servers do).

**Out of memory on Whisper**: Set `WHISPER_COMPUTE_TYPE=int8` for CPU, or `int8_float16` for GPU. Last resort: `WHISPER_MODEL=medium` (some Chinese accuracy loss).

**Pipeline crashed mid-run**: Re-run the same command. Stages with cached intermediates (`audio.wav`, `transcript.md`) are skipped automatically. Use `--force` to redo everything.
````

- [ ] **Step 2: Run full test suite as final smoke**

```bash
.venv/Scripts/pytest
```

Expected: all tests pass (~25-30 tests across the 19 tasks).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: full README with install, diarization setup, troubleshooting"
```

---

## Task 20: TranscriptCorrector — Stage 2.95 專有名詞 LLM 修正

**Background:** Spec v3 §4.8 — Whisper 對中文人名/產品名易拼錯，會污染下游所有抽取。在 chunker 前加保守修正。**這個 task 在 T1-T19 全部完成、pipeline 能跑後再做**（增量加 stage）。

**Files:**
- Create: `script/agents/corrector_agent.py`
- Create: `script/transcript_corrector.py`
- Create: `script/prompts/corrector_system.j2`
- Create: `script/prompts/corrector_user.j2`
- Create: `script/prompts/glossary.md`
- Create: `script/prompts/few_shot/corrector/example_001.json`
- Create: `tests/test_corrector_agent.py`
- Create: `tests/test_transcript_corrector.py`
- Modify: `script/schemas.py` — add `CorrectionDiff`, `CorrectionResult`
- Modify: `script/config.py` — add `enable_proper_noun_correction`, `glossary_file`
- Modify: `script/pipeline.py` — insert Stage 2.95 between transcript write and chunker
- Modify: `tests/test_pipeline.py` — add corrector enabled/disabled tests
- Modify: `tests/test_schemas.py` — add validation tests for new schemas
- Modify: `tests/test_config.py` — add tests for new fields
- Modify: `README.md` — document `ENABLE_PROPER_NOUN_CORRECTION` + glossary

- [ ] **Step 1: Add schemas to `script/schemas.py`**

```python
class CorrectionDiff(BaseModel):
    original: str
    corrected: str
    matched_term: str
    timestamp: str


class CorrectionResult(BaseModel):
    corrected_text: str
    diffs: list[CorrectionDiff]
```

Add a test in `tests/test_schemas.py`:

```python
from script.schemas import CorrectionDiff, CorrectionResult


def test_correction_result_holds_diffs():
    r = CorrectionResult(
        corrected_text="x",
        diffs=[CorrectionDiff(original="a", corrected="b", matched_term="b", timestamp="00:00:01")],
    )
    assert len(r.diffs) == 1
```

- [ ] **Step 2: Add config fields to `script/config.py`**

```python
    # === Transcript Correction (Stage 2.95) ===
    enable_proper_noun_correction: bool = Field(False, alias="ENABLE_PROPER_NOUN_CORRECTION")
    glossary_file: str = Field("script/prompts/glossary.md", alias="GLOSSARY_FILE")
```

Add a test to `tests/test_config.py`:

```python
def test_proper_noun_correction_default_false(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_BASE", "https://x.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.enable_proper_noun_correction is False
    assert s.glossary_file == "script/prompts/glossary.md"
```

- [ ] **Step 3: Run schema + config tests — pass**

```bash
.venv/Scripts/pytest tests/test_schemas.py tests/test_config.py -v
```

- [ ] **Step 4: Create `script/prompts/glossary.md`**

```markdown
# 術語表（人類維護）

corrector 只會修正下方列出的詞彙在 transcript 中的常見錯誤拼寫，其他內容一字不動。

## 人名
- 小王（不要寫成：肖王、小汪）

## 產品 / 專案代號
- Phoenix（不要寫成：菲尼克斯、鳳凰）

## 部門 / 縮寫
- RD = 研發部
- PMO = 專案管理辦公室
- Sprint（保持英文，不要音譯成「司普林特」）
```

- [ ] **Step 5: Create `script/prompts/corrector_system.j2`**

```jinja
你是一個極度保守的會議逐字稿術語修正員。給你一份術語表與一段逐字稿，你的工作是：

# 唯一的修正規則
- 只修正術語表內列出的詞彙在逐字稿中的常見錯誤拼寫
- 其他內容**一字不動**：不改字、不改標點、不改時間戳、不改換行、不修文法、不縮短、不擴寫
- 找不到該修正的詞彙就回原文不變

# 輸出
- corrected_text：修正後的完整逐字稿
- diffs：每筆修正記錄 (original, corrected, matched_term, timestamp)

# 術語表
{{ glossary }}

# 公司背景
{{ background }}
```

- [ ] **Step 6: Create `script/prompts/corrector_user.j2`**

```jinja
{% for s in few_shots %}
範例輸入：
{{ s.input }}

範例輸出：
{{ s.output }}

---
{% endfor %}

請修正以下逐字稿片段，輸出 CorrectionResult JSON：

{{ chunk_text }}
```

- [ ] **Step 7: Create `script/prompts/few_shot/corrector/example_001.json`**

```json
{
  "input": "[00:01:05] 肖王你下週要不要去客戶那邊做菲尼克斯的 demo？\n[00:01:15] 司普林特那邊我先 review。",
  "output": "{\"corrected_text\": \"[00:01:05] 小王你下週要不要去客戶那邊做 Phoenix 的 demo？\\n[00:01:15] Sprint 那邊我先 review。\", \"diffs\": [{\"original\": \"肖王\", \"corrected\": \"小王\", \"matched_term\": \"小王\", \"timestamp\": \"00:01:05\"}, {\"original\": \"菲尼克斯\", \"corrected\": \"Phoenix\", \"matched_term\": \"Phoenix\", \"timestamp\": \"00:01:05\"}, {\"original\": \"司普林特\", \"corrected\": \"Sprint\", \"matched_term\": \"Sprint\", \"timestamp\": \"00:01:15\"}]}",
  "comment": "示範：時間戳、標點、其他字一字不動。"
}
```

- [ ] **Step 8: Write `tests/test_corrector_agent.py`**

```python
from unittest.mock import MagicMock, patch
from script.schemas import CorrectionResult, CorrectionDiff
from script.agents.corrector_agent import CorrectorAgent


def _make_agent():
    with patch("script.agents.corrector_agent.LLMAgent.__init__", return_value=None):
        a = CorrectorAgent.__new__(CorrectorAgent)
        a.render = MagicMock(side_effect=lambda tpl, **ctx: f"R({tpl})")
        a.call = MagicMock()
        return a


def test_correct_returns_llm_result():
    a = _make_agent()
    expect = CorrectionResult(
        corrected_text="x",
        diffs=[CorrectionDiff(original="a", corrected="b", matched_term="b", timestamp="00:00:01")],
    )
    a.call.return_value = expect
    out = a.correct(chunk_text="raw", glossary="g")
    assert out is expect
    # glossary should be passed into render context for the system template
    sys_kwargs = a.render.call_args_list[0].kwargs
    assert sys_kwargs.get("glossary") == "g"
```

- [ ] **Step 9: Implement `script/agents/corrector_agent.py`**

```python
from script.agents.base import LLMAgent
from script.schemas import CorrectionResult


class CorrectorAgent(LLMAgent):
    def __init__(self, *, prompts_dir: str, client, model: str, instructor_mode: str):
        super().__init__(
            name="corrector",
            prompts_dir=prompts_dir,
            client=client,
            model=model,
            instructor_mode=instructor_mode,
        )

    def correct(self, *, chunk_text: str, glossary: str) -> CorrectionResult:
        sys = self.render("corrector_system.j2", glossary=glossary)
        user = self.render("corrector_user.j2", chunk_text=chunk_text)
        return self.call(system=sys, user=user, response_model=CorrectionResult)
```

- [ ] **Step 10: Run corrector agent tests — pass**

```bash
.venv/Scripts/pytest tests/test_corrector_agent.py -v
```

- [ ] **Step 11: Write `tests/test_transcript_corrector.py`**

```python
from unittest.mock import MagicMock, patch
from script.schemas import CorrectionResult, CorrectionDiff
from script.transcript_corrector import correct_transcript


def test_correct_transcript_chunks_and_concatenates(tmp_path):
    src = tmp_path / "t.md"
    src.write_text(
        "[00:00:01] 肖王您好。\n[00:00:05] 菲尼克斯產品。\n",
        encoding="utf-8",
    )
    glossary_path = tmp_path / "glossary.md"
    glossary_path.write_text("- 小王\n- Phoenix\n", encoding="utf-8")
    diff_path = tmp_path / "diff.json"
    raw_backup = tmp_path / "t.raw.md"

    fake_agent = MagicMock()
    fake_agent.correct.return_value = CorrectionResult(
        corrected_text="[00:00:01] 小王您好。\n[00:00:05] Phoenix 產品。",
        diffs=[
            CorrectionDiff(original="肖王", corrected="小王", matched_term="小王", timestamp="00:00:01"),
            CorrectionDiff(original="菲尼克斯", corrected="Phoenix", matched_term="Phoenix", timestamp="00:00:05"),
        ],
    )

    correct_transcript(
        transcript_path=str(src),
        glossary_path=str(glossary_path),
        diff_path=str(diff_path),
        raw_backup_path=str(raw_backup),
        agent=fake_agent,
        chunk_chars=1000,
    )

    # transcript was overwritten with corrected
    assert "小王" in src.read_text(encoding="utf-8")
    assert "Phoenix" in src.read_text(encoding="utf-8")
    # raw was backed up
    assert "肖王" in raw_backup.read_text(encoding="utf-8")
    # diffs persisted
    import json
    diffs = json.loads(diff_path.read_text(encoding="utf-8"))
    assert len(diffs) == 2
    assert diffs[0]["matched_term"] == "小王"


def test_skip_when_glossary_empty(tmp_path):
    src = tmp_path / "t.md"
    src.write_text("[00:00:01] x\n", encoding="utf-8")
    glossary_path = tmp_path / "glossary.md"
    glossary_path.write_text("\n  \n", encoding="utf-8")  # whitespace only
    diff_path = tmp_path / "diff.json"
    raw_backup = tmp_path / "t.raw.md"

    fake_agent = MagicMock()
    correct_transcript(
        transcript_path=str(src),
        glossary_path=str(glossary_path),
        diff_path=str(diff_path),
        raw_backup_path=str(raw_backup),
        agent=fake_agent,
        chunk_chars=1000,
    )
    fake_agent.correct.assert_not_called()
    assert not raw_backup.exists()  # no backup when no work done
```

- [ ] **Step 12: Implement `script/transcript_corrector.py`**

```python
import json
import re
import shutil
from pathlib import Path
from script.schemas import CorrectionResult


def _is_glossary_meaningful(text: str) -> bool:
    """True if glossary has at least one non-comment, non-blank bullet."""
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return True
    return False


def _split_by_chars(text: str, chunk_chars: int) -> list[str]:
    """Split transcript text on newlines, accumulating up to chunk_chars per chunk."""
    lines = text.splitlines(keepends=True)
    chunks: list[str] = []
    buf = ""
    for line in lines:
        if buf and len(buf) + len(line) > chunk_chars:
            chunks.append(buf)
            buf = line
        else:
            buf += line
    if buf:
        chunks.append(buf)
    return chunks


def correct_transcript(
    *,
    transcript_path: str,
    glossary_path: str,
    diff_path: str,
    raw_backup_path: str,
    agent,
    chunk_chars: int,
) -> None:
    glossary = Path(glossary_path).read_text(encoding="utf-8")
    if not _is_glossary_meaningful(glossary):
        # nothing to correct → leave transcript alone
        return

    raw_text = Path(transcript_path).read_text(encoding="utf-8")
    chunks = _split_by_chars(raw_text, chunk_chars)

    corrected_parts: list[str] = []
    all_diffs: list[dict] = []
    for chunk in chunks:
        result: CorrectionResult = agent.correct(chunk_text=chunk, glossary=glossary)
        corrected_parts.append(result.corrected_text)
        all_diffs.extend([d.model_dump() for d in result.diffs])

    # back up raw, overwrite transcript, write diffs
    shutil.copyfile(transcript_path, raw_backup_path)
    Path(transcript_path).write_text("\n".join(corrected_parts), encoding="utf-8")
    Path(diff_path).parent.mkdir(parents=True, exist_ok=True)
    Path(diff_path).write_text(
        json.dumps(all_diffs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
```

- [ ] **Step 13: Run transcript_corrector tests — pass**

```bash
.venv/Scripts/pytest tests/test_transcript_corrector.py -v
```

Expected: 2 passed.

- [ ] **Step 14: Wire into `script/pipeline.py`**

Add import at top:

```python
from script.transcript_corrector import correct_transcript
from script.agents.corrector_agent import CorrectorAgent
```

Insert this block in `run_pipeline`, **immediately after `write_transcript_md(...)` (or `write_transcript_md(merged, ...)`) and BEFORE `# Stage 3: Minutes`**:

```python
    # Stage 2.95: optional proper-noun correction
    if settings.enable_proper_noun_correction:
        client_for_corrector = OpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_api_base
        )
        mode_pre = probe_instructor_mode(client_for_corrector, model=settings.openai_model)
        corrector = CorrectorAgent(
            prompts_dir="script/prompts", client=client_for_corrector,
            model=settings.openai_model, instructor_mode=mode_pre,
        )
        correct_transcript(
            transcript_path=str(transcript_path),
            glossary_path=settings.glossary_file,
            diff_path=str(inter_dir / "correction_diff.json"),
            raw_backup_path=str(out_dir / "transcript.raw.md"),
            agent=corrector,
            chunk_chars=settings.llm_chunk_tokens,  # use same budget as minutes
        )
        log_kv(logger, "INFO", "stage.corrector", enabled=True)
```

Then in **the existing `client = OpenAI(...)` line for Stage 3**, replace it with reuse of the same client (or just recreate — both fine; recreating is simpler for the diff):

```python
    client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_api_base)
    mode = probe_instructor_mode(client, model=settings.openai_model)
```

(No change required if you leave the existing client/mode block as-is — the corrector block above just adds a separate client. This duplicates one HTTP call to probe but keeps the diff minimal.)

- [ ] **Step 15: Add pipeline tests for corrector path** in `tests/test_pipeline.py`

```python
@patch("script.pipeline.write_minutes_xlsx")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_transcript_md")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.transcribe")
@patch("script.pipeline.extract_audio")
@patch("script.pipeline.correct_transcript")
@patch("script.pipeline.CorrectorAgent")
def test_pipeline_invokes_corrector_when_enabled(
    CAm, correct_m, extract, transcribe_m, chunk_m, MAm, RAm,
    write_t, write_r, write_x, tmp_path,
):
    settings = _settings(tmp_path, ENABLE_PROPER_NOUN_CORRECTION="true")
    transcribe_m.return_value = [Segment(0.0, 1.0, "hi")]
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

    run_pipeline("in.mp4", settings=settings, name="t")

    correct_m.assert_called_once()
    CAm.assert_called_once()
```

- [ ] **Step 16: Run all pipeline tests — pass**

```bash
.venv/Scripts/pytest tests/test_pipeline.py -v
```

Expected: 4 passed (3 original + 1 corrector path).

- [ ] **Step 17: Update `README.md`**

Add a section after the "Optional: Enable Speaker Diarization" block:

```markdown
## (Optional) Enable Proper-Noun Correction

Whisper occasionally mis-transcribes Chinese proper nouns (人名, 公司名, 產品名). To fix this:

1. Edit `script/prompts/glossary.md` and list your common terms (人名 / 產品 / 縮寫).
2. In `.env` set `ENABLE_PROPER_NOUN_CORRECTION=true`.
3. Each run will:
   - Save the original transcript as `out/<name>/transcript.raw.md`.
   - Overwrite `transcript.md` with the corrected version.
   - Log every change to `out/<name>/intermediate/correction_diff.json` for audit.

The LLM is prompted with a strictly conservative rule: **only fix terms listed in glossary.md, change nothing else**.
```

- [ ] **Step 18: Run full test suite as final smoke**

```bash
.venv/Scripts/pytest
```

Expected: all tests pass (~32-35 tests now).

- [ ] **Step 19: Commit (split into two commits for review clarity)**

```bash
# 1. New module + prompts + tests
git add script/agents/corrector_agent.py script/transcript_corrector.py script/prompts/corrector_system.j2 script/prompts/corrector_user.j2 script/prompts/glossary.md script/prompts/few_shot/corrector/example_001.json script/schemas.py script/config.py tests/test_corrector_agent.py tests/test_transcript_corrector.py tests/test_schemas.py tests/test_config.py
git commit -m "feat: TranscriptCorrector agent for conservative proper-noun fix"

# 2. Wire into pipeline + docs
git add script/pipeline.py tests/test_pipeline.py README.md
git commit -m "feat: integrate Stage 2.95 proper-noun correction into pipeline"
```

---

## Self-Review Notes

- **Spec coverage**: every section in `doc/specs/2026-05-06-meeting-minutes-design.md` maps to at least one task — config (T2, T20), logger (T3), schemas (T4, T20), media (T5), transcribe (T6), diarize (T7), transcript writer (T8), chunker (T9), agent base + Instructor probe (T10), minutes prompts (T11), minutes agent (T12), reviewer prompts (T13), reviewer agent (T14), excel writer (T15), review report writer (T16), pipeline (T17, T20), CLI (T18), README (T19, T20), Stage 2.95 corrector (T20).
- **No placeholders**: every step contains real code or an exact command. No "TBD", no "implement later".
- **Type consistency**: `Segment` (Task 6) ↔ `TranscribedSegment` (Task 7) ↔ `write_transcript_md` accepts both via `isinstance` check (Task 8). `MeetingMinutes`, `ChunkExtract`, `ReviewResult` defined in Task 4 are referenced consistently in Tasks 12, 14, 15, 16, 17.
- **Stage cache** behavior tested explicitly in Task 17 (`test_pipeline_skips_transcribe_when_cache_exists`).
- **Diarization optional** tested in Task 17 (both on and off paths).
- **First few-shot** committed for both agents (Tasks 11, 13) so the system works out of the box; future few-shot files just drop into the same folder.
