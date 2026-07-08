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


def test_unfence_strips_full_markdown_block():
    """Realtek's medium model puts valid JSON inside ```json … ``` markdown
    fences as the tool_call.arguments string. _unfence pulls the JSON out
    so Pydantic's JSON parser doesn't see backticks as line-1 column-1."""
    from script.agents.base import _unfence
    payload = '```json\n{"a": 1, "b": [2, 3]}\n```'
    assert _unfence(payload) == '{"a": 1, "b": [2, 3]}'


def test_unfence_handles_no_lang_tag():
    from script.agents.base import _unfence
    assert _unfence('```\n{"x": 1}\n```') == '{"x": 1}'


def test_unfence_leaves_unfenced_input_alone():
    from script.agents.base import _unfence
    s = '{"a": 1}'
    assert _unfence(s) is s  # exact same object — no allocation needed


def test_unfence_extracts_block_after_preamble():
    """Some reasoning models prepend natural-language commentary before the
    fenced JSON ("OK, here is the consolidated output:\\n\\n```json…```").
    We must extract the JSON regardless of leading text — anchoring at
    start would leave Pydantic to see the Chinese preamble at col 1."""
    from script.agents.base import _unfence
    payload = '好的，整合如下：\n\n```json\n{"conclusions": []}\n```'
    assert _unfence(payload) == '{"conclusions": []}'


def test_unfence_extracts_block_with_trailing_text():
    """Trailing text after the closing fence is also discarded."""
    from script.agents.base import _unfence
    payload = '```json\n{"a": 1}\n```\n\nLet me know if you need anything else.'
    assert _unfence(payload) == '{"a": 1}'


def test_unfence_inline_backticks_in_string_value_not_extracted():
    """Backticks that appear inline in a JSON string value but don't form a
    proper ```\\n…\\n``` block must not be mis-extracted."""
    from script.agents.base import _unfence
    s = '{"code": "use `git status` to check"}'
    assert _unfence(s) == s


def test_unfence_handles_none_and_empty():
    from script.agents.base import _unfence
    assert _unfence(None) is None
    assert _unfence("") == ""


def test_strip_thinking_tokens_unfences_tool_call_arguments():
    """End-to-end: a response whose tool_call.arguments is a markdown-fenced
    JSON gets unwrapped in-place so Instructor's downstream parser sees
    clean JSON. This is the exact failure mode observed with the medium
    model in production."""
    from script.agents.base import _strip_thinking_tokens
    client = MagicMock()
    tc = MagicMock()
    tc.function = MagicMock()
    tc.function.arguments = '```json\n{"topics": ["t1"]}\n```'
    msg = MagicMock()
    msg.content = ""
    msg.tool_calls = [tc]
    choice = MagicMock()
    choice.message = msg
    fake_resp = MagicMock()
    fake_resp.choices = [choice]
    fake_resp.usage = None
    client.chat.completions.create.return_value = fake_resp
    for attr in ("_strip_thinking_installed", "_usage_log"):
        if hasattr(client, attr):
            delattr(client, attr)

    wrapped = _strip_thinking_tokens(client)
    wrapped.chat.completions.create()

    assert tc.function.arguments == '{"topics": ["t1"]}'


def test_repair_json_fixes_duplicated_topics_key():
    """The on-prem `expert` model glues a spurious partial key-string
    containing a `{` between the opening brace and the real first key, e.g.
    `{\\n  "topics{\\n  "topics": [...]`. The stray newline inside that broken
    string is what Pydantic rejects. _repair_json must recover the intended
    object with a clean `topics` key."""
    from script.agents.base import _repair_json
    bad = ('{\n  "topics{\n  "topics": [\n    "CPU arch"\n  ],\n'
           '  "conclusions": [],\n  "actions": [],\n  "key_points": []\n}')
    obj = json.loads(_repair_json(bad))
    assert list(obj.keys()) == ["topics", "conclusions", "actions", "key_points"]
    assert obj["topics"] == ["CPU arch"]


def test_repair_json_fixes_stray_open_brace_variant():
    """Second observed variant: `{\\n  "{\\n  "topics": [...]`."""
    from script.agents.base import _repair_json
    bad = ('{\n  "{\n  "topics": [\n    "x"\n  ],\n'
           '  "conclusions": [],\n  "actions": [],\n  "key_points": []\n}')
    obj = json.loads(_repair_json(bad))
    assert list(obj.keys()) == ["topics", "conclusions", "actions", "key_points"]


def test_repair_json_leaves_valid_json_semantically_unchanged():
    from script.agents.base import _repair_json
    good = '{"topics": ["x"], "conclusions": [], "actions": [], "key_points": []}'
    assert json.loads(_repair_json(good)) == json.loads(good)


def test_repair_json_handles_none_and_empty():
    from script.agents.base import _repair_json
    assert _repair_json(None) is None
    assert _repair_json("") == ""


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
