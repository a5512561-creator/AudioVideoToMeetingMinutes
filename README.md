# Meeting Minutes System

Convert meeting audio/video into structured Excel minutes via on-prem LLM.

## Setup

1. Install ffmpeg and put it on PATH.
2. `python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`
3. `cp .env.example .env` and fill in `OPENAI_*` values.
4. (Optional) For speaker diarization: apply for HuggingFace token and accept gated model terms — see `doc/specs/`.

## Usage

```bash
python script/main.py path/to/meeting.mp4
```

See `doc/specs/2026-05-06-meeting-minutes-design.md` for full design.
