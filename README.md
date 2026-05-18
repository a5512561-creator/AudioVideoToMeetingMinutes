# Meeting Minutes System

Convert a prepared meeting transcript into structured minutes (HTML) plus a Markdown review report, using an on-prem OpenAI-compatible LLM.

See `doc/specs/2026-05-18-transcript-to-minutes-design.md` for the current architecture. The earlier design document `doc/specs/2026-05-06-meeting-minutes-design.md` is kept as historical reference.

## Prerequisites

- Python 3.11 or newer

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

## Input Format

The tool expects a UTF-8 encoded transcript file. Each block consists of a timestamp line (`MM:SS` or `H:MM:SS`) followed by one or more lines of spoken text:

```
00:00
這件事情改善多少可以所以聽，所以我才想弄問過你說...
00:10
我覺得剛剛說的你根本沒辦法定半年 ok...
```

No speaker labels are expected in the transcript. Speaker-labeled transcript support is a planned future feature (see `doc/specs/2026-05-18-transcript-to-minutes-design.md` §8); for now transcripts are processed without speaker identification.

## (Optional) Enable Proper-Noun Correction

The source transcript may contain mis-recognized Chinese proper nouns (人名, 公司名, 產品名). To fix this:

1. Edit `script/prompts/glossary.md` and list your common terms (人名 / 產品 / 縮寫).
2. In `.env` set `ENABLE_PROPER_NOUN_CORRECTION=true`.
3. Each run will:
   - Save the original transcript as `out\<name>\transcript.raw.md`.
   - Overwrite `transcript.md` with the corrected version.
   - Log every change to `out\<name>\intermediate\correction_diff.json` for audit.

The LLM is prompted with a strictly conservative rule: **only fix terms listed in glossary.md, change nothing else**.

## Usage

```powershell
# Basic
python -m script.main process path\to\transcript.txt

# Specify output folder name
python -m script.main process transcript.txt --name 2026Q2_planning

# Force re-run all stages (ignore cached intermediates)
python -m script.main process transcript.txt --force

# Re-render outputs from cached minutes.json + review.json (no LLM)
python -m script.main process transcript.txt --name 2026Q2_planning --rerender
```

Outputs land in `out\<name>\`:
- `minutes.html` — tabbed HTML with 會議結論, Action Items, and Review sections
- `review_report.md` — human-friendly review summary
- `transcript.md` — normalized, timestamped transcript (no speaker labels)
- `intermediate\` — chunks, raw map outputs, minutes.json, review.json

Logs land in `log\run_YYYYMMDD-HHMMSS.log`.

## Tests

```powershell
.venv\Scripts\pytest
```

Tests are hermetic and require no network access or downloaded models.

## Troubleshooting

**LLM keeps returning malformed JSON**: Lower `LLM_CHUNK_TOKENS` so each prompt is smaller, or check that `OPENAI_API_BASE` points to a server that supports `response_format=json_object` (most OpenAI-compatible servers do).

**Pipeline crashed mid-run**: Re-run the same command. Stages with a cached `transcript.md` are skipped automatically. Use `--force` to redo everything from scratch.
