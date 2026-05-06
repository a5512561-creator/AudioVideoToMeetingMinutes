import dataclasses
import json
from pathlib import Path
from openai import OpenAI

from script.config import Settings
from script.logger import setup_logger, log_kv
from script.media import extract_audio
from script.transcribe import transcribe, Segment
from script.diarize import diarize, assign_speakers, TranscribedSegment
from script.chunker import chunk_transcript
from script.markdown_writer import write_transcript_md, write_review_report_md
from script.excel_writer import write_minutes_xlsx
from script.agents.base import probe_instructor_mode
from script.agents.minutes_agent import MinutesAgent
from script.agents.reviewer_agent import ReviewerAgent
from script.transcript_corrector import correct_transcript
from script.agents.corrector_agent import CorrectorAgent
from script.schemas import MeetingMinutes, ReviewResult
from script import speaker_map as _spk_map


def _chunk_to_dict(c) -> dict:
    """Serialize a Chunk (dataclass) to dict, falling back to __dict__ for non-dataclasses."""
    if dataclasses.is_dataclass(c) and not isinstance(c, type):
        return dataclasses.asdict(c)
    return {"text": c.text, "first_timestamp": c.first_timestamp,
            "last_timestamp": c.last_timestamp, "token_estimate": c.token_estimate}


