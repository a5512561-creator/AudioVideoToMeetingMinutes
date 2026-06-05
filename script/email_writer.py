"""Company-format meeting-minutes email HTML (paste-into-Outlook safe).

Renders a FinalizedMinutes (user-confirmed content) into semantic HTML with
inline styles and tables — no JS, no CSS classes — matching the company
"會議記錄" email layout. Also converts a raw SynthesizedMinutes into an
initial FinalizedMinutes (decisions folded into the summary cell), used both
as the Q&A starting point and for the process-stage preview email.
"""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from script.schemas import (
    SynthesizedMinutes, MeetingMeta,
    FinalizedMinutes, FinalTopic, FinalAction,
)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def synth_to_finalized(
    synth: SynthesizedMinutes, *, subject: str, meta: MeetingMeta
) -> FinalizedMinutes:
    """Build an initial FinalizedMinutes from raw synthesis output.

    Decisions are folded into the topic summary (company format has no
    separate decision column). Action priority is dropped; note starts empty.
    """
    topics = []
    for t in synth.topics:
        summary = t.summary
        if t.decisions:
            summary = f"{summary}（決議：{'；'.join(t.decisions)}）"
        topics.append(FinalTopic(item=t.title, summary=summary))
    actions = [
        FinalAction(task=a.task, owner=a.owner, due=a.due, note="")
        for a in synth.action_items
    ]
    return FinalizedMinutes(meta=meta, subject=subject,
                            topics=topics, actions=actions)


def render_email_html(final: FinalizedMinutes) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
        keep_trailing_newline=False,
    )
    return env.get_template("minutes_email.html.j2").render(f=final, m=final.meta)


def write_email_html(final: FinalizedMinutes, dst: str) -> None:
    html = render_email_html(final)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_text(html, encoding="utf-8")
