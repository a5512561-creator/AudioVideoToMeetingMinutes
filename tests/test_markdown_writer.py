from script.transcribe import Segment
from script.diarize import TranscribedSegment
from script.markdown_writer import write_transcript_md


def test_transcript_without_speaker(tmp_path):
    segs = [
        Segment(start=5.0, end=8.0, text="那我們先講第一個議題。"),
        Segment(start=12.5, end=20.0, text="上週會議達成共識。"),
    ]
    dst = tmp_path / "transcript.md"
    write_transcript_md(segs, str(dst))
    text = dst.read_text(encoding="utf-8")
    assert text == (
        "[00:00:05] 那我們先講第一個議題。\n"
        "[00:00:12] 上週會議達成共識。\n"
    )


def test_transcript_with_speaker(tmp_path):
    segs = [
        TranscribedSegment(start=5.0, end=8.0, text="第一個議題。", speaker="SPEAKER_1"),
        TranscribedSegment(start=12.5, end=20.0, text="達成共識。", speaker="SPEAKER_2"),
    ]
    dst = tmp_path / "transcript.md"
    write_transcript_md(segs, str(dst))
    text = dst.read_text(encoding="utf-8")
    assert text == (
        "[00:00:05] SPEAKER_1: 第一個議題。\n"
        "[00:00:12] SPEAKER_2: 達成共識。\n"
    )


from script.schemas import (
    Conclusion,
    Action,
    MeetingMinutes,
    ReviewNote,
    ReviewResult,
)
from script.markdown_writer import write_review_report_md


def _c(text="c"):
    return Conclusion(
        text=text, is_inferred=False, source_quote="q",
        source_timestamp="00:00:01", source_speaker="SPEAKER_1",
    )


def _a(task="a"):
    return Action(
        task=task, owner="o", due="2026-05-15", priority="high",
        source_quote="q", source_timestamp="00:00:02", source_speaker=None,
        rationale="r", is_inferred=False, owner_inferred=False,
        due_inferred=False, priority_inferred=True,
    )


def test_review_report_groups_warn_and_ok(tmp_path):
    minutes = MeetingMinutes(conclusions=[_c("c1"), _c("c2")], actions=[_a("a1")])
    review = ReviewResult(notes=[
        ReviewNote(target_section="conclusion", target_id="C1",
                   category="ok", severity="info", note="", suggestion=""),
        ReviewNote(target_section="conclusion", target_id="C2",
                   category="ambiguity", severity="warn", note="模糊", suggestion="確認"),
        ReviewNote(target_section="action", target_id="A1",
                   category="ok", severity="info", note="", suggestion=""),
    ])
    dst = tmp_path / "review_report.md"
    write_review_report_md(
        minutes, review, str(dst),
        meeting_file="x.mp4", diarization_enabled=True, speakers_detected=2,
    )
    text = dst.read_text(encoding="utf-8")
    assert "# Meeting Review Report" in text
    assert "**會議檔案**: x.mp4" in text
    assert "**Diarization**: enabled (2 speakers detected)" in text
    assert "1 warn / 0 error / 2 OK" in text
    assert "C2 — ambiguity" in text
    assert "模糊" in text
    assert "## ✅ OK (2)" in text
    assert "C1: c1" in text
    assert "A1: a1" in text
