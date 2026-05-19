"""Best-effort meeting metadata the transcript itself cannot supply.

Date is inferred from the output name / source filename; meeting duration
is a *hint* derived from the transcript timestamp span (NOT wall-clock).
"""
import re
from pathlib import Path

_DATE_SEP = re.compile(r"(20\d{2})[-/](\d{2})[-/](\d{2})")
_DATE_8 = re.compile(r"(20\d{2})(\d{2})(\d{2})")
_TS = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\]")


def infer_meeting_date(name: str | None, src: str) -> str:
    """Return 'YYYY/MM/DD' from name/src basename, else the literal
    placeholder 'YYYY/MM/DD'. `name` wins over `src`."""
    for cand in ([name] if name else []) + [Path(src).stem]:
        m = _DATE_SEP.search(cand) or _DATE_8.search(cand)
        if m:
            return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return "YYYY/MM/DD"


def duration_hint(transcript_md_text: str) -> str:
    """Hint string from the [HH:MM:SS] span; '逐字稿長度未知' if none."""
    ts = _TS.findall(transcript_md_text)
    if not ts:
        return "逐字稿長度未知"
    secs = [int(h) * 3600 + int(m) * 60 + int(s) for h, m, s in ts]
    span = max(secs) - min(secs)
    h, rem = divmod(span, 3600)
    return f"逐字稿長度約 {h}h {rem // 60}m"
