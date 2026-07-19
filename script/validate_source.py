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
