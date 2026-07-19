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

# Plain Android-Recorder style: MM:SS or HH:MM:SS at line start (optionally bracketed).
_TS_PLAIN = re.compile(r"^\s*\[?(\d{1,2}:\d{2}(?::\d{2})?)\b")
# WebVTT cue-timing line: HH:MM:SS.mmm --> HH:MM:SS.mmm (the real .vtt source format).
_TS_VTT = re.compile(r"^\s*(\d{2}:\d{2}:\d{2})\.\d+\s+-->")


def _extract_timestamp(line: str) -> str | None:
    m = _TS_VTT.match(line)
    if m:
        return m.group(1)
    m = _TS_PLAIN.match(line)
    if m:
        return m.group(1)
    return None

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
        ts = _extract_timestamp(line)
        if ts:
            stamps.append(ts)
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
