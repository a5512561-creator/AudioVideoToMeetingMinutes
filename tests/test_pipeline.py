import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from script.config import Settings
from script.schemas import (
    Conclusion, Action, ChunkExtract, MeetingMinutes, ReviewResult, ReviewNote,
    SynthesizedMinutes, SynthTopic,
)
from script.pipeline import run_pipeline


def _settings(tmp_path, **over):
    base = dict(
        OPENAI_API_KEY="sk-x", OPENAI_API_BASE="https://x/v1", OPENAI_MODEL="m",
        OUT_DIR=str(tmp_path / "out"), LOG_DIR=str(tmp_path / "log"),
        ENABLE_PROPER_NOUN_CORRECTION="false",
    )
    base.update(over)
    return Settings(**base)


def _conc(): return Conclusion(text="c", is_inferred=False, source_quote="q",
                                source_timestamp="00:00:01", source_speaker=None)
def _act(): return Action(task="t", owner="o", due="d", priority="medium",
                          source_quote="q", source_timestamp="00:00:02",
                          source_speaker=None, rationale="r", is_inferred=False,
                          owner_inferred=False, due_inferred=False, priority_inferred=True)


def _src(tmp_path):
    p = tmp_path / "transcript_in.txt"
    p.write_text("00:00\n大家好\n", encoding="utf-8")
    return str(p)


@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.load_transcript")
@patch("script.pipeline.SynthesisAgent")
@patch("script.pipeline.write_email_html")
def test_pipeline_runs_from_transcript(
    write_email, SAm, load_m, chunk_m, MAm, RAm, write_r, write_x, tmp_path,
):
    settings = _settings(tmp_path)
    out_dir = Path(settings.out_dir) / "t"

    def _fake_load(src, dst):
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_text("[00:00:00] 大家好\n", encoding="utf-8")
    load_m.side_effect = _fake_load

    chunk_m.return_value = [MagicMock(text="x", first_timestamp="00:00:00",
                                       last_timestamp="00:00:01", token_estimate=5)]
    MAm.return_value.map_chunks.return_value = [
        ChunkExtract(topics=[], conclusions=[_conc()], actions=[_act()])
    ]
    MAm.return_value.reduce.return_value = MeetingMinutes(
        conclusions=[_conc()], actions=[_act()],
    )
    RAm.return_value.review.return_value = ReviewResult(notes=[
        ReviewNote(target_section="conclusion", target_id="C1",
                   category="ok", severity="info", note="", suggestion=""),
        ReviewNote(target_section="action", target_id="A1",
                   category="ok", severity="info", note="", suggestion=""),
    ])
    SAm.return_value.synthesize.return_value = SynthesizedMinutes(
        topics=[SynthTopic(title="t", summary="s")]
    )

    run_pipeline(_src(tmp_path), settings=settings, name="t")

    load_m.assert_called_once()
    write_x.assert_called_once()
    write_r.assert_called_once()


@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.load_transcript")
@patch("script.pipeline.SynthesisAgent")
@patch("script.pipeline.write_email_html")
def test_pipeline_uses_cached_transcript(
    write_email, SAm, load_m, chunk_m, MAm, RAm, write_r, write_x, tmp_path,
):
    settings = _settings(tmp_path)
    out_dir = Path(settings.out_dir) / "t"
    out_dir.mkdir(parents=True)
    (out_dir / "transcript.md").write_text("[00:00:00] cached\n", encoding="utf-8")

    chunk_m.return_value = [MagicMock(text="x", first_timestamp="00:00:00",
                                       last_timestamp="00:00:01", token_estimate=5)]
    MAm.return_value.map_chunks.return_value = [
        ChunkExtract(topics=[], conclusions=[_conc()], actions=[])
    ]
    MAm.return_value.reduce.return_value = MeetingMinutes(conclusions=[_conc()], actions=[])
    RAm.return_value.review.return_value = ReviewResult(notes=[
        ReviewNote(target_section="conclusion", target_id="C1",
                   category="ok", severity="info", note="", suggestion=""),
    ])
    SAm.return_value.synthesize.return_value = SynthesizedMinutes(
        topics=[SynthTopic(title="t", summary="s")]
    )

    run_pipeline(_src(tmp_path), settings=settings, name="t", force=False)

    load_m.assert_not_called()


