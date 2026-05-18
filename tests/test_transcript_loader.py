from script.transcript_loader import normalize, load_transcript


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
