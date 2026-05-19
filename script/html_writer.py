"""Interactive self-contained HTML for synthesized meeting minutes.

Renders SynthesizedMinutes (topic-grouped decisions + consolidated
actions) with tab navigation, full-text search and an action priority
filter. The Review tab surfaces the reviewer's warn/error notes from the
detailed extraction pass; those reference the RAW extracted items, not the
synthesized topics, so the tab carries an on-page disclaimer.
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from script.schemas import SynthesizedMinutes, ReviewResult, MeetingMeta
from script.meeting_meta import empty_meta

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_SECTION_LABEL = {"conclusion": "結論", "key_point": "重點", "action": "Action"}
_SEV_ICON = {"info": "✅", "warn": "⚠️", "error": "❌"}


def write_minutes_html(
    synth: SynthesizedMinutes,
    review: ReviewResult,
    dst: str,
    *,
    meeting_file: str,
    meta: MeetingMeta | None = None,
) -> None:
    """Render the interactive synthesized-minutes HTML.

    meta resolution order: explicit `meta` arg -> `synth.meta` -> empty_meta().
    """
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    m = meta or synth.meta or empty_meta()

    topics = [
        {
            "idx": i,
            "title": t.title,
            "summary": t.summary,
            "decisions": list(t.decisions),
            "source_timestamps": list(t.source_timestamps),
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
    )
    Path(dst).write_text(html, encoding="utf-8")
