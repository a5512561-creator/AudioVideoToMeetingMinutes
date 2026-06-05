"""Interactive finalize step: confirm minutes, render email, open Outlook draft.

Reads the cached synthesized.json from a prior `process` run, runs the
terminal Q&A, persists finalized.json, writes minutes_email.html, and opens
an editable Outlook draft (falling back to the HTML file if Outlook is
unavailable). Runs no LLM calls.
"""
from pathlib import Path

from script.schemas import SynthesizedMinutes, FinalizedMinutes
from script.email_writer import synth_to_finalized, render_email_html
from script.qna import run_qna
from script.outlook_draft import open_draft
from script.meeting_meta import empty_meta


def run_finalize(out_dir: str, *, default_subject: str, reuse: bool = False,
                 inp=input, out=print) -> None:
    out_path = Path(out_dir)
    synth_path = out_path / "intermediate" / "synthesized.json"
    if not synth_path.exists():
        raise RuntimeError(
            f"找不到 {synth_path} — 請先對此會議跑 `process` 產生會議記錄。"
        )
    synth = SynthesizedMinutes.model_validate_json(
        synth_path.read_text(encoding="utf-8"))

    finalized_path = out_path / "finalized.json"
    if reuse and finalized_path.exists():
        initial = FinalizedMinutes.model_validate_json(
            finalized_path.read_text(encoding="utf-8"))
    else:
        initial = synth_to_finalized(
            synth, subject=default_subject, meta=synth.meta or empty_meta())

    final = run_qna(initial, inp=inp, out=out)

    finalized_path.write_text(final.model_dump_json(), encoding="utf-8")
    html_path = out_path / "minutes_email.html"
    html = render_email_html(final)
    html_path.write_text(html, encoding="utf-8")

    if open_draft(final.subject, html):
        out(f"\n✅ 已開啟 Outlook 草稿（未寄出）。同時輸出：{html_path}")
    else:
        out(f"\n⚠️ 無法開啟 Outlook 草稿；已輸出 HTML，請手動開啟：{html_path}")
