from unittest.mock import MagicMock, patch
from script.schemas import (
    Conclusion, Action, MeetingMinutes, MeetingMeta,
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
