from script.transcript_loader import normalize, load_transcript, detect_format


def test_mmss_block_normalized_to_hhmmss():
    raw = "00:00\n第一段內容\n00:10\n第二段內容\n"
    assert normalize(raw) == (
        "[00:00:00] 第一段內容\n"
        "[00:00:10] 第二段內容\n"
    )


def test_h_mm_ss_timestamp_supported():
    raw = "1:02:03\n跨小時內容\n"
    assert normalize(raw) == "[01:02:03] 跨小時內容\n"


def test_multiline_block_collapsed_to_single_line():
    raw = "00:05\n第一行\n\n第二行   有空白\n"
    assert normalize(raw) == "[00:00:05] 第一行 第二行 有空白\n"


def test_leading_text_without_timestamp_gets_zero():
    raw = "開頭沒有時間戳的文字\n00:10\n後續\n"
    assert normalize(raw) == (
        "[00:00:00] 開頭沒有時間戳的文字\n"
        "[00:00:10] 後續\n"
    )


def test_timestamp_with_empty_block_is_skipped():
    raw = "00:00\n有內容\n00:10\n\n00:20\n再次有內容\n"
    assert normalize(raw) == (
        "[00:00:00] 有內容\n"
        "[00:00:20] 再次有內容\n"
    )


def test_output_compatible_with_chunker_ts_regex():
    import re
    out = normalize("3:07\nabc\n")
    assert re.match(r"^\[(\d{2}:\d{2}:\d{2})\]", out)


def test_load_transcript_reads_utf8_and_writes_dst(tmp_path):
    src = tmp_path / "in.txt"
    src.write_text("00:00\n你好\n", encoding="utf-8")
    dst = tmp_path / "out" / "transcript.md"
    load_transcript(str(src), str(dst))
    assert dst.read_text(encoding="utf-8") == "[00:00:00] 你好\n"


# ─────────────────────────── WebVTT (Teams) ──────────────────────────────

_VTT_BASIC = """WEBVTT

abc-123/1-0
00:00:07.006 --> 00:00:08.966
<v Shawn Lan>請問大家看得到畫面嗎？</v>

abc-123/2-0
00:00:13.156 --> 00:00:14.316
<v Shawn Lan>到就開始了。</v>
"""


def test_vtt_basic_speaker_extracted_and_ms_dropped():
    """One cue → one '[HH:MM:SS] Speaker: text' line; ms precision dropped."""
    assert normalize(_VTT_BASIC) == (
        "[00:00:07] Shawn Lan: 請問大家看得到畫面嗎？\n"
        "[00:00:13] Shawn Lan: 到就開始了。\n"
    )


def test_vtt_multiline_cue_text_joined():
    """A Teams cue can wrap its text across lines; closing </v> may sit on
    the final line. normalize joins with single spaces."""
    raw = (
        "WEBVTT\n\n"
        "x/1\n"
        "00:00:24.796 --> 00:00:32.496\n"
        "<v Shawn Lan>PP control這個finance net machine啊，\n"
        "還有之前沒有timeout的這個機制，</v>\n"
    )
    assert normalize(raw) == (
        "[00:00:24] Shawn Lan: PP control這個finance net machine啊， "
        "還有之前沒有timeout的這個機制，\n"
    )


def test_vtt_multiple_speakers_alternate():
    raw = (
        "WEBVTT\n\n"
        "id1\n00:00:01.000 --> 00:00:02.000\n<v Alice>hi</v>\n\n"
        "id2\n00:00:03.000 --> 00:00:04.000\n<v Bob Chen>hello</v>\n\n"
        "id3\n00:00:05.000 --> 00:00:06.000\n<v Alice>bye</v>\n"
    )
    assert normalize(raw) == (
        "[00:00:01] Alice: hi\n"
        "[00:00:03] Bob Chen: hello\n"
        "[00:00:05] Alice: bye\n"
    )


def test_vtt_cue_without_voice_tag_falls_back_to_no_speaker():
    """If a cue lacks <v...> (rare — e.g. shared screen narration with no
    attributed voice), emit timestamp + text without a speaker prefix."""
    raw = (
        "WEBVTT\n\n"
        "x/1\n00:00:10.000 --> 00:00:11.000\nplain text no voice tag\n"
    )
    assert normalize(raw) == "[00:00:10] plain text no voice tag\n"


def test_vtt_empty_cue_skipped():
    """If a cue has a time line but no text body, don't emit a stray
    '[HH:MM:SS] :' line — drop the cue entirely."""
    raw = (
        "WEBVTT\n\n"
        "x/1\n00:00:01.000 --> 00:00:02.000\n<v Alice>hi</v>\n\n"
        "x/2\n00:00:03.000 --> 00:00:04.000\n\n"
        "x/3\n00:00:05.000 --> 00:00:06.000\n<v Bob>bye</v>\n"
    )
    assert normalize(raw) == "[00:00:01] Alice: hi\n[00:00:05] Bob: bye\n"


def test_vtt_header_with_metadata_ignored():
    """VTT files often have header metadata (Kind:, Language:, NOTE blocks)
    between the WEBVTT line and the first cue. They must be skipped."""
    raw = (
        "WEBVTT\n"
        "Kind: captions\n"
        "Language: zh-TW\n"
        "\n"
        "NOTE this is a note\n"
        "\n"
        "x/1\n00:00:07.000 --> 00:00:08.000\n<v Alice>hi</v>\n"
    )
    assert normalize(raw) == "[00:00:07] Alice: hi\n"


def test_vtt_dispatch_does_not_confuse_android():
    """A line that happens to contain the word 'webvtt' deep inside an
    Android transcript must NOT trigger the VTT branch — only a first
    non-blank line equal to WEBVTT (case-insensitive prefix) routes there."""
    raw = "00:05\n我提到 webvtt 這個格式\n"
    # Falls through to Android path; speaker-less normal output.
    assert normalize(raw) == "[00:00:05] 我提到 webvtt 這個格式\n"


def test_vtt_load_transcript_end_to_end(tmp_path):
    src = tmp_path / "teams.vtt"
    src.write_text(_VTT_BASIC, encoding="utf-8")
    dst = tmp_path / "out" / "transcript.md"
    fmt = load_transcript(str(src), str(dst))
    assert fmt == "vtt"
    assert dst.read_text(encoding="utf-8") == (
        "[00:00:07] Shawn Lan: 請問大家看得到畫面嗎？\n"
        "[00:00:13] Shawn Lan: 到就開始了。\n"
    )


def test_load_transcript_returns_android_format(tmp_path):
    """load_transcript() return value is fed into pipeline's stage log so
    operators can audit which loader path the auto-detection took."""
    src = tmp_path / "in.txt"
    src.write_text("00:00\n你好\n", encoding="utf-8")
    dst = tmp_path / "out" / "transcript.md"
    assert load_transcript(str(src), str(dst)) == "android"


def test_detect_format_helper():
    assert detect_format("WEBVTT\n\nx") == "vtt"
    assert detect_format("\nWEBVTT\n\nx") == "vtt"  # leading blank ok
    assert detect_format("00:00\n你好\n") == "android"
    assert detect_format("") == "android"  # empty defaults to Android
