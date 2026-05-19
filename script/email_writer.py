"""Simple, paste-into-Outlook email HTML for synthesized minutes.

Deliberately minimal: semantic tags + one table + inline styles, no JS,
no CSS classes, no collapsibles — so an Outlook paste keeps its layout.
"""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from script.schemas import SynthesizedMinutes
from script.meeting_meta import empty_meta

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def write_email_html(
    synth: SynthesizedMinutes, dst: str, *, meeting_file: str
) -> None:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
        keep_trailing_newline=False,
    )
    meta = synth.meta or empty_meta()
    html = env.get_template("minutes_email.html.j2").render(
        synth=synth, m=meta, meeting_file=meeting_file
    )
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_text(html, encoding="utf-8")
