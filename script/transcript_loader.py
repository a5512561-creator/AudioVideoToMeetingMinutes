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
