import pytest
from script.chunker import chunk_transcript, Chunk


def _md(lines):
    return "\n".join(lines) + "\n"


def test_single_short_chunk_returned_intact():
    text = _md([
        "[00:00:01] 短句一。",
        "[00:00:05] 短句二。",
    ])
    chunks = chunk_transcript(text, max_tokens=1000, overlap_ratio=0.1)
    assert len(chunks) == 1
    assert chunks[0].text.strip() == text.strip()
    assert chunks[0].first_timestamp == "00:00:01"
    assert chunks[0].last_timestamp == "00:00:05"


def test_chunk_split_when_exceeding_max_tokens():
    # 50 sentences, each ~10 chars; with max_tokens=20 (worst-case=30 chars) → multiple chunks
    sentences = [f"[00:00:{i:02d}] 句子第{i}個結尾。" for i in range(50)]
    text = _md(sentences)
    chunks = chunk_transcript(text, max_tokens=20, overlap_ratio=0.1)
    assert len(chunks) >= 2
    # No chunk exceeds limit (allow some slack as we cut at sentence boundary)
    for c in chunks:
        assert c.token_estimate <= 20 * 1.5


def test_overlap_repeats_last_lines_of_previous_chunk():
    sentences = [f"[00:00:{i:02d}] 句子{i}。" for i in range(40)]
    text = _md(sentences)
    chunks = chunk_transcript(text, max_tokens=15, overlap_ratio=0.20)
    assert len(chunks) >= 2
    # Second chunk should start with some content also present at end of first
    first_lines = set(chunks[0].text.splitlines()[-3:])
    second_lines = set(chunks[1].text.splitlines()[:3])
    assert first_lines & second_lines, "expected overlap between adjacent chunks"


def test_token_estimate_uses_char_x_15_when_tiktoken_unavailable(monkeypatch):
    # Force the fallback path
    monkeypatch.setattr("script.chunker._tiktoken_count", lambda s: None)
    chunks = chunk_transcript("[00:00:01] 你好。\n", max_tokens=1000, overlap_ratio=0.1)
    assert chunks[0].token_estimate == int(len("[00:00:01] 你好。") * 1.5)


def test_first_and_last_timestamp_extracted():
    text = _md([
        "[00:01:30] A",
        "[00:02:45] B",
        "[01:23:45] C",
    ])
    chunks = chunk_transcript(text, max_tokens=1000, overlap_ratio=0.1)
    assert chunks[0].first_timestamp == "00:01:30"
    assert chunks[0].last_timestamp == "01:23:45"
