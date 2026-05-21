from unittest.mock import MagicMock, patch
from script.schemas import (
    Conclusion, Action, MeetingMinutes, MeetingMeta,
    ReviewNote, ReviewResult,
    SynthesizedMinutes, SynthTopic, SynthAction,
)
from script.agents.synthesis_agent import SynthesisAgent


def _conc():
    return Conclusion(text="KPI 不納入考核", is_inferred=False, source_quote="q",
                       source_timestamp="00:05:50", source_speaker=None)


def _act():
    return Action(task="試算 KTR", owner="未明", due="兩週後", priority="high",
                  source_quote="q", source_timestamp="00:01:27", source_speaker=None,
                  rationale="r", is_inferred=False, owner_inferred=True,
                  due_inferred=False, priority_inferred=True)


def _make_agent():
    with patch("script.agents.synthesis_agent.LLMAgent.__init__", return_value=None):
        a = SynthesisAgent.__new__(SynthesisAgent)
        a.render = MagicMock(side_effect=lambda tpl, **ctx: f"R({tpl})")
        a.call = MagicMock()
        return a


def test_synthesize_passes_minutes_json_and_injects_meta():
    a = _make_agent()
    llm_out = SynthesizedMinutes(
        topics=[SynthTopic(title="KPI", summary="s", decisions=["d"],
                            source_timestamps=["00:05:50"])],
        action_items=[SynthAction(task="試算 KTR", owner="未明", due="兩週後",
                                   priority="high", source_timestamps=["00:01:27"])],
    )
    assert llm_out.meta is None
    a.call.return_value = llm_out
    minutes = MeetingMinutes(conclusions=[_conc()], actions=[_act()])
    meta = MeetingMeta(meeting_date="2026/05/18", duration_hint="逐字稿長度約 1h 55m")

    out = a.synthesize(minutes, meta)

    assert out is llm_out
    assert out.meta == meta  # pipeline-owned meta injected post-call
    user_ctx = a.render.call_args_list[1].kwargs
    assert "KPI 不納入考核" in user_ctx["minutes_json"]
    assert a.call.call_args.kwargs["response_model"] is SynthesizedMinutes


def test_synthesize_embeds_ids_in_minutes_payload():
    """Synthesis input must carry C1/A1/K1 IDs so review.notes target_id
    actually resolves to a recognisable item in the prompt."""
    a = _make_agent()
    a.call.return_value = SynthesizedMinutes(topics=[], action_items=[])
    minutes = MeetingMinutes(conclusions=[_conc(), _conc()], actions=[_act()])
    meta = MeetingMeta(meeting_date="d", duration_hint="h")

    a.synthesize(minutes, meta)

    payload = a.render.call_args_list[1].kwargs["minutes_json"]
    assert '"id": "C1"' in payload
    assert '"id": "C2"' in payload
    assert '"id": "A1"' in payload


def test_synthesize_forwards_only_warn_and_error_notes():
    """review_warns must include warn + error notes but drop info-level OK."""
    a = _make_agent()
    a.call.return_value = SynthesizedMinutes(topics=[], action_items=[])
    minutes = MeetingMinutes(conclusions=[_conc()], actions=[_act()])
    meta = MeetingMeta(meeting_date="d", duration_hint="h")
    review = ReviewResult(notes=[
        ReviewNote(target_section="conclusion", target_id="C1",
                   category="ok", severity="info", note="", suggestion=""),
        ReviewNote(target_section="action", target_id="A1",
                   category="ambiguity", severity="warn",
                   note="缺乏交付物", suggestion="補上輸出形式"),
        ReviewNote(target_section="conclusion", target_id="C1",
                   category="conflict", severity="error",
                   note="與其他結論矛盾", suggestion="重審"),
    ])

    a.synthesize(minutes, meta, review=review)

    warns = a.render.call_args_list[1].kwargs["review_warns"]
    assert len(warns) == 2  # info dropped, warn+error kept
    severities = {w["severity"] for w in warns}
    assert severities == {"warn", "error"}
    target_ids = {w["target_id"] for w in warns}
    assert target_ids == {"A1", "C1"}


def test_synthesize_passes_empty_review_warns_when_no_review():
    """Backward compatible: review=None → review_warns is []."""
    a = _make_agent()
    a.call.return_value = SynthesizedMinutes(topics=[], action_items=[])
    minutes = MeetingMinutes(conclusions=[_conc()], actions=[_act()])
    meta = MeetingMeta(meeting_date="d", duration_hint="h")

    a.synthesize(minutes, meta)  # no review kwarg

    warns = a.render.call_args_list[1].kwargs["review_warns"]
    assert warns == []
