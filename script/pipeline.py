import dataclasses
import json
import shutil
from pathlib import Path
from openai import OpenAI

from script.config import Settings
from script.logger import setup_logger, log_kv
from script.progress import Heartbeat
from script.transcript_loader import load_transcript
from script.chunker import chunk_transcript
from script.markdown_writer import write_review_report_md
from script.html_writer import write_minutes_html
from script.agents.base import probe_instructor_mode, usage_summary, estimate_cost
from script.agents.minutes_agent import MinutesAgent
from script.agents.reviewer_agent import ReviewerAgent
from script.agents.synthesis_agent import SynthesisAgent
from script.email_writer import write_email_html, synth_to_finalized
from script.meeting_meta import infer_meeting_date, duration_hint, empty_meta
from script.audio_assets import (
    find_sibling_audio, output_audio, clip_start, cut_clips, file_to_data_url,
)
from script.transcript_corrector import correct_transcript
from script.agents.corrector_agent import CorrectorAgent
from script.schemas import MeetingMinutes, MeetingMeta, ReviewResult, SynthesizedMinutes
from script import speaker_map as _spk_map


def _chunk_to_dict(c) -> dict:
    """Serialize a Chunk (dataclass) to dict, falling back to __dict__ for non-dataclasses."""
    if dataclasses.is_dataclass(c) and not isinstance(c, type):
        return dataclasses.asdict(c)
    return {"text": c.text, "first_timestamp": c.first_timestamp,
            "last_timestamp": c.last_timestamp, "token_estimate": c.token_estimate}


def _resolve_instructor_mode(client, settings) -> str:
    """Return Instructor's API mode, honouring the OPENAI_INSTRUCTOR_MODE
    override before falling back to the auto-probe.

    Some local-hosted reasoning models accept tool-call requests but emit
    malformed tool_call.arguments (Anthropic XML, markdown-fenced JSON with
    chatty preamble). The auto-probe can't catch that — it only checks
    whether the *request* is accepted. The env override lets users force
    ``JSON`` or ``MD_JSON`` mode when their model needs it.
    """
    override = (settings.openai_instructor_mode or "").strip().upper()
    if override and override != "AUTO":
        return override
    return probe_instructor_mode(client, model=settings.openai_model)


