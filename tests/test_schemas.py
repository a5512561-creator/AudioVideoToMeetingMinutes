import pytest
from pydantic import ValidationError
from script.schemas import (
    Conclusion,
    Action,
    KeyPoint,
    ChunkExtract,
    MeetingMinutes,
    ReviewNote,
)


def _conclusion(**over):
    base = dict(
        text="x",
        is_inferred=False,
        source_quote="y",
        source_timestamp="00:00:01",
        source_speaker=None,
    )
    base.update(over)
    return Conclusion(**base)


def _action(**over):
    base = dict(
        task="t",
        owner="o",
        due="2026-05-15",
        priority="medium",
        source_quote="q",
        source_timestamp="00:00:02",
        source_speaker=None,
        rationale="r",
        is_inferred=False,
        owner_inferred=False,
        due_inferred=False,
        priority_inferred=True,
    )
    base.update(over)
    return Action(**base)


def test_conclusion_speaker_optional():
    c = _conclusion(source_speaker="SPEAKER_1")
    assert c.source_speaker == "SPEAKER_1"
    c2 = _conclusion(source_speaker=None)
    assert c2.source_speaker is None


def test_action_priority_must_be_enum():
    with pytest.raises(ValidationError):
        _action(priority="urgent")  # not in enum


def test_meeting_minutes_holds_lists():
    m = MeetingMinutes(conclusions=[_conclusion()], actions=[_action()])
    assert len(m.conclusions) == 1 and len(m.actions) == 1


def test_review_note_target_section_enum():
    ReviewNote(
        target_section="conclusion",
        target_id="C1",
        category="ok",
        severity="info",
        note="",
        suggestion="",
    )
    with pytest.raises(ValidationError):
        ReviewNote(
            target_section="結論",  # must be english enum
            target_id="C1",
            category="ok",
            severity="info",
            note="",
            suggestion="",
        )


def _key_point(**over):
    base = dict(
        text="k",
        is_inferred=False,
        source_quote="kq",
        source_timestamp="00:00:03",
        source_speaker=None,
    )
    base.update(over)
    return KeyPoint(**base)


def test_key_point_fields():
    kp = _key_point(text="spec 項目說明", source_speaker="SPEAKER_2")
    assert kp.text == "spec 項目說明"
    assert kp.source_speaker == "SPEAKER_2"
    assert not kp.is_inferred


def test_chunk_extract_holds_key_points():
    ce = ChunkExtract(
        topics=["t1"],
        conclusions=[_conclusion()],
        actions=[_action()],
        key_points=[_key_point()],
    )
    assert len(ce.key_points) == 1


def test_chunk_extract_key_points_defaults_to_empty():
    ce = ChunkExtract(topics=["t1"], conclusions=[_conclusion()], actions=[_action()])
    assert ce.key_points == []


def test_meeting_minutes_holds_key_points():
    m = MeetingMinutes(
        conclusions=[_conclusion()],
        actions=[_action()],
        key_points=[_key_point()],
    )
    assert len(m.key_points) == 1


def test_meeting_minutes_key_points_defaults_to_empty():
    m = MeetingMinutes(conclusions=[_conclusion()], actions=[_action()])
    assert m.key_points == []


def test_review_note_accepts_key_point_section():
    ReviewNote(
        target_section="key_point",
        target_id="K1",
        category="ok",
        severity="info",
        note="",
        suggestion="",
    )


def test_chunk_extract_holds_topics_conclusions_actions():
    ce = ChunkExtract(topics=["t1"], conclusions=[_conclusion()], actions=[_action()])
    assert ce.topics == ["t1"]


from script.schemas import CorrectionDiff, CorrectionResult


def test_correction_result_holds_diffs():
    r = CorrectionResult(
        corrected_text="x",
        diffs=[CorrectionDiff(original="a", corrected="b", matched_term="b", timestamp="00:00:01")],
    )
    assert len(r.diffs) == 1


from script.schemas import (
    SynthTopic, SynthAction, SourceRef, MeetingMeta, SynthesizedMinutes,
)


def test_synth_topic_defaults():
    t = SynthTopic(title="KPI 訂定", summary="討論摘要")
    assert t.decisions == [] and t.source_timestamps == []


def test_synth_action_priority_enum():
    a = SynthAction(task="試算 KTR", owner="未明", due="未明", priority="high")
    assert a.source_timestamps == []
    with pytest.raises(ValidationError):
        SynthAction(task="x", owner="未明", due="未明", priority="urgent")


def test_synthesized_minutes_meta_optional_and_nested():
    sm = SynthesizedMinutes(
        topics=[SynthTopic(title="t", summary="s", decisions=["d"])],
        action_items=[SynthAction(task="x", owner="未明", due="未明", priority="low")],
        source_index=[SourceRef(label="決議 1", timestamps=["00:08:34"])],
    )
    assert sm.meta is None
    sm.meta = MeetingMeta(meeting_date="2026/05/18", duration_hint="逐字稿長度約 1h 55m")
    assert sm.meta.meeting_date == "2026/05/18"
    assert sm.topics[0].decisions == ["d"]