def run_pipeline(
    src: str,
    *,
    settings: Settings,
    name: str | None = None,
    force: bool = False,
    skip_transcribe: bool = False,
    diarize_override: bool | None = None,
    rerender_only: bool = False,
) -> None:
    base_name = name or Path(src).stem
    out_dir = Path(settings.out_dir) / base_name
    inter_dir = out_dir / "intermediate"
    out_dir.mkdir(parents=True, exist_ok=True)
    inter_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logger("pipeline", log_dir=settings.log_dir, level=settings.log_level)
    log_kv(logger, "INFO", "pipeline.start", file=src, name=base_name,
           rerender_only=rerender_only)

    # Always load speaker_map (empty dict if missing)
    spk_map = _spk_map.load(str(out_dir / "speaker_map.json"))

    if rerender_only:
        # Read cached minutes + review, re-write outputs only
        minutes_path = inter_dir / "minutes.json"
        review_path = inter_dir / "review.json"
        if not minutes_path.exists() or not review_path.exists():
            raise RuntimeError(
                "--rerender requires cached intermediate/minutes.json and "
                "intermediate/review.json from a previous full run."
            )
        minutes = MeetingMinutes.model_validate_json(minutes_path.read_text(encoding="utf-8"))
        review = ReviewResult.model_validate_json(review_path.read_text(encoding="utf-8"))
        diar_was_used = (out_dir / "speaker_map.json").exists()
        speakers_detected = len({k for k in spk_map}) if diar_was_used else 0

        write_minutes_xlsx(minutes, review, str(out_dir / "minutes.xlsx"), speaker_map=spk_map)
        write_review_report_md(
            minutes, review, str(out_dir / "review_report.md"),
            meeting_file=src, diarization_enabled=diar_was_used,
            speakers_detected=speakers_detected, speaker_map=spk_map,
        )
        log_kv(logger, "INFO", "pipeline.done", out=str(out_dir), mode="rerender")
        return

    audio_path = inter_dir / "audio.wav"
    transcript_path = out_dir / "transcript.md"

    diar_enabled = (
        diarize_override if diarize_override is not None else settings.enable_diarization
    )
    speakers_detected = 0

    # Stage 1+2 (+optional 2.5): produce transcript.md
    if force or not transcript_path.exists():
        if force or not audio_path.exists():
            extract_audio(src, str(audio_path))
            log_kv(logger, "INFO", "stage.media", output=str(audio_path))
        if skip_transcribe and not transcript_path.exists():
            raise RuntimeError("--skip-transcribe used but no cached transcript.md exists")
        segments = transcribe(
            str(audio_path),
            model=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            language=settings.whisper_language,
            initial_prompt=settings.whisper_initial_prompt,
            vad_filter=settings.whisper_vad_filter,
        )
        log_kv(logger, "INFO", "stage.transcribe", segments=len(segments))

        if diar_enabled:
            speaker_segs = diarize(
                str(audio_path),
                model=settings.diarization_model,
                hf_token=settings.hf_token,
            )
            speakers_detected = len({s.label for s in speaker_segs})
            log_kv(logger, "INFO", "stage.diarize", speakers=speakers_detected)
            (inter_dir / "diarization.json").write_text(
                json.dumps([s.__dict__ for s in speaker_segs], ensure_ascii=False),
                encoding="utf-8",
            )
            _spk_map.write_template(
                str(out_dir / "speaker_map.json"),
                [s.label for s in speaker_segs],
            )
            # Reload in case template was just created (identity mapping for full runs)
            spk_map = _spk_map.load(str(out_dir / "speaker_map.json"))
            merged = assign_speakers(segments, speaker_segs)
            write_transcript_md(merged, str(transcript_path))
            transcript_text = transcript_path.read_text(encoding="utf-8") if transcript_path.exists() else ""
        else:
            write_transcript_md(segments, str(transcript_path))
            transcript_text = transcript_path.read_text(encoding="utf-8") if transcript_path.exists() else ""
    else:
        log_kv(logger, "INFO", "stage.transcribe.cached", path=str(transcript_path))
        transcript_text = transcript_path.read_text(encoding="utf-8")

    # Stage 2.95: optional proper-noun correction
    if settings.enable_proper_noun_correction:
        client_for_corrector = OpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_api_base
        )
        mode_pre = probe_instructor_mode(client_for_corrector, model=settings.openai_model)
        corrector = CorrectorAgent(
            prompts_dir="script/prompts", client=client_for_corrector,
            model=settings.openai_model, instructor_mode=mode_pre,
        )
        correct_transcript(
            transcript_path=str(transcript_path),
            glossary_path=settings.glossary_file,
            diff_path=str(inter_dir / "correction_diff.json"),
            raw_backup_path=str(out_dir / "transcript.raw.md"),
            agent=corrector,
            chunk_chars=settings.llm_chunk_tokens,
        )
        log_kv(logger, "INFO", "stage.corrector", enabled=True)

    # Re-read transcript (may have been corrected by Stage 2.95)
    if transcript_path.exists():
        transcript_text = transcript_path.read_text(encoding="utf-8")

    # Stage 3: Minutes
    chunks = chunk_transcript(
        transcript_text,
        max_tokens=settings.llm_chunk_tokens,
        overlap_ratio=settings.llm_chunk_overlap_ratio,
    )
    (inter_dir / "chunks.json").write_text(
        json.dumps([_chunk_to_dict(c) for c in chunks], ensure_ascii=False), encoding="utf-8",
    )
    log_kv(logger, "INFO", "stage.chunk", chunks=len(chunks))

    client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_api_base)
    mode = probe_instructor_mode(client, model=settings.openai_model)
    log_kv(logger, "INFO", "instructor.mode", mode=mode)

    minutes_agent = MinutesAgent(
        prompts_dir="script/prompts", client=client,
        model=settings.openai_model, instructor_mode=mode,
    )
    extracts = minutes_agent.map_chunks(chunks, parallel=settings.llm_parallel_map)
    (inter_dir / "map_outputs.json").write_text(
        json.dumps([e.model_dump() for e in extracts], ensure_ascii=False),
        encoding="utf-8",
    )
    minutes = minutes_agent.reduce(
        extracts, max_input_chars=settings.llm_chunk_tokens * 2,
    )
    (inter_dir / "minutes.json").write_text(
        minutes.model_dump_json(), encoding="utf-8",
    )
    log_kv(logger, "INFO", "stage.minutes",
           conclusions=len(minutes.conclusions), actions=len(minutes.actions))

    # Stage 4: Review
    reviewer = ReviewerAgent(
        prompts_dir="script/prompts", client=client,
        model=settings.openai_model, instructor_mode=mode,
    )
    review = reviewer.review(minutes)
    (inter_dir / "review.json").write_text(
        review.model_dump_json(), encoding="utf-8",
    )
    warns = sum(1 for n in review.notes if n.severity == "warn")
    errors = sum(1 for n in review.notes if n.severity == "error")
    log_kv(logger, "INFO", "stage.review",
           items=len(review.notes), warns=warns, errors=errors)

    # Outputs
    write_minutes_xlsx(minutes, review, str(out_dir / "minutes.xlsx"), speaker_map=spk_map)
    write_review_report_md(
        minutes, review, str(out_dir / "review_report.md"),
        meeting_file=src,
        diarization_enabled=diar_enabled,
        speakers_detected=speakers_detected,
        speaker_map=spk_map,
    )
    log_kv(logger, "INFO", "pipeline.done", out=str(out_dir))