def _cut_audio_clips(out_dir, synth, settings) -> dict[int, str]:
    """Pre-cut one ffmpeg clip per unique ▶ anchor in ``synth``, then encode
    each cut to a ``data:audio/...;base64,...`` URL.

    The returned dict maps ``start_second → data URL``. We inline rather
    than reference external clip files because cloud viewers (OneDrive,
    SharePoint, Outlook web) render the user's HTML inside an iframe whose
    base URL is the viewer's domain, **not** the user's folder. Relative
    ``<audio src="clip_NN.m4a">`` therefore 404s in the viewer even though
    the file sits in the same folder when downloaded locally. data: URLs
    sidestep this entirely — no network fetch happens.

    Returns ``{}`` when no sibling audio was copied, ffmpeg is unavailable,
    or every cut failed.
    """
    audio = output_audio(out_dir)
    if audio is None:
        return {}
    pre = settings.audio_clip_pre_seconds
    starts: list[int] = []
    for t in synth.topics:
        if t.source_timestamps:
            s = clip_start(t.source_timestamps[0], pre)
            if s is not None:
                starts.append(s)
    for a in synth.action_items:
        if a.source_timestamps:
            s = clip_start(a.source_timestamps[0], pre)
            if s is not None:
                starts.append(s)
    cut_map = cut_clips(audio, starts, settings.audio_clip_duration_seconds, out_dir)
    return {s: file_to_data_url(out_dir / name) for s, name in cut_map.items()}


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
    logger = setup_logger("pipeline", log_dir=settings.log_dir,
                          level=settings.log_level, run_label=base_name)
    log_kv(logger, "INFO", "pipeline.start", file=src, name=base_name,
           model=settings.openai_model, rerender_only=rerender_only)

    # Always load speaker_map (empty dict if missing)
    spk_map = _spk_map.load(str(out_dir / "speaker_map.json"))

    if rerender_only:
        minutes_path = inter_dir / "minutes.json"
        review_path = inter_dir / "review.json"
        synth_path = inter_dir / "synthesized.json"
        if not minutes_path.exists() or not review_path.exists() or not synth_path.exists():
            raise RuntimeError(
                "--rerender requires cached intermediate/minutes.json, "
                "intermediate/review.json and intermediate/synthesized.json "
                "from a previous full run."
            )
        minutes = MeetingMinutes.model_validate_json(minutes_path.read_text(encoding="utf-8"))
        review = ReviewResult.model_validate_json(review_path.read_text(encoding="utf-8"))
        synth = SynthesizedMinutes.model_validate_json(synth_path.read_text(encoding="utf-8"))

        clips = _cut_audio_clips(out_dir, synth, settings)
        log_kv(logger, "INFO", "stage.audio_clips", count=len(clips), mode="rerender")

        write_minutes_html(
            synth, review, str(out_dir / "minutes.html"),
            meeting_file=src, meta=synth.meta,
            pre=settings.audio_clip_pre_seconds,
            clips=clips,
        )
        write_review_report_md(
            minutes, review, str(out_dir / "review_report.md"),
            meeting_file=src, diarization_enabled=False,
            speakers_detected=0, speaker_map=spk_map,
        )
        preview = synth_to_finalized(
            synth, subject=base_name, meta=synth.meta or empty_meta()
        )
        write_email_html(preview, str(out_dir / "minutes_email.html"))
        log_kv(logger, "INFO", "pipeline.done", out=str(out_dir), mode="rerender")
        return

    transcript_path = out_dir / "transcript.md"

    # Stage 1: obtain transcript.md from the user-supplied transcript file
    if force or not transcript_path.exists():
        if not Path(src).exists():
            raise RuntimeError(f"transcript file not found: {src}")
        fmt = load_transcript(src, str(transcript_path))
        log_kv(logger, "INFO", "stage.load_transcript",
               output=str(transcript_path), format=fmt)
    else:
        log_kv(logger, "INFO", "stage.transcript.cached", path=str(transcript_path))
    transcript_text = transcript_path.read_text(encoding="utf-8")

    # Stage 2.95: optional proper-noun correction
    if settings.enable_proper_noun_correction:
        client_for_corrector = OpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_api_base
        )
        mode_pre = _resolve_instructor_mode(client_for_corrector, settings)
        corrector = CorrectorAgent(
            prompts_dir="script/prompts", client=client_for_corrector,
            model=settings.openai_model, instructor_mode=mode_pre,
            temperature=settings.llm_temperature,
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
    mode = _resolve_instructor_mode(client, settings)
    log_kv(logger, "INFO", "instructor.mode", mode=mode)

    # Progress heartbeat: estimate total LLM calls = map (1/chunk) + reduce
    # (~N-1 in the tree, ≥1) + review (1) + synthesis (1). Slight over-count
    # keeps the % from sticking at 100% before pipeline.done.
    _n = len(chunks)
    heartbeat = Heartbeat(
        logger,
        calls_done_fn=lambda: len(getattr(client, "_usage_log", [])),
        total_estimate=_n + max(1, _n - 1) + 2,
        interval=settings.progress_interval_secs,
    )
    heartbeat.start()

    minutes_agent = MinutesAgent(
        prompts_dir="script/prompts", client=client,
        model=settings.openai_model, instructor_mode=mode,
        temperature=settings.llm_temperature,
    )
    heartbeat.set_stage("minutes:map")
    usage_before_minutes = len(getattr(client, "_usage_log", []))
    extracts = minutes_agent.map_chunks(chunks, parallel=settings.llm_parallel_map)
    (inter_dir / "map_outputs.json").write_text(
        json.dumps([e.model_dump() for e in extracts], ensure_ascii=False),
        encoding="utf-8",
    )
    heartbeat.set_stage("minutes:reduce")
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
        temperature=settings.llm_temperature,
    )
    heartbeat.set_stage("review")
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

    # Stage 5: synthesis -> paste-safe email HTML
    meta = MeetingMeta(
        meeting_date=infer_meeting_date(name, src),
        duration_hint=duration_hint(transcript_text),
        llm_model=settings.openai_model,
    )
    synth_agent = SynthesisAgent(
        prompts_dir="script/prompts", client=client,
        model=settings.openai_model, instructor_mode=mode,
        temperature=settings.llm_temperature,
    )
    heartbeat.set_stage("synthesis")
    usage_before_synth = len(getattr(client, "_usage_log", []))
    # Pass review notes so synthesis can address flagged items rather than
    # copy them verbatim (e.g. ambiguity → expand detail, conflict → reconcile).
    synth = synth_agent.synthesize(minutes, meta, review=review)
    (inter_dir / "synthesized.json").write_text(
        synth.model_dump_json(), encoding="utf-8",
    )
    preview = synth_to_finalized(synth, subject=base_name, meta=meta)
    write_email_html(preview, str(out_dir / "minutes_email.html"))
    synth_usage = usage_summary(getattr(client, "_usage_log", [])[usage_before_synth:])
    log_kv(logger, "INFO", "stage.synthesis",
           topics=len(synth.topics), actions=len(synth.action_items),
           calls=synth_usage["calls"],
           tokens_in=synth_usage["prompt_tokens"],
           tokens_out=synth_usage["completion_tokens"])
    heartbeat.stop()  # LLM stages done; remaining work (audio, render) is fast

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

    # Copy sibling audio (same folder + stem as src) for minutes.html ▶
    _audio = find_sibling_audio(src)
    if _audio is not None:
        try:
            _audio_dst = out_dir / ("audio" + _audio.suffix.lower())
            shutil.copyfile(str(_audio), str(_audio_dst))
            log_kv(logger, "INFO", "stage.audio_asset", copied=str(_audio_dst))
        except OSError as e:
            log_kv(logger, "WARNING", "stage.audio_asset", error=str(e))
    else:
        log_kv(logger, "INFO", "stage.audio_asset", status="missing")

    clips = _cut_audio_clips(out_dir, synth, settings)
    log_kv(logger, "INFO", "stage.audio_clips", count=len(clips))

    # Outputs
    write_minutes_html(
        synth, review, str(out_dir / "minutes.html"),
        meeting_file=src, meta=meta,
        pre=settings.audio_clip_pre_seconds,
        clips=clips,
    )
    write_review_report_md(
        minutes, review, str(out_dir / "review_report.md"),
        meeting_file=src,
        diarization_enabled=False,
        speakers_detected=0,
        speaker_map=spk_map,
    )
    log_kv(logger, "INFO", "pipeline.done", out=str(out_dir))
