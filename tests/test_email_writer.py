from script.schemas import (
    SynthesizedMinutes, SynthTopic, SynthAction, MeetingMeta,
    FinalizedMinutes, FinalTopic, FinalAction,
)
from script.email_writer import (
    synth_to_finalized, render_email_html, write_email_html,
)


def _synth():
    return SynthesizedMinutes(
        meta=MeetingMeta(meeting_date="2026/06/04", duration_hint="約 2h"),
        topics=[SynthTopic(title="FCS 移除彈性討論",
                           summary="討論是否提供 FCS 移除彈性。",
                           decisions=["此項尚無定論，後續確認"],
                           source_timestamps=["00:05:50"])],
        action_items=[SynthAction(task="釐清 FCS 移除需求",
                                  owner="林冠名", due="6/E", priority="high",
                                  source_timestamps=["00:01:27"])],
    )


def _final():
    return FinalizedMinutes(
        meta=MeetingMeta(
            meeting_date="2026/06/04", duration_hint="約 2h",
            meeting_time="16:00 - 18:00", location="R531",
            attendees="Max、Heping", recorder="林冠名",
            doc_links="spec.docx", video_links="rec.mp4", jira="",
        ),
        subject="會議記錄: Channelize",
        topics=[FinalTopic(item="FCS 移除彈性討論",
                           summary="討論是否提供彈性（決議：尚無定論，後續確認）")],
        actions=[FinalAction(task="釐清 FCS 移除需求", owner="林冠名",
                             due="6/E", note="")],
    )


def test_synth_to_finalized_keeps_decisions_separate():
    f = synth_to_finalized(_synth(), subject="會議記錄", meta=_synth().meta)
    assert f.subject == "會議記錄"
    assert f.topics[0].item == "FCS 移除彈性討論"
    # decisions are carried as their own field, NOT folded into the summary
    assert f.topics[0].decisions == ["此項尚無定論，後續確認"]
    assert "決議" not in f.topics[0].summary
    assert f.topics[0].summary == "討論是否提供 FCS 移除彈性。"
    assert f.actions[0].owner == "林冠名" and f.actions[0].due == "6/E"
    assert f.actions[0].note == ""


def test_email_html_renders_summary_as_numbered_list_and_blue_decisions(tmp_path):
    """Summary becomes an <ol> of sentences; decisions render as a distinct
    blue (#0563C1) 決議 block rather than parenthetical text in the summary."""
    synth = _synth()
    synth.topics[0].summary = "第一點。第二點。"
    f = synth_to_finalized(synth, subject="會議記錄", meta=synth.meta)
    dst = tmp_path / "e.html"
    write_email_html(f, str(dst))
    html = dst.read_text(encoding="utf-8")
    assert "<ol" in html
    assert "<li" in html and "第一點。" in html and "第二點。" in html
    assert "決議" in html
    assert "#0563C1" in html or "#0563c1" in html
    assert "此項尚無定論，後續確認" in html


def test_email_html_company_format(tmp_path):
    dst = tmp_path / "minutes_email.html"
    write_email_html(_final(), str(dst))
    html = dst.read_text(encoding="utf-8")
    assert "Dear all" in html
    assert "Best regards" in html and "林冠名" in html
    assert "2026/06/04" in html and "16:00 - 18:00" in html and "R531" in html
    assert "____" not in html
    assert "會議記錄與決議" in html and "項目" in html and "摘要" in html
    assert "Action Items" in html
    assert "行動項目" in html and "負責人" in html and "到期日" in html and "備註" in html
    assert "優先級" not in html
    assert "釐清 FCS 移除需求" in html and "6/E" in html
    assert "<script" not in html


def test_email_html_blank_fields_render_empty(tmp_path):
    f = _final()
    f.meta.attendees = ""
    f.meta.location = ""
    dst = tmp_path / "e.html"
    write_email_html(f, str(dst))
    html = dst.read_text(encoding="utf-8")
    assert "參與人員" in html
    assert "____" not in html


def test_email_html_escapes_text(tmp_path):
    f = _final()
    f.topics[0].summary = "風險 <b>注意</b> & 風控"
    dst = tmp_path / "e.html"
    write_email_html(f, str(dst))
    html = dst.read_text(encoding="utf-8")
    assert "&lt;b&gt;" in html and "&amp;" in html


def test_email_html_shows_llm_model_note(tmp_path):
    f = _final()
    f.meta.llm_model = "claude-opus-4-8"
    dst = tmp_path / "e.html"
    write_email_html(f, str(dst))
    html = dst.read_text(encoding="utf-8")
    assert "claude-opus-4-8" in html
    assert "LLM" in html and "人工校閱" in html


def test_email_html_omits_llm_note_when_blank(tmp_path):
    f = _final()  # llm_model defaults to ""
    dst = tmp_path / "e2.html"
    write_email_html(f, str(dst))
    html = dst.read_text(encoding="utf-8")
    assert "人工校閱" not in html
