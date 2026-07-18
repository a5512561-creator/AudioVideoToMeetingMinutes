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


def test_meeting_meta_new_fields_default_empty():
    from script.schemas import MeetingMeta
    m = MeetingMeta(meeting_date="2026/06/04", duration_hint="約 2h")
    assert m.meeting_time == ""
    assert m.location == ""
    assert m.attendees == ""
    assert m.recorder == ""
    assert m.doc_links == ""
    assert m.video_links == ""
    assert m.jira == ""
    assert m.llm_model == ""


def test_finalized_minutes_model():
    from script.schemas import (
        FinalizedMinutes, FinalTopic, FinalAction, MeetingMeta,
    )
    f = FinalizedMinutes(
        meta=MeetingMeta(meeting_date="2026/06/04", duration_hint="約 2h"),
        subject="會議記錄",
        topics=[FinalTopic(item="主題A", summary="摘要A（決議：X）")],
        actions=[FinalAction(task="做X", owner="Alice", due="6/E", note="")],
    )
    assert f.topics[0].item == "主題A"
    assert f.actions[0].note == ""
    assert FinalizedMinutes.model_validate_json(f.model_dump_json()) == f


def test_audit_result_defaults_and_roundtrip():
    from script.schemas import (
        AuditCheckMechanical, AuditCheckSemantic, AuditResult,
    )
    r = AuditResult(
        mechanical=[AuditCheckMechanical(
            key="action_owner_present", label="每個 Action 有負責人",
            passed=False, offending=["A3"])],
        semantic=[AuditCheckSemantic(
            key="fluency", label="語句通順", score=4, rationale="大致通順")],
    )
    # defaults
    assert r.overall_pass is False
    assert r.reviewed is False
    # offending default is []
    assert AuditCheckMechanical(key="k", label="l", passed=True).offending == []
    # JSON round-trips (used to write/read intermediate/audit.json)
    back = AuditResult.model_validate_json(r.model_dump_json())
    assert back.mechanical[0].offending == ["A3"]
    assert back.semantic[0].score == 4


def test_semantic_audit_is_llm_response_model():
    from script.schemas import SemanticAudit, AuditCheckSemantic
    s = SemanticAudit(checks=[AuditCheckSemantic(
        key="traceable", label="可追溯", score=5, rationale="每條決議都有依據")])
    assert s.checks[0].key == "traceable"
    assert SemanticAudit().checks == []  # empty default
