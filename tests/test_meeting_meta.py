from script.meeting_meta import infer_meeting_date, duration_hint


def test_date_from_8digit_in_name():
    assert infer_meeting_date("20260518_leadersync", "x.txt") == "2026/05/18"


def test_date_from_separated_in_src_when_name_missing():
    assert infer_meeting_date(None, r"D:\m\2026-05-18 meeting.txt") == "2026/05/18"


def test_date_name_takes_precedence_over_src():
    assert infer_meeting_date("20260101_x", r"D:\m\20251231.txt") == "2026/01/01"


def test_date_fallback_placeholder():
    assert infer_meeting_date("leadersync", "meeting.txt") == "YYYY/MM/DD"


def test_duration_hint_from_span():
    md = "[00:00:00] a\n[00:10:00] b\n[01:55:14] c\n"
    assert duration_hint(md) == "逐字稿長度約 1h 55m"


def test_duration_hint_no_timestamps():
    assert duration_hint("no timestamps here\n") == "逐字稿長度未知"


def test_empty_meta_placeholders():
    from script.meeting_meta import empty_meta
    from script.schemas import MeetingMeta
    m = empty_meta()
    assert isinstance(m, MeetingMeta)
    assert m.meeting_date == "YYYY/MM/DD"
    assert m.duration_hint == "逐字稿長度未知"
