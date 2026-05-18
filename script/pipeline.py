import dataclasses
import json
from pathlib import Path
from openai import OpenAI

from script.config import Settings
from script.logger import setup_logger, log_kv
from script.transcript_loader import load_transcript
from script.chunker import chunk_transcript
from script.markdown_writer import write_review_report_md
from script.html_writer import write_minutes_html
from script.agents.base import probe_instructor_mode, usage_summary, estimate_cost
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
        minutes_path = inter_dir / "minutes.json"
        review_path = inter_dir / "review.json"
        if not minutes_path.exists() or not review_path.exists():
            raise RuntimeError(
                "--rerender requires cached intermediate/minutes.json and "
                "intermediate/review.json from a previous full run."
            )
        minutes = MeetingMinutes.model_validate_json(minutes_path.read_text(encoding="utf-8"))
        review = ReviewResult.model_validate_json(review_path.read_text(encoding="utf-8"))

        write_minutes_html(
            minutes, review, str(out_dir / "minutes.html"),
            meeting_file=src,
            diarization_enabled=False,
            speakers_detected=0,
            speaker_map=spk_map,
        )
        write_review_report_md(
            minutes, review, str(out_dir / "review_report.md"),
            meeting_file=src, diarization_enabled=False,
            speakers_detected=0, speaker_map=spk_map,
        )
        log_kv(logger, "INFO", "pipeline.done", out=str(out_dir), mode="rerender")
        return

    transcript_path = out_dir / "transcript.md"

    # Stage 1: obtain transcript.md from the user-supplied transcript file
    if force or not transcript_path.exists():
        if not Path(src).exists():
            raise RuntimeError(f"transcript file not found: {src}")
        load_transcript(src, str(transcript_path))
        log_kv(logger, "INFO", "stage.load_transcript", output=str(transcript_path))
    else:
        log_kv(logger, "INFO", "stage.transcript.cached", path=str(transcript_path))
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
    usage_before_minutes = len(getattr(client, "_usage_log", []))
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
    minutes_usage = usage_summary(getattr(client, "_usage_log", [])[usage_before_minutes:])
    log_kv(logger, "INFO", "stage.minutes",
           conclusions=len(minutes.conclusions), actions=len(minutes.actions),
           calls=minutes_usage["calls"],
           tokens_in=minutes_usage["prompt_tokens"],
           tokens_out=minutes_usage["completion_tokens"])

    # Stage 4: Review
    reviewer = ReviewerAgent(
        prompts_dir="script/prompts", client=client,
        model=settings.openai_model, instructor_mode=mode,
    )
    usage_before_review = len(getattr(client, "_usage_log", []))
    review = reviewer.review(minutes)
    (inter_dir / "review.json").write_text(
        review.model_dump_json(), encoding="utf-8",
    )
    warns = sum(1 for n in review.notes if n.severity == "warn")
    errors = sum(1 for n in review.notes if n.severity == "error")
    review_usage = usage_summary(getattr(client, "_usage_log", [])[usage_before_review:])
    log_kv(logger, "INFO", "stage.review",
           items=len(review.notes), warns=warns, errors=errors,
           calls=review_usage["calls"],
           tokens_in=review_usage["prompt_tokens"],
           tokens_out=review_usage["completion_tokens"])

    # Aggregate token usage + optional cost summary
    total = usage_summary(getattr(client, "_usage_log", []))
    cost = estimate_cost(
        total["prompt_tokens"], total["completion_tokens"],
        price_per_1m_input=settings.llm_price_per_1m_input,
        price_per_1m_output=settings.llm_price_per_1m_output,
    )
    log_kv(logger, "INFO", "pipeline.tokens",
           calls=total["calls"],
           tokens_in=total["prompt_tokens"],
           tokens_out=total["completion_tokens"],
           cost=f"{cost:.4f}", currency=settings.llm_currency)

    # Outputs
    write_minutes_html(
        minutes, review, str(out_dir / "minutes.html"),
        meeting_file=src,
        diarization_enabled=False,
        speakers_detected=0,
        speaker_map=spk_map,
    )
    write_review_report_md(
        minutes, review, str(out_dir / "review_report.md"),
        meeting_file=src,
        diarization_enabled=False,
        speakers_detected=0,
        speaker_map=spk_map,
    )
    log_kv(logger, "INFO", "pipeline.done", out=str(out_dir))
