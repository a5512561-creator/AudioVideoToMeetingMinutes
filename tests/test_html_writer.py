import re
from script.schemas import (
    Conclusion, Action, KeyPoint, MeetingMinutes,
    ReviewNote, ReviewResult,
)
from script.html_writer import write_minutes_html


def _conc(text="C-text", inferred=False, speaker=None):
    return Conclusion(
        text=text, is_inferred=inferred, source_quote="src-c",
        source_timestamp="00:01:00", source_speaker=speaker,
    )


def _kp(text="K-text", inferred=False, speaker=None):
    return KeyPoint(
        text=text, is_inferred=inferred, source_quote="src-k",
        source_timestamp="00:02:00", source_speaker=speaker,
    )


def _act(task="A-task", owner="o", inferred=False, speaker=None):
    return Action(
        task=task, owner=owner, due="2026-05-15", priority="high",
        source_quote="src-a", source_timestamp="00:03:00", source_speaker=speaker,
        rationale="r", is_inferred=inferred, owner_inferred=False,
        due_inferred=False, priority_inferred=True,
    )


def _ok_note(section, tid):
    return ReviewNote(target_section=section, target_id=tid,
                      category="ok", severity="info", note="", suggestion="")


def _warn_note(section, tid, note="msg"):
    return ReviewNote(target_section=section, target_id=tid,
                      category="ambiguity", severity="warn", note=note, suggestion="fix")


def test_html_contains_all_sections(tmp_path):
    minutes = MeetingMinutes(
        conclusions=[_conc("c1")],
        key_points=[_kp("k1")],
        actions=[_act("a1")],
    )
    review = ReviewResult(notes=[
        _ok_note("conclusion", "C1"),
        _ok_note("key_point", "K1"),
        _ok_note("action", "A1"),
    ])
    dst = tmp_path / "m.html"
    write_minutes_html(
        minutes, review, str(dst),
        meeting_file="meeting.mp4",
        diarization_enabled=False, speakers_detected=0,
    )
    text = dst.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in text
    assert "c1" in text and "k1" in text and "a1" in text
    assert 'data-tab="conclusions"' in text
    assert 'data-tab="keypoints"' in text
    assert 'data-tab="actions"' in text
    assert 'data-tab="review"' in text


def test_inferred_items_get_marker(tmp_path):
    minutes = MeetingMinutes(
        conclusions=[_conc("inferred c", inferred=True)],
        key_points=[],
        actions=[],
    )
    review = ReviewResult(notes=[_ok_note("conclusion", "C1")])
    dst = tmp_path / "m.html"
    write_minutes_html(
        minutes, review, str(dst),
        meeting_file="x", diarization_enabled=False, speakers_detected=0,
    )
    text = dst.read_text(encoding="utf-8")
    assert "[LLM推論]" in text or "LLM推論" in text  # inferred marker


def test_speaker_map_substitutes_in_html(tmp_path):
    minutes = MeetingMinutes(
        conclusions=[_conc("c1", speaker="SPEAKER_00")],
        key_points=[],
        actions=[_act("a1", speaker="SPEAKER_01")],
    )
    review = ReviewResult(notes=[
        _ok_note("conclusion", "C1"),
        _ok_note("action", "A1"),
    ])
    dst = tmp_path / "m.html"
    write_minutes_html(
        minutes, review, str(dst),
        meeting_file="x", diarization_enabled=True, speakers_detected=2,
        speaker_map={"SPEAKER_00": "Albert", "SPEAKER_01": "John"},
    )
    text = dst.read_text(encoding="utf-8")
    assert "Albert" in text
    assert "John" in text
    assert "SPEAKER_00" not in text
    assert "SPEAKER_01" not in text


def test_review_summary_only_shows_warn_and_error(tmp_path):
    minutes = MeetingMinutes(
        conclusions=[_conc("c1"), _conc("c2")],
        key_points=[],
        actions=[],
    )
    review = ReviewResult(notes=[
        _ok_note("conclusion", "C1"),
        _warn_note("conclusion", "C2", note="模糊"),
    ])
    dst = tmp_path / "m.html"
    write_minutes_html(
        minutes, review, str(dst),
        meeting_file="x", diarization_enabled=False, speakers_detected=0,
    )
    text = dst.read_text(encoding="utf-8")
    # C1 is OK — should NOT appear in review section, but C2 should
    review_match = re.search(r'<section id="review".*?</section>', text, re.DOTALL)
    assert review_match
    review_html = review_match.group(0)
    assert "模糊" in review_html
    assert "#C2" in review_html  # anchor link


def test_owner_remap_via_remap_text(tmp_path):
    # action.owner is a free-text field; LLM may put SPEAKER_NN there
    minutes = MeetingMinutes(
        conclusions=[],
        key_points=[],
        actions=[_act("a1", owner="SPEAKER_01")],
    )
    review = ReviewResult(notes=[_ok_note("action", "A1")])
    dst = tmp_path / "m.html"
    write_minutes_html(
        minutes, review, str(dst),
        meeting_file="x", diarization_enabled=True, speakers_detected=1,
        speaker_map={"SPEAKER_01": "John"},
    )
    text = dst.read_text(encoding="utf-8")
    assert "John" in text
    assert "SPEAKER_01" not in text


def test_html_is_self_contained_no_external_assets(tmp_path):
    minutes = MeetingMinutes(conclusions=[_conc("c1")], key_points=[], actions=[])
    review = ReviewResult(notes=[_ok_note("conclusion", "C1")])
    dst = tmp_path / "m.html"
    write_minutes_html(
        minutes, review, str(dst),
        meeting_file="x", diarization_enabled=False, speakers_detected=0,
    )
    text = dst.read_text(encoding="utf-8")
    # No CDN includes
    assert "cdn." not in text.lower()
    assert "//unpkg" not in text
    # No relative <link href="..."> for external CSS
    assert '<link rel="stylesheet" href' not in text
    # Inline style + script blocks present
    assert "<style>" in text
    assert "<script>" in text
