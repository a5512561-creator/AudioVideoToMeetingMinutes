import re
from script.schemas import (
    SynthesizedMinutes, SynthTopic, SynthAction, SourceRef,
    MeetingMeta, ReviewNote, ReviewResult,
)
from script.html_writer import write_minutes_html


def _synth(**over):
    base = dict(
        meta=MeetingMeta(meeting_date="2026/05/18",
                         duration_hint="逐字稿長度約 1h 55m"),
        topics=[SynthTopic(title="KPI / KTR 訂定方式",
                            summary="討論 KPI 是否納入考核。",
                            decisions=["KPI 不納入考核", "兩週後帶 KTR 公式"],
                            source_timestamps=["00:05:50"])],
        action_items=[SynthAction(task="各團隊試算 KTR 公式", owner="各團隊",
                                  due="兩週後", priority="high",
                                  source_timestamps=["00:01:27"]),
                      SynthAction(task="更新 wiki", owner="未明",
                                  due="未明", priority="low",
                                  source_timestamps=["00:30:00"])],
        source_index=[SourceRef(label="決議 1", timestamps=["00:05:50"])],
    )
    base.update(over)
    return SynthesizedMinutes(**base)


def _warn(section="conclusion", tid="C2", note="語意模糊"):
    return ReviewNote(target_section=section, target_id=tid,
                      category="ambiguity", severity="warn",
                      note=note, suggestion="請確認")


def _ok():
    return ReviewNote(target_section="conclusion", target_id="C1",
                      category="ok", severity="info", note="", suggestion="")


def test_html_has_three_tabs_and_header(tmp_path):
    dst = tmp_path / "m.html"
    write_minutes_html(_synth(), ReviewResult(notes=[_ok()]), str(dst),
                       meeting_file=r"D:\m\x.txt",
                       meta=MeetingMeta(meeting_date="2026/05/18",
                                        duration_hint="逐字稿長度約 1h 55m"))
    t = dst.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in t
    assert 'data-tab="topics"' in t
    assert 'data-tab="actions"' in t
    assert 'data-tab="review"' in t
    assert 'data-tab="conclusions"' not in t and 'data-tab="keypoints"' not in t
    assert "2026/05/18" in t
    assert "逐字稿長度約 1h 55m" in t
    assert "x.txt" in t
    assert "1 議題" in t and "2 決議" in t and "2 Action" in t


def test_topics_tab_renders_title_summary_decisions(tmp_path):
    dst = tmp_path / "m.html"
    write_minutes_html(_synth(), ReviewResult(notes=[]), str(dst),
                       meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert "KPI / KTR 訂定方式" in t
    assert "討論 KPI 是否納入考核。" in t
    assert "KPI 不納入考核" in t and "兩週後帶 KTR 公式" in t
    assert "00:05:50" in t


def test_actions_tab_table_and_priority_filter(tmp_path):
    dst = tmp_path / "m.html"
    write_minutes_html(_synth(), ReviewResult(notes=[]), str(dst),
                       meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert "<table" in t
    assert "各團隊試算 KTR 公式" in t and "更新 wiki" in t
    assert 'data-priority="high"' in t and 'data-priority="low"' in t
    assert "高" in t and "低" in t


def test_review_tab_shows_warn_with_disclaimer(tmp_path):
    dst = tmp_path / "m.html"
    write_minutes_html(_synth(), ReviewResult(notes=[_ok(), _warn(note="模糊點")]),
                       str(dst), meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    rev = re.search(r'<section id="review".*?</section>', t, re.DOTALL).group(0)
    assert "原始抽取項目" in rev
    assert "模糊點" in rev
    assert "請確認" in rev
    assert rev.count("C1") == 0


def test_no_speaker_or_source_quote_remnants(tmp_path):
    dst = tmp_path / "m.html"
    write_minutes_html(_synth(), ReviewResult(notes=[]), str(dst),
                       meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert "speaker" not in t.lower()
    assert "SPEAKER_" not in t
    assert "source_quote" not in t
    assert "來源原句" not in t


def test_meta_fallback_when_none(tmp_path):
    s = _synth(meta=None)
    dst = tmp_path / "m.html"
    write_minutes_html(s, ReviewResult(notes=[]), str(dst), meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert "YYYY/MM/DD" in t and "逐字稿長度未知" in t


def test_html_self_contained_and_escapes(tmp_path):
    s = _synth()
    s.topics[0].summary = "風險 <b>注意</b> & 風控"
    dst = tmp_path / "m.html"
    write_minutes_html(s, ReviewResult(notes=[]), str(dst), meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert "cdn." not in t.lower() and "//unpkg" not in t
    assert "<style>" in t and "<script>" in t
    assert "&lt;b&gt;" in t and "&amp;" in t


def test_medium_priority_renders_label_and_data_attr(tmp_path):
    s = _synth(action_items=[SynthAction(task="中度任務", owner="未明",
                                         due="未明", priority="medium",
                                         source_timestamps=["00:09:00"])])
    dst = tmp_path / "m.html"
    write_minutes_html(s, ReviewResult(notes=[]), str(dst), meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert 'data-priority="medium"' in t
    assert "中度任務" in t
    assert "中" in t  # medium -> 中 label
