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
