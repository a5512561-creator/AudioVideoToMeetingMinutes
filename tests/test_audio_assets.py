from pathlib import Path
from script.audio_assets import find_sibling_audio, clip_start


def test_find_sibling_prefers_extension_order(tmp_path):
    (tmp_path / "mtg.txt").write_text("x", encoding="utf-8")
    (tmp_path / "mtg.mp3").write_text("a", encoding="utf-8")
    (tmp_path / "mtg.m4a").write_text("a", encoding="utf-8")
    got = find_sibling_audio(str(tmp_path / "mtg.txt"))
    assert got is not None and got.name == "mtg.m4a"  # .m4a first in order


def test_find_sibling_single_match(tmp_path):
    (tmp_path / "會議.txt").write_text("x", encoding="utf-8")
    (tmp_path / "會議.wav").write_text("a", encoding="utf-8")
    got = find_sibling_audio(str(tmp_path / "會議.txt"))
    assert got is not None and got.name == "會議.wav"


def test_find_sibling_none_when_absent(tmp_path):
    (tmp_path / "mtg.txt").write_text("x", encoding="utf-8")
    assert find_sibling_audio(str(tmp_path / "mtg.txt")) is None


def test_find_sibling_ignores_different_stem(tmp_path):
    (tmp_path / "mtg.txt").write_text("x", encoding="utf-8")
    (tmp_path / "other.m4a").write_text("a", encoding="utf-8")
    assert find_sibling_audio(str(tmp_path / "mtg.txt")) is None


def test_clip_start_hhmmss_minus_pre():
    assert clip_start("01:02:03", 5) == 3723 - 5


def test_clip_start_mmss():
    assert clip_start("05:50", 5) == 350 - 5


def test_clip_start_clamps_to_zero():
    assert clip_start("00:00:02", 5) == 0


def test_clip_start_bad_value_returns_none():
    assert clip_start("", 5) is None
    assert clip_start("abc", 5) is None
    assert clip_start("1:2:3:4", 5) is None
