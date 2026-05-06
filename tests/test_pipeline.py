import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from script.config import Settings
from script.transcribe import Segment
from script.diarize import SpeakerSegment, TranscribedSegment
from script.schemas import (
    Conclusion, Action, ChunkExtract, MeetingMinutes, ReviewResult, ReviewNote,
)
from script.pipeline import run_pipeline


def _settings(tmp_path, **over):
    base = dict(
        OPENAI_API_KEY="sk-x", OPENAI_API_BASE="https://x/v1", OPENAI_MODEL="m",
        OUT_DIR=str(tmp_path / "out"), LOG_DIR=str(tmp_path / "log"),
    )
    base.update(over)
    return Settings(**base)


def _conc(): return Conclusion(text="c", is_inferred=False, source_quote="q",
                                source_timestamp="00:00:01", source_speaker=None)
def _act(): return Action(task="t", owner="o", due="d", priority="medium",
                          source_quote="q", source_timestamp="00:00:02",
                          source_speaker=None, rationale="r", is_inferred=False,
                          owner_inferred=False, due_inferred=False, priority_inferred=True)


@patch("script.pipeline.write_minutes_xlsx")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_transcript_md")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.transcribe")
@patch("script.pipeline.extract_audio")
def test_pipeline_runs_all_stages_diarization_off(
    extract, transcribe_m, chunk_m, MAm, RAm,
    write_t, write_r, write_x, tmp_path,
):
    settings = _settings(tmp_path)
    transcribe_m.return_value = [Segment(0.0, 1.0, "hi")]
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

    run_pipeline("in.mp4", settings=settings, name="t")

    extract.assert_called_once()
    transcribe_m.assert_called_once()
    write_t.assert_called_once()
    write_x.assert_called_once()
    write_r.assert_called_once()


@patch("script.pipeline.write_minutes_xlsx")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_transcript_md")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.diarize")
@patch("script.pipeline.assign_speakers")
@patch("script.pipeline.transcribe")
@patch("script.pipeline.extract_audio")
def test_pipeline_invokes_diarize_when_enabled(
    extract, transcribe_m, assign_m, diarize_m, chunk_m, MAm, RAm,
    write_t, write_r, write_x, tmp_path,
):
    settings = _settings(tmp_path, ENABLE_DIARIZATION="true", HF_TOKEN="hf_x")
    transcribe_m.return_value = [Segment(0.0, 1.0, "hi")]
    diarize_m.return_value = [SpeakerSegment(0.0, 1.0, "SPEAKER_1")]
    assign_m.return_value = [TranscribedSegment(0.0, 1.0, "hi", "SPEAKER_1")]
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

    run_pipeline("in.mp4", settings=settings, name="t")

    diarize_m.assert_called_once()
    assign_m.assert_called_once()


@patch("script.pipeline.write_minutes_xlsx")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_transcript_md")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.transcribe")
@patch("script.pipeline.extract_audio")
def test_pipeline_skips_transcribe_when_cache_exists(
    extract, transcribe_m, chunk_m, MAm, RAm,
    write_t, write_r, write_x, tmp_path,
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

    run_pipeline("in.mp4", settings=settings, name="t", force=False)

    extract.assert_not_called()
    transcribe_m.assert_not_called()
    write_t.assert_not_called()


@patch("script.pipeline.write_minutes_xlsx")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_transcript_md")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.transcribe")
@patch("script.pipeline.extract_audio")
@patch("script.pipeline.correct_transcript")
@patch("script.pipeline.CorrectorAgent")
def test_pipeline_invokes_corrector_when_enabled(
    CAm, correct_m, extract, transcribe_m, chunk_m, MAm, RAm,
    write_t, write_r, write_x, tmp_path,
):
    settings = _settings(tmp_path, ENABLE_PROPER_NOUN_CORRECTION="true")
    transcribe_m.return_value = [Segment(0.0, 1.0, "hi")]
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

    run_pipeline("in.mp4", settings=settings, name="t")

    correct_m.assert_called_once()
    CAm.assert_called_once()
