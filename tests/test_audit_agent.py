from unittest.mock import MagicMock, patch
from script.schemas import (
    SynthesizedMinutes, SynthTopic, SynthAction,
    SemanticAudit, AuditCheckSemantic,
)
from script.agents.audit_agent import AuditAgent


def _make_agent():
    with patch("script.agents.audit_agent.LLMAgent.__init__", return_value=None):
        a = AuditAgent.__new__(AuditAgent)
        a.render = MagicMock(side_effect=lambda tpl, **ctx: f"R({tpl})")
        a.call = MagicMock()
        a._load_checklist = MagicMock(return_value="CHECKLIST-TEXT")
        return a


def _synth():
    return SynthesizedMinutes(
        topics=[SynthTopic(title="KPI", summary="s", decisions=["d"])],
        action_items=[SynthAction(task="t", owner="o", due="d", priority="high")],
    )


def test_audit_passes_checklist_and_synth_json_to_prompt():
    a = _make_agent()
    a.call.return_value = SemanticAudit(checks=[
        AuditCheckSemantic(key="fluency", label="語句通順", score=4, rationale="ok")])

    out = a.audit(_synth())

    assert isinstance(out, list)
    assert out[0].key == "fluency"
    user_ctx = a.render.call_args_list[1].kwargs
    assert user_ctx["checklist"] == "CHECKLIST-TEXT"
    assert "KPI" in user_ctx["synth_json"]
    assert a.call.call_args.kwargs["response_model"] is SemanticAudit


def test_audit_returns_empty_list_when_llm_returns_no_checks():
    a = _make_agent()
    a.call.return_value = SemanticAudit(checks=[])
    assert a.audit(_synth()) == []
