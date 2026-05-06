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
