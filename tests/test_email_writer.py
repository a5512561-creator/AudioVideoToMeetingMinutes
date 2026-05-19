from script.schemas import (
    SynthesizedMinutes, SynthTopic, SynthAction, SourceRef, MeetingMeta,
)
from script.email_writer import write_email_html


def _synth():
    return SynthesizedMinutes(
        meta=MeetingMeta(meeting_date="2026/05/18",
                         duration_hint="逐字稿長度約 1h 55m"),
        topics=[SynthTopic(title="KPI / KTR 訂定方式",
                            summary="討論 KPI 是否納入考核。",
                            decisions=["KPI 不納入考核"],
                            source_timestamps=["00:05:50"])],
        action_items=[SynthAction(task="各團隊試算 KTR 公式",
                                  owner="各團隊", due="兩週後", priority="high",
                                  source_timestamps=["00:01:27"])],
        source_index=[SourceRef(label="決議 1", timestamps=["00:05:50"]),
                      SourceRef(label="Action 1", timestamps=["00:01:27"])],
    )


def test_email_html_has_template_fields_and_no_script(tmp_path):
    dst = tmp_path / "minutes_email.html"
    write_email_html(_synth(), str(dst), meeting_file=r"D:\m\x.txt")
    html = dst.read_text(encoding="utf-8")
    assert "會議日期" in html and "2026/05/18" in html
    assert "逐字稿長度約 1h 55m" in html
    assert "參與人員" in html and "____" in html
    assert "記錄人" in html
    assert "會議記錄與決議" in html
    assert "KPI / KTR 訂定方式" in html
    assert "KPI 不納入考核" in html
    assert "Action Items" in html
    assert "<table" in html
    assert "各團隊試算 KTR 公式" in html and "兩週後" in html
    assert "來源對照" in html
    assert "決議 1" in html and "00:05:50" in html
    assert "<script" not in html
    assert "tab(" not in html and 'class="tab"' not in html


def test_email_html_escapes_text(tmp_path):
    s = _synth()
    s.topics[0].summary = "風險 <b>注意</b> & 風控"
    dst = tmp_path / "e.html"
    write_email_html(s, str(dst), meeting_file="x")
    html = dst.read_text(encoding="utf-8")
    assert "&lt;b&gt;" in html and "&amp;" in html
