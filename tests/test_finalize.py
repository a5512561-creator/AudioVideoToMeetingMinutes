import json
from unittest.mock import patch
from script.schemas import (
    SynthesizedMinutes, SynthTopic, SynthAction, MeetingMeta,
    FinalizedMinutes, FinalTopic, FinalAction,
)
from script.finalize import run_finalize


def _write_synth(out_dir):
    inter = out_dir / "intermediate"
    inter.mkdir(parents=True)
    synth = SynthesizedMinutes(
        meta=MeetingMeta(meeting_date="2026/06/04", duration_hint="約 2h"),
        topics=[SynthTopic(title="主題A", summary="摘要A", decisions=["決議A"])],
        action_items=[SynthAction(task="做X", owner="猜", due="未知", priority="high")],
    )
    (inter / "synthesized.json").write_text(synth.model_dump_json(), encoding="utf-8")


def _confirmed():
    return FinalizedMinutes(
        meta=MeetingMeta(meeting_date="2026/06/04", duration_hint="約 2h",
                         recorder="林冠名"),
        subject="會議記錄: t",
        topics=[FinalTopic(item="主題A", summary="摘要A（決議：決議A）")],
        actions=[FinalAction(task="做X", owner="Alice", due="6/E", note="")],
    )


def test_finalize_writes_json_html_and_opens_draft(tmp_path):
    out_dir = tmp_path / "out" / "t"
    _write_synth(out_dir)
    with patch("script.finalize.run_qna", return_value=_confirmed()) as qna, \
         patch("script.finalize.open_draft", return_value=True) as draft:
        run_finalize(str(out_dir), default_subject="t")
    initial = qna.call_args.args[0]
    assert isinstance(initial, FinalizedMinutes)
    assert "決議" in initial.topics[0].summary
    assert initial.subject == "t"
    assert (out_dir / "finalized.json").exists()
    assert (out_dir / "minutes_email.html").exists()
    subject_arg, html_arg = draft.call_args.args
    assert subject_arg == "會議記錄: t"
    assert "林冠名" in html_arg and "6/E" in html_arg
    saved = FinalizedMinutes.model_validate_json(
        (out_dir / "finalized.json").read_text(encoding="utf-8"))
    assert saved.actions[0].owner == "Alice"


def test_finalize_missing_synth_raises(tmp_path):
    out_dir = tmp_path / "out" / "missing"
    out_dir.mkdir(parents=True)
    try:
        run_finalize(str(out_dir), default_subject="x")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "process" in str(e)


def test_finalize_reuse_loads_previous_as_defaults(tmp_path):
    out_dir = tmp_path / "out" / "t"
    _write_synth(out_dir)
    prev = _confirmed()
    prev.meta.location = "R531"
    (out_dir / "finalized.json").write_text(prev.model_dump_json(), encoding="utf-8")
    with patch("script.finalize.run_qna", return_value=_confirmed()) as qna, \
         patch("script.finalize.open_draft", return_value=True):
        run_finalize(str(out_dir), default_subject="t", reuse=True)
    initial = qna.call_args.args[0]
    assert initial.meta.location == "R531"