@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.load_transcript")
@patch("script.pipeline.correct_transcript")
@patch("script.pipeline.CorrectorAgent")
@patch("script.pipeline.SynthesisAgent")
@patch("script.pipeline.write_email_html")
def test_pipeline_invokes_corrector_when_enabled(
    write_email, SAm, CAm, correct_m, load_m, chunk_m, MAm, RAm, write_r, write_x, tmp_path,
):
    settings = _settings(tmp_path, ENABLE_PROPER_NOUN_CORRECTION="true")

    def _fake_load(src, dst):
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_text("[00:00:00] 大家好\n", encoding="utf-8")
    load_m.side_effect = _fake_load

    chunk_m.return_value = [MagicMock(text="x", first_timestamp="00:00:00",
                                       last_timestamp="00:00:01", token_estimate=5)]
    MAm.return_value.map_chunks.return_value = [
        ChunkExtract(topics=[], conclusions=[_conc()], actions=[])
    ]
    MAm.return_value.reduce.return_value = MeetingMinutes(conclusions=[_conc()], actions=[])
    RAm.return_value.review.return_value = ReviewResult(notes=[
        ReviewNote(target_section="conclusion", target_id="C1",
                   category="ok", severity="info", note="", suggestion=""),
    ])
    SAm.return_value.synthesize.return_value = SynthesizedMinutes(
        topics=[SynthTopic(title="t", summary="s")]
    )

    run_pipeline(_src(tmp_path), settings=settings, name="t")

    correct_m.assert_called_once()
    CAm.assert_called_once()


@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_email_html")
def test_rerender_uses_all_three_caches(write_email, write_r, write_x, tmp_path):
    from script.schemas import SynthesizedMinutes, SynthTopic
    settings = _settings(tmp_path)
    out_dir = Path(settings.out_dir) / "t"
    inter = out_dir / "intermediate"
    inter.mkdir(parents=True)
    (inter / "minutes.json").write_text(
        MeetingMinutes(conclusions=[_conc()], actions=[_act()]).model_dump_json(),
        encoding="utf-8")
    (inter / "review.json").write_text(
        ReviewResult(notes=[]).model_dump_json(), encoding="utf-8")
    (inter / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="t", summary="s")]
                           ).model_dump_json(), encoding="utf-8")

    run_pipeline(_src(tmp_path), settings=settings, name="t", rerender_only=True)

    write_x.assert_called_once()
    write_r.assert_called_once()
    write_email.assert_called_once()
    from script.schemas import SynthesizedMinutes as _SM
    assert isinstance(write_x.call_args.args[0], _SM)


def test_pipeline_rerender_only_raises_without_cache(tmp_path):
    settings = _settings(tmp_path)
    with pytest.raises(RuntimeError, match="cached"):
        run_pipeline(_src(tmp_path), settings=settings, name="missing", rerender_only=True)


@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_email_html")
@patch("script.pipeline.SynthesisAgent")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.load_transcript")
def test_pipeline_runs_synthesis_stage_and_keeps_existing_outputs(
    load_m, chunk_m, MAm, RAm, SAm, write_email, write_r, write_x, tmp_path,
):
    settings = _settings(tmp_path)

    def _fake_load(src, dst):
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_text("[00:00:00] 大家好\n[01:00:00] 結束\n", encoding="utf-8")
    load_m.side_effect = _fake_load

    chunk_m.return_value = [MagicMock(text="x", first_timestamp="00:00:00",
                                       last_timestamp="00:00:01", token_estimate=5)]
    MAm.return_value.map_chunks.return_value = [
        ChunkExtract(topics=[], conclusions=[_conc()], actions=[_act()])
    ]
    MAm.return_value.reduce.return_value = MeetingMinutes(
        conclusions=[_conc()], actions=[_act()],
    )
    RAm.return_value.review.return_value = ReviewResult(notes=[
        ReviewNote(target_section="conclusion", target_id="C1",
                   category="ok", severity="info", note="", suggestion=""),
        ReviewNote(target_section="action", target_id="A1",
                   category="ok", severity="info", note="", suggestion=""),
    ])
    SAm.return_value.synthesize.return_value = SynthesizedMinutes(
        topics=[SynthTopic(title="t", summary="s", decisions=["d"])],
    )

    run_pipeline(_src(tmp_path), settings=settings, name="20260518_x")

    SAm.return_value.synthesize.assert_called_once()
    sm_arg, meta_arg = SAm.return_value.synthesize.call_args.args
    assert isinstance(sm_arg, MeetingMinutes)
    assert meta_arg.meeting_date == "2026/05/18"
    assert "逐字稿長度約 1h" in meta_arg.duration_hint
    write_email.assert_called_once()
    write_x.assert_called_once()
    write_r.assert_called_once()
    assert (Path(settings.out_dir) / "20260518_x" / "intermediate"
            / "synthesized.json").exists()


def test_rerender_raises_when_synthesized_missing(tmp_path):
    settings = _settings(tmp_path)
    out_dir = Path(settings.out_dir) / "t"
    inter = out_dir / "intermediate"
    inter.mkdir(parents=True)
    (inter / "minutes.json").write_text(
        MeetingMinutes(conclusions=[_conc()], actions=[_act()]).model_dump_json(),
        encoding="utf-8")
    (inter / "review.json").write_text(
        ReviewResult(notes=[]).model_dump_json(), encoding="utf-8")
    with pytest.raises(RuntimeError, match="synthesized.json"):
        run_pipeline(_src(tmp_path), settings=settings, name="t", rerender_only=True)
