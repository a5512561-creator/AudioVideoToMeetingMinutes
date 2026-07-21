from pathlib import Path

from script.schemas import (
    MeetingMinutes, ReviewResult, SynthesizedMinutes, SynthTopic,
    Conclusion, Action,
)
from script.intermediate_check import validate_intermediate


def _conc():
    return Conclusion(text="c", is_inferred=False, source_quote="q",
                      source_timestamp="00:00:01", source_speaker=None)


def _act():
    return Action(task="t", owner="o", due="d", priority="high",
                  source_quote="q", source_timestamp="00:00:02",
                  source_speaker=None, rationale="r", is_inferred=False,
                  owner_inferred=False, due_inferred=False, priority_inferred=False)


def _write_all_valid(inter: Path):
    inter.mkdir(parents=True, exist_ok=True)
    (inter / "minutes.json").write_text(
        MeetingMinutes(conclusions=[_conc()], actions=[_act()]).model_dump_json(),
        encoding="utf-8")
    (inter / "review.json").write_text(ReviewResult(notes=[]).model_dump_json(),
                                       encoding="utf-8")
    (inter / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="A", summary="s")]).model_dump_json(),
        encoding="utf-8")


def test_all_valid(tmp_path):
    inter = tmp_path / "out" / "t" / "intermediate"
    _write_all_valid(inter)
    r = validate_intermediate(tmp_path / "out" / "t")
    assert r["ok"] is True
    assert all(f["ok"] for f in r["files"].values())


def test_missing_file_reported(tmp_path):
    inter = tmp_path / "out" / "t" / "intermediate"
    _write_all_valid(inter)
    (inter / "synthesized.json").unlink()
    r = validate_intermediate(tmp_path / "out" / "t")
    assert r["ok"] is False
    assert r["files"]["synthesized"]["ok"] is False
    assert "找不到" in r["files"]["synthesized"]["error"]


def test_wrong_shape_reported(tmp_path):
    inter = tmp_path / "out" / "t" / "intermediate"
    _write_all_valid(inter)
    # minutes.json uses wrong field name "items" at top level — engine-B mistake
    # (note: {"conclusions": {"items": []}} is coerced by _UnwrapListFields,
    # but a top-level {"items": [...]} with missing required fields fails)
    (inter / "minutes.json").write_text('{"conclusions": "not-a-list", "actions": []}',
                                         encoding="utf-8")
    r = validate_intermediate(tmp_path / "out" / "t")
    assert r["ok"] is False
    assert r["files"]["minutes"]["ok"] is False
    assert r["files"]["minutes"]["error"]  # a non-empty pydantic message


def test_bad_json_reported(tmp_path):
    inter = tmp_path / "out" / "t" / "intermediate"
    _write_all_valid(inter)
    (inter / "review.json").write_text("{not json", encoding="utf-8")
    r = validate_intermediate(tmp_path / "out" / "t")
    assert r["ok"] is False
    assert r["files"]["review"]["ok"] is False
