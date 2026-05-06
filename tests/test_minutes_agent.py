from unittest.mock import MagicMock, patch
from script.chunker import Chunk
from script.schemas import (
    Conclusion,
    Action,
    ChunkExtract,
    MeetingMinutes,
)
from script.agents.minutes_agent import MinutesAgent


def _conc(text="c", **over):
    base = dict(
        text=text, is_inferred=False, source_quote="q",
        source_timestamp="00:00:01", source_speaker=None,
    )
    base.update(over)
    return Conclusion(**base)


def _act(task="t", **over):
    base = dict(
        task=task, owner="o", due="d", priority="medium",
        source_quote="q", source_timestamp="00:00:02", source_speaker=None,
        rationale="r", is_inferred=False, owner_inferred=False,
        due_inferred=False, priority_inferred=True,
    )
    base.update(over)
    return Action(**base)


def _make_agent():
    with patch("script.agents.minutes_agent.LLMAgent.__init__", return_value=None):
        a = MinutesAgent.__new__(MinutesAgent)
        a.render = MagicMock(side_effect=lambda tpl, **ctx: f"R({tpl})")
        a.call = MagicMock()
        return a


def test_map_calls_llm_per_chunk():
    a = _make_agent()
    a.call.side_effect = [
        ChunkExtract(topics=["t1"], conclusions=[_conc("c1")], actions=[]),
        ChunkExtract(topics=["t2"], conclusions=[], actions=[_act("a1")]),
    ]
    chunks = [
        Chunk(text="x", first_timestamp="00:00:00", last_timestamp="00:00:10", token_estimate=10),
        Chunk(text="y", first_timestamp="00:00:11", last_timestamp="00:00:20", token_estimate=10),
    ]
    out = a.map_chunks(chunks, parallel=1)
    assert len(out) == 2
    assert out[0].conclusions[0].text == "c1"
    assert out[1].actions[0].task == "a1"
    assert a.call.call_count == 2


def test_reduce_merges_extracts():
    a = _make_agent()
    merged = MeetingMinutes(conclusions=[_conc("merged_c")], actions=[_act("merged_a")])
    a.call.return_value = merged
    extracts = [
        ChunkExtract(topics=[], conclusions=[_conc("c1")], actions=[]),
        ChunkExtract(topics=[], conclusions=[_conc("c2")], actions=[]),
    ]
    out = a.reduce(extracts, max_input_chars=1_000_000)
    assert out is merged
    assert a.call.call_count == 1


def test_reduce_falls_back_to_tree_when_input_too_big():
    a = _make_agent()
    # First two pairwise reductions, then final merge -> 3 calls
    a.call.side_effect = [
        MeetingMinutes(conclusions=[_conc("p1")], actions=[]),
        MeetingMinutes(conclusions=[_conc("p2")], actions=[]),
        MeetingMinutes(conclusions=[_conc("final")], actions=[]),
    ]
    extracts = [
        ChunkExtract(topics=[], conclusions=[_conc(f"c{i}")], actions=[])
        for i in range(4)
    ]
    out = a.reduce(extracts, max_input_chars=20)  # tiny limit forces tree
    assert out.conclusions[0].text == "final"
    assert a.call.call_count == 3


def test_assign_ids_after_reduce():
    a = _make_agent()
    minutes = MeetingMinutes(
        conclusions=[_conc("c1"), _conc("c2")],
        actions=[_act("a1"), _act("a2"), _act("a3")],
    )
    ided = a.assign_ids(minutes)
    assert ided["C1"].text == "c1"
    assert ided["C2"].text == "c2"
    assert ided["A1"].task == "a1"
    assert ided["A3"].task == "a3"
