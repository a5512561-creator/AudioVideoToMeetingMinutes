from pathlib import Path
from script.validate_source import validate_source, SourceReport


def _write(p: Path, text: str) -> Path:
    p.write_text(text, encoding="utf-8")
    return p


def test_valid_transcript_reports_ok(tmp_path):
    src = _write(tmp_path / "mtg.txt",
                 "00:00 大家好\n00:12 開始討論 KPI\n01:05 結論\n")
    r = validate_source(str(src))
    assert isinstance(r, SourceReport)
    assert r.exists is True
    assert r.utf8 is True
    assert r.timestamp_lines >= 3
    assert r.first_timestamp == "00:00"
    assert r.last_timestamp == "01:05"
    assert r.non_empty is True
    assert r.ok is True
    assert r.problems == []


def test_missing_file_is_not_ok(tmp_path):
    r = validate_source(str(tmp_path / "nope.txt"))
    assert r.exists is False
    assert r.ok is False
    assert any("找不到" in p for p in r.problems)


def test_no_timestamps_flags_problem(tmp_path):
    src = _write(tmp_path / "flat.txt", "大家好\n開始討論\n沒有時間戳\n")
    r = validate_source(str(src))
    assert r.timestamp_lines == 0
    assert r.ok is False
    assert any("時間戳" in p for p in r.problems)


def test_report_contains_no_transcript_text(tmp_path):
    secret = "極機密專案代號 BLUEFALCON"
    src = _write(tmp_path / "s.txt", f"00:00 {secret}\n00:10 結束\n")
    r = validate_source(str(src))
    dumped = r.model_dump_json()
    # Metadata only — the report must never carry transcript content.
    assert secret not in dumped
    assert "BLUEFALCON" not in dumped


def test_detects_sibling_audio(tmp_path):
    _write(tmp_path / "mtg.txt", "00:00 hi\n00:10 bye\n")
    (tmp_path / "mtg.m4a").write_bytes(b"\x00\x01\x02")
    r = validate_source(str(tmp_path / "mtg.txt"))
    assert r.has_sibling_audio is True
    assert r.audio_ext == ".m4a"


def test_valid_vtt_transcript_reports_ok(tmp_path):
    vtt = ("WEBVTT\n\n"
           "00:00:00.000 --> 00:00:03.500\n大家好\n\n"
           "00:01:05.200 --> 00:01:08.000\n結論\n")
    src = _write(tmp_path / "mtg.vtt", vtt)
    r = validate_source(str(src))
    assert r.timestamp_lines == 2
    assert r.first_timestamp == "00:00:00"
    assert r.last_timestamp == "00:01:05"
    assert r.ok is True


def test_vtt_report_leaks_no_text(tmp_path):
    vtt = ("WEBVTT\n\n00:00:00.000 --> 00:00:03.500\n極機密 BLUEFALCON\n")
    src = _write(tmp_path / "s.vtt", vtt)
    r = validate_source(str(src))
    assert "BLUEFALCON" not in r.model_dump_json()


def test_non_utf8_file_flagged(tmp_path):
    p = tmp_path / "bad.vtt"
    p.write_bytes(b"\xff\xfe\x00bad")
    r = validate_source(str(p))
    assert r.exists is True
    assert r.utf8 is False
    assert r.ok is False
