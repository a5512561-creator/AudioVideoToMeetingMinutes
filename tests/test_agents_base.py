import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from pydantic import BaseModel
from script.agents.base import LLMAgent, probe_instructor_mode, FewShot


class Out(BaseModel):
    msg: str


@pytest.fixture
def prompt_dir(tmp_path):
    """Create a minimal prompts/ tree for tests."""
    p = tmp_path / "prompts"
    (p / "few_shot/test").mkdir(parents=True)
    (p / "background.md").write_text("BG_CONTENT", encoding="utf-8")
    (p / "test_system.j2").write_text("SYS {{ background }}", encoding="utf-8")
    (p / "test_user.j2").write_text(
        "{% for s in few_shots %}EX:{{ s.input }}={{ s.output }}\n{% endfor %}USER {{ payload }}",
        encoding="utf-8",
    )
    (p / "few_shot/test/ex1.json").write_text(
        json.dumps({"input": "i1", "output": "o1", "comment": "c"}),
        encoding="utf-8",
    )
    return p


def test_load_few_shots_excludes_comment(prompt_dir):
    agent = LLMAgent(
        name="test",
        prompts_dir=str(prompt_dir),
        client=MagicMock(),
        model="m",
        instructor_mode="JSON",
    )
    assert len(agent.few_shots) == 1
    assert agent.few_shots[0] == FewShot(input="i1", output="o1")


def test_render_injects_background_and_few_shots(prompt_dir):
    agent = LLMAgent(
        name="test",
        prompts_dir=str(prompt_dir),
        client=MagicMock(),
        model="m",
        instructor_mode="JSON",
    )
    sys_text = agent.render("test_system.j2")
    assert sys_text == "SYS BG_CONTENT"
    user_text = agent.render("test_user.j2", payload="P")
    assert "EX:i1=o1" in user_text
    assert "USER P" in user_text


def test_call_invokes_instructor_with_response_model(prompt_dir):
    raw_client = MagicMock()
    fake_resp = Out(msg="ok")
    with patch("script.agents.base.instructor.from_openai") as ifo:
        patched_client = MagicMock()
        patched_client.chat.completions.create.return_value = fake_resp
        ifo.return_value = patched_client
        agent = LLMAgent(
            name="test",
            prompts_dir=str(prompt_dir),
            client=raw_client,
            model="m",
            instructor_mode="JSON",
        )
        out = agent.call(system="S", user="U", response_model=Out, max_retries=2)

    assert out is fake_resp
    kwargs = patched_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "m"
    assert kwargs["response_model"] is Out
    assert kwargs["max_retries"] == 2
    assert kwargs["messages"] == [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "U"},
    ]


def test_probe_instructor_mode_returns_tools_when_supported():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = MagicMock()  # no exception
    mode = probe_instructor_mode(fake_client, model="m")
    assert mode == "TOOLS"


def test_probe_instructor_mode_falls_back_to_json_on_error():
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = Exception("400 unsupported")
    mode = probe_instructor_mode(fake_client, model="m")
    assert mode == "JSON"


def test_strip_thinking_tokens_records_usage():
    """Token usage on each completion appended to client._usage_log."""
    from script.agents.base import _strip_thinking_tokens
    client = MagicMock()
    # Build a fake response with .usage
    fake_resp = MagicMock()
    fake_resp.choices = []
    fake_resp.usage = MagicMock(prompt_tokens=120, completion_tokens=40, total_tokens=160)
    client.chat.completions.create.return_value = fake_resp
    # Reset attributes set by previous test runs
    if hasattr(client, "_strip_thinking_installed"):
        delattr(client, "_strip_thinking_installed")
    if hasattr(client, "_usage_log"):
        delattr(client, "_usage_log")

    wrapped = _strip_thinking_tokens(client)
    wrapped.chat.completions.create()
    wrapped.chat.completions.create()

    assert len(client._usage_log) == 2
    assert client._usage_log[0] == {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160}


def test_usage_summary_aggregates():
    from script.agents.base import usage_summary
    log = [
        {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
        {"prompt_tokens": 200, "completion_tokens": 50, "total_tokens": 250},
    ]
    s = usage_summary(log)
    assert s == {"calls": 2, "prompt_tokens": 300, "completion_tokens": 80, "total_tokens": 380}


def test_usage_summary_handles_empty():
    from script.agents.base import usage_summary
    assert usage_summary([]) == {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def test_estimate_cost_simple():
    from script.agents.base import estimate_cost
    # GPT-4o pricing: $2.50/M input, $10/M output
    cost = estimate_cost(1_000_000, 100_000,
                         price_per_1m_input=2.50, price_per_1m_output=10.0)
    # 1M * $2.50 + 100K * $10 = $2.50 + $1.00 = $3.50
    assert abs(cost - 3.50) < 1e-9


def test_estimate_cost_zero_when_prices_unset():
    from script.agents.base import estimate_cost
    assert estimate_cost(123_456, 78_910,
                         price_per_1m_input=0.0, price_per_1m_output=0.0) == 0.0
