import pytest
from pydantic import ValidationError
from script.schemas import (
    Conclusion,
    Action,
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
