"""Local editable-minutes server: edit synthesized minutes in a browser, then
export to an Outlook draft. Binds 127.0.0.1 only; runs no LLM (it edits the
already-synthesized output, never the raw transcript).
"""
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from pydantic import ValidationError

from script.schemas import SynthesizedMinutes, AuditResult
from script import audit_mechanical
from script.email_writer import synth_to_finalized, render_email_html
from script.outlook_draft import open_draft
from script.meeting_meta import empty_meta

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def load_data(out_dir) -> dict:
    """Load {synthesized, audit} for the editable page (audit optional)."""
    inter = Path(out_dir) / "intermediate"
    synth = SynthesizedMinutes.model_validate_json(
        (inter / "synthesized.json").read_text(encoding="utf-8"))
    audit_path = inter / "audit.json"
    audit = (AuditResult.model_validate_json(audit_path.read_text(encoding="utf-8"))
             if audit_path.exists() else AuditResult())
    return {
        "synthesized": json.loads(synth.model_dump_json()),
        "audit": json.loads(audit.model_dump_json()),
    }


def render_edit_page(out_dir) -> str:
    """Render the editable page with DATA embedded as UTF-8 JSON."""
    data = load_data(out_dir)
    # ensure_ascii=False keeps Chinese readable; the "</" -> "<\/" replace stops
    # any "</script>" inside content from breaking out of the inline <script>.
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)
    return env.get_template("edit.html.j2").render(
        data_json=data_json,
        meeting_name=Path(out_dir).name,
    )


def handle_export(posted: dict, out_dir) -> dict:
    """Authoritative export: re-validate Layer-1 server-side, then write outputs
    and open an Outlook draft. Returns a JSON-able result dict.

    The client JS also gates, but never trust it — the mechanical check is
    re-run here and nothing is written unless it passes AND the payload is
    marked reviewed.
    """
    out_dir = Path(out_dir)
    if not isinstance(posted, dict):
        return {"ok": False, "reason": "invalid_payload",
                "detail": "expected a JSON object"}
    try:
        synth = SynthesizedMinutes.model_validate(posted.get("synthesized", {}))
    except ValidationError as e:
        return {"ok": False, "reason": "invalid_payload", "detail": str(e)}

    checks = audit_mechanical.evaluate(synth)
    if not audit_mechanical.overall_pass(checks):
        return {
            "ok": False,
            "reason": "audit_failed",
            "failing": [
                {"key": c.key, "label": c.label, "offending": c.offending}
                for c in checks if not c.passed
            ],
        }
    if not bool(posted.get("reviewed", False)):
        return {"ok": False, "reason": "not_reviewed"}

    inter = out_dir / "intermediate"
    inter.mkdir(parents=True, exist_ok=True)
    (inter / "synthesized.json").write_text(synth.model_dump_json(), encoding="utf-8")

    subject = out_dir.name
    meta = synth.meta if synth.meta is not None else empty_meta()
    final = synth_to_finalized(synth, subject=subject, meta=meta)
    email_html = render_email_html(final)
    email_path = out_dir / "email.html"
    email_path.write_text(email_html, encoding="utf-8")

    outlook_opened = open_draft(subject, email_html)

    return {
        "ok": True,
        "email_html": str(email_path),
        "outlook_opened": outlook_opened,
    }
