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
2. Run the LLM-free readiness check and read only its metadata output:
   `python -m script.main validate "<transcript path>"`
3. If it reports OK, run the on-prem pipeline:
   `python -m script.main process "<transcript path>" --name "<name>" --llm company`
4. Everything (map/reduce/review/synth/audit) runs on the company endpoint. You
   never open the transcript; you only read command stdout.
5. Open the editable page so the user can edit the minutes and export to Outlook:
   `python -m script.main edit "<name>"`
   The user edits topics / decisions / actions in the browser; the export button
   unlocks only when the mechanical audit passes and they tick "已審閱", then it
   writes email.html to the folder and opens an Outlook draft.

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
4. Open the editable page: `python -m script.main edit "<name>"` (same as the
   company route — edit in the browser, then export to an Outlook draft).

## Notes
- The CLI refuses a full run without `--llm` (backstop). The PreToolUse hook
  blocks reads of locked files (mechanical isolation): it finds the lock by
  walking up from the file being read, so it works even when your working
  directory is the repo root and the meeting folder is elsewhere. This skill
  asking first is the primary gate. All three must agree before confidential
  content moves.
