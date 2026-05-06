# Meeting Minutes System

Convert long meeting audio/video into a structured Excel minutes file plus a Markdown review report, using on-prem OpenAI-compatible LLM, faster-whisper for ASR, and optional pyannote diarization.

See `doc/specs/2026-05-06-meeting-minutes-design.md` for the full design.

## Prerequisites

- Python 3.11 or newer
- ffmpeg on PATH (download from https://ffmpeg.org/)
- (Optional) HuggingFace account + token if you want speaker diarization

## Install

```powershell
git clone <this repo>
cd AudioVideoToMeetingMinutes
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
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

```powershell
# Basic
python script\main.py path\to\meeting.mp4

# Specify output folder name
python script\main.py meeting.mp4 --name 2026Q2_planning

# Force re-run all stages (ignore cached intermediates)
python script\main.py meeting.mp4 --force

# Reuse existing transcript.md (e.g. you hand-corrected it)
python script\main.py meeting.mp4 --skip-transcribe

# Override diarization for this run
python script\main.py meeting.mp4 --diarize       # turn on
python script\main.py meeting.mp4 --no-diarize    # turn off
```

Outputs land in `out\<basename>\`:
- `minutes.xlsx` — Sheet 1 (會議結論 + Action Items), Sheet 2 (Review 摘要)
- `review_report.md` — human-friendly review summary
- `transcript.md` — timestamped (with speaker labels if diarization enabled)
- `intermediate\` — chunks, raw map outputs, minutes JSON, review JSON, audio.wav (debug)

Logs land in `log\run_YYYYMMDD-HHMMSS.log`.

## Tests

```powershell
.venv\Scripts\pytest
```

All unit tests use mocks — no models are downloaded.

## Troubleshooting

**`FFmpegMissingError`**: Install ffmpeg and ensure it's on PATH. On Windows you may need to log out / log back in after editing PATH.

**Whisper model download is slow / blocked**: Pre-download the model on a machine with internet:
```powershell
.venv\Scripts\python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3')"
```
The model lands in `~/.cache/huggingface/hub/`. Copy that directory to the target machine.

**Diarization fails with `401 unauthorized`**: HF token missing or you didn't accept the gated model terms. See "Enable Speaker Diarization" above.

**LLM keeps returning malformed JSON**: Lower `LLM_CHUNK_TOKENS` so each prompt is smaller, or check that `OPENAI_API_BASE` points to a server that supports `response_format=json_object` (most OpenAI-compatible servers do).

**Out of memory on Whisper**: Set `WHISPER_COMPUTE_TYPE=int8` for CPU, or `int8_float16` for GPU. Last resort: `WHISPER_MODEL=medium` (some Chinese accuracy loss).

**Pipeline crashed mid-run**: Re-run the same command. Stages with cached intermediates (`audio.wav`, `transcript.md`) are skipped automatically. Use `--force` to redo everything.
