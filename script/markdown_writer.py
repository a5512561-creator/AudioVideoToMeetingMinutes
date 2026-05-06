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
