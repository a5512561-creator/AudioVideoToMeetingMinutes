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
