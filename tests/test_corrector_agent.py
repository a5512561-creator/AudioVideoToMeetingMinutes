from unittest.mock import MagicMock, patch
from script.schemas import CorrectionResult, CorrectionDiff
from script.agents.corrector_agent import CorrectorAgent


def _make_agent():
    with patch("script.agents.corrector_agent.LLMAgent.__init__", return_value=None):
        a = CorrectorAgent.__new__(CorrectorAgent)
        a.render = MagicMock(side_effect=lambda tpl, **ctx: f"R({tpl})")
        a.call = MagicMock()
        return a


def test_correct_returns_llm_result():
    a = _make_agent()
    expect = CorrectionResult(
        corrected_text="x",
        diffs=[CorrectionDiff(original="a", corrected="b", matched_term="b", timestamp="00:00:01")],
    )
    a.call.return_value = expect
    out = a.correct(chunk_text="raw", glossary="g")
    assert out is expect
    sys_kwargs = a.render.call_args_list[0].kwargs
    assert sys_kwargs.get("glossary") == "g"
