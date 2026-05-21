"""Interactive self-contained HTML for synthesized meeting minutes.

Renders SynthesizedMinutes (topic-grouped decisions + consolidated
actions) with tab navigation, full-text search and an action priority
filter. The Review tab surfaces the reviewer's warn/error notes from the
detailed extraction pass; those reference the RAW extracted items, not the
synthesized topics, so the tab carries an on-page disclaimer.

When the caller passes per-anchor audio clips (``clips`` kwarg, populated
by ``pipeline._cut_audio_clips``), each decision/action gets a ▶ that
plays an inline ``data:audio/...;base64,...`` URL. Inlining the audio (vs
referencing external files) is necessary because cloud viewers (OneDrive,
SharePoint, Outlook web) render the HTML inside an iframe whose base URL
is the viewer domain — relative ``<audio src="clip_NN.m4a">`` URLs cannot
reach the user's folder from there. data: URLs make the HTML truly
single-file portable.
"""
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from script.schemas import SynthesizedMinutes, ReviewResult, MeetingMeta
from script.meeting_meta import empty_meta
from script.audio_assets import clip_start

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_SECTION_LABEL = {"conclusion": "結論", "key_point": "重點", "action": "Action"}
_SEV_ICON = {"info": "✅", "warn": "⚠️", "error": "❌"}


def _clip_key_for(timestamps, pre: int, clips: dict[int, str]):
    """Return the start-second as a string key if its anchor has a clip; None otherwise.

    The buttons hold this short key (e.g. ``"345"``); the actual data URL
    lives in a single JS ``CLIPS`` dict in the page so each unique clip
    appears exactly once even when many decisions share the same anchor.
    """
    if not timestamps or not clips:
        return None
    s = clip_start(timestamps[0], pre)
    if s is None or s not in clips:
        return None
    return str(s)


def write_minutes_html(
    synth: SynthesizedMinutes,
    review: ReviewResult,
    dst: str,
    *,
    meeting_file: str,
    meta: MeetingMeta | None = None,
    pre: int = 5,
    clips: dict[int, str] | None = None,
) -> None:
    """Render the interactive synthesized-minutes HTML.

    meta resolution order: explicit `meta` arg -> `synth.meta` -> empty_meta().
    Audio ▶ buttons render when `clips` maps the per-item anchor second to
    a ``data:audio/...;base64,...`` URL produced by pipeline.
    """
    out_dir = Path(dst).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    m = meta or synth.meta or empty_meta()

    clips = clips or {}
    has_audio = bool(clips)
    clips_js = json.dumps({str(k): v for k, v in clips.items()}, ensure_ascii=True)

    topics = [
        {
            "idx": i,
            "title": t.title,
            "summary": t.summary,
            "decisions": list(t.decisions),
            "clip": _clip_key_for(t.source_timestamps, pre, clips),
        }
        for i, t in enumerate(synth.topics, start=1)
    ]
    actions = [
        {
            "idx": i,
            "task": a.task,
            "owner": a.owner,
            "due": a.due,
            "priority": a.priority,
            # `context` (前因) — added in v9, missing on older cached
            # SynthesizedMinutes JSON (loaded via Pydantic default "")
            "context": getattr(a, "context", "") or "",
            "clip": _clip_key_for(a.source_timestamps, pre, clips),
        }
        for i, a in enumerate(synth.action_items, start=1)
    ]
    review_rows = [
        {
            "id": n.target_id,
            "section": _SECTION_LABEL.get(n.target_section, n.target_section),
            "category": n.category,
            "severity": n.severity,
            "icon": _SEV_ICON.get(n.severity, ""),
            "note": n.note or "",
            "suggestion": n.suggestion or "",
        }
        for n in review.notes
        if n.severity in ("warn", "error")
    ]
    n_decisions = sum(len(t["decisions"]) for t in topics)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    html = env.get_template("minutes.html.j2").render(
        meeting_file=Path(meeting_file).name or meeting_file,
        meta=m,
        topics=topics,
        actions=actions,
        review_rows=review_rows,
        n_topics=len(topics),
        n_decisions=n_decisions,
        n_actions=len(actions),
        n_warns=sum(1 for n in review.notes if n.severity == "warn"),
        n_errors=sum(1 for n in review.notes if n.severity == "error"),
        has_audio=has_audio,
        clips_js=clips_js,
    )
    Path(dst).write_text(html, encoding="utf-8")
