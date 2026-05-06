from unittest.mock import MagicMock, patch
from script.schemas import (
    Conclusion,
    Action,
    KeyPoint,
    MeetingMinutes,
    ReviewNote,
    ReviewResult,
)
from script.agents.reviewer_agent import ReviewerAgent


def _conc():
    return Conclusion(
        text="c", is_inferred=False, source_quote="q",
        source_timestamp="00:00:01", source_speaker=None,
    )


def _act():
    return Action(
        task="t", owner="o", due="d", priority="medium",
        source_quote="q", source_timestamp="00:00:02", source_speaker=None,
        rationale="r", is_inferred=False, owner_inferred=False,
        due_inferred=False, priority_inferred=True,
    )


def _kp():
    return KeyPoint(
        text="k", is_inferred=False, source_quote="kq",
        source_timestamp="00:00:03", source_speaker=None,
    )


def _make_agent():
    with patch("script.agents.reviewer_agent.LLMAgent.__init__", return_value=None):
        a = ReviewerAgent.__new__(ReviewerAgent)
        a.render = MagicMock(side_effect=lambda tpl, **ctx: f"R({tpl})")
        a.call = MagicMock()
        return a


def test_review_passes_minutes_with_ids_to_llm():
    a = _make_agent()
    notes = ReviewResult(notes=[
        ReviewNote(target_section="conclusion", target_id="C1",
                   category="ok", severity="info", note="", suggestion=""),
        ReviewNote(target_section="key_point", target_id="K1",
                   category="ok", severity="info", note="", suggestion=""),
        ReviewNote(target_section="action", target_id="A1",
                   category="ok", severity="info", note="", suggestion=""),
    ])
    a.call.return_value = notes
    minutes = MeetingMinutes(conclusions=[_conc()], key_points=[_kp()], actions=[_act()])
    out = a.review(minutes)
    assert out is notes
    rendered_user = a.render.call_args_list[1].kwargs["minutes_with_ids_json"]
    assert '"id": "C1"' in rendered_user
    assert '"id": "K1"' in rendered_user
    assert '"id": "A1"' in rendered_user
