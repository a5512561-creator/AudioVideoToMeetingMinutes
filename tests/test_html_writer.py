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
    assert "1 議題" in t and "2 Action" in t
    assert "決議" not in t


def test_topics_tab_renders_title_summary_no_decisions(tmp_path):
    dst = tmp_path / "m.html"
    write_minutes_html(_synth(), ReviewResult(notes=[]), str(dst),
                       meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert "KPI / KTR 訂定方式" in t
    assert "討論 KPI 是否納入考核。" in t
    # the 決議 block was removed — decisions are no longer rendered
    assert "KPI 不納入考核" not in t and "兩週後帶 KTR 公式" not in t


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


def test_audio_buttons_present_when_clips_provided(tmp_path):
    dst = tmp_path / "m.html"
    # Clip values are data URLs; the per-button data-clip attr is just the
    # start-second key, which JS dereferences against the inlined CLIPS map.
    clips = {345: "data:audio/mp4;base64,XYZ_TOPIC", 82: "data:audio/mp4;base64,XYZ_ACTION"}
    write_minutes_html(_synth(), ReviewResult(notes=[]), str(dst),
                       meeting_file="x", pre=5, clips=clips)
    t = dst.read_text(encoding="utf-8")
    assert '<audio id="clip"' in t
    assert 'class="play"' in t
    assert 'data-clip="345"' in t   # topic 00:05:50 -> 350-5
    assert 'data-clip="82"' in t    # action 00:01:27 -> 87-5
    # JS CLIPS dict carries the actual data URLs
    assert '"345": "data:audio/mp4;base64,XYZ_TOPIC"' in t
    assert '"82": "data:audio/mp4;base64,XYZ_ACTION"' in t
    assert 'class="src"' not in t
    assert "聽</th>" in t


def test_no_audio_buttons_when_clips_empty(tmp_path):
    dst = tmp_path / "m.html"
    write_minutes_html(_synth(), ReviewResult(notes=[]), str(dst),
                       meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert '<audio' not in t
    assert 'class="play"' not in t
    assert 'class="src"' not in t
    assert "聽</th>" not in t
    assert "var CLIPS=" not in t


def test_audio_pre_roll_used_for_clip_lookup(tmp_path):
    dst = tmp_path / "m.html"
    # pre=10 → topic anchor 350-10=340, action anchor 87-10=77
    clips = {340: "data:audio/mpeg;base64,T", 77: "data:audio/mpeg;base64,A"}
    write_minutes_html(_synth(), ReviewResult(notes=[]), str(dst),
                       meeting_file="x", pre=10, clips=clips)
    t = dst.read_text(encoding="utf-8")
    assert 'data-clip="340"' in t
    assert 'data-clip="77"' in t


def test_audio_button_omitted_when_clip_missing_for_anchor(tmp_path):
    """Selective: if a topic's anchor has no matching clip, that ▶ is skipped
    but other items with matching clips still render."""
    dst = tmp_path / "m.html"
    # Only action 87-5=82 has a clip; topic 350-5=345 does not.
    clips = {82: "data:audio/mp4;base64,A"}
    write_minutes_html(_synth(), ReviewResult(notes=[]), str(dst),
                       meeting_file="x", pre=5, clips=clips)
    t = dst.read_text(encoding="utf-8")
    assert 'data-clip="82"' in t
    assert 'data-clip="345"' not in t


def test_action_renders_context_when_present(tmp_path):
    """前因 / context — when non-empty, shows beneath the task with the
    "前因：" label so readers see why this action exists, not just what."""
    from script.schemas import SynthAction
    s = _synth(action_items=[
        SynthAction(task="完成 API 規格", owner="小王", due="下週五",
                    priority="high",
                    context="下週要 demo、目前 API 規格未定為 blocker",
                    source_timestamps=["00:05:20"]),
    ])
    dst = tmp_path / "m.html"
    write_minutes_html(s, ReviewResult(notes=[]), str(dst), meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert "前因：" in t
    assert "下週要 demo" in t  # context content rendered
    assert 'class="ctx"' in t  # CSS class for styling


def test_action_skips_context_block_when_empty(tmp_path):
    """No 前因 row should appear when context is empty (back-compat: older
    cached SynthesizedMinutes JSON had no context field at all)."""
    from script.schemas import SynthAction
    s = _synth(action_items=[
        SynthAction(task="任意任務", owner="未明", due="未明",
                    priority="medium",
                    source_timestamps=["00:00:00"]),  # context defaults to ""
    ])
    dst = tmp_path / "m.html"
    write_minutes_html(s, ReviewResult(notes=[]), str(dst), meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert "前因：" not in t
    assert 'class="ctx"' not in t


def test_clips_dict_contains_each_unique_url_once(tmp_path):
    """When a topic and action share the same start, the JS CLIPS dict still
    lists each URL exactly once (key-collapse via dict)."""
    from script.schemas import SynthTopic, SynthAction
    s = _synth(
        topics=[SynthTopic(title="T", summary="s",
                            decisions=["d1", "d2", "d3"],
                            source_timestamps=["00:05:50"])],
        action_items=[SynthAction(task="t", owner="o", due="d", priority="high",
                                   source_timestamps=["00:05:50"])],
    )
    dst = tmp_path / "m.html"
    clips = {345: "data:audio/mp4;base64,SHARED"}
    write_minutes_html(s, ReviewResult(notes=[]), str(dst),
                       meeting_file="x", pre=5, clips=clips)
    t = dst.read_text(encoding="utf-8")
    # 1 topic-title ▶ + 1 action ▶ share start=345 → 2 buttons with data-clip="345"
    # (decisions no longer render, so they contribute no buttons)
    assert t.count('data-clip="345"') == 2
    # but the data URL appears exactly once (in the JS CLIPS dict)
    assert t.count("SHARED") == 1


def test_html_shows_llm_model(tmp_path):
    dst = tmp_path / "m.html"
    s = _synth(meta=MeetingMeta(meeting_date="2026/05/18",
                                duration_hint="約 1h",
                                llm_model="claude-opus-4-8"))
    write_minutes_html(s, ReviewResult(notes=[]), str(dst), meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert "LLM 整理" in t and "claude-opus-4-8" in t


def test_html_omits_llm_when_blank(tmp_path):
    dst = tmp_path / "m2.html"
    write_minutes_html(_synth(), ReviewResult(notes=[]), str(dst), meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert "LLM 整理" not in t
