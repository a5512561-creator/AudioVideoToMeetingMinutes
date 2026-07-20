import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

from script.audio_assets import (
    find_sibling_audio, clip_start, output_audio, cut_clips,
    find_sibling_media, is_video_container, extract_audio_track,
)


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


# ── sibling media discovery (audio + video containers) ──────────────────────

def test_find_sibling_media_prefers_audio_over_video(tmp_path):
    (tmp_path / "mtg.txt").write_text("x", encoding="utf-8")
    (tmp_path / "mtg.mp4").write_bytes(b"video")
    (tmp_path / "mtg.m4a").write_bytes(b"audio")
    got = find_sibling_media(str(tmp_path / "mtg.txt"))
    assert got is not None and got.name == "mtg.m4a"  # audio wins over video


def test_find_sibling_media_finds_mp4(tmp_path):
    (tmp_path / "會議.txt").write_text("x", encoding="utf-8")
    (tmp_path / "會議.mp4").write_bytes(b"video")  # Teams recording
    got = find_sibling_media(str(tmp_path / "會議.txt"))
    assert got is not None and got.name == "會議.mp4"


def test_find_sibling_media_none_when_absent(tmp_path):
    (tmp_path / "mtg.txt").write_text("x", encoding="utf-8")
    assert find_sibling_media(str(tmp_path / "mtg.txt")) is None


def test_find_sibling_audio_still_ignores_video(tmp_path):
    # find_sibling_audio stays audio-only; video is find_sibling_media's job.
    (tmp_path / "mtg.txt").write_text("x", encoding="utf-8")
    (tmp_path / "mtg.mp4").write_bytes(b"video")
    assert find_sibling_audio(str(tmp_path / "mtg.txt")) is None


def test_is_video_container():
    assert is_video_container(Path("a.mp4")) is True
    assert is_video_container(Path("a.MP4")) is True  # case-insensitive
    assert is_video_container(Path("a.m4a")) is False
    assert is_video_container(Path("a.wav")) is False


def _fake_extract_run(dst_index: int, fail_on_copy: bool = False):
    """subprocess.run replacement for extract_audio_track. Writes a non-empty
    dst and returns rc=0, unless fail_on_copy and the command is a stream copy
    (``-c:a copy``), in which case it returns rc=1 without writing."""
    def _run(cmd, **kw):
        if fail_on_copy and "copy" in cmd:
            return MagicMock(returncode=1, stdout=b"", stderr=b"cannot copy")
        Path(cmd[dst_index]).write_bytes(b"AUDIO" * 300)
        return MagicMock(returncode=0, stdout=b"", stderr=b"")
    return _run


@patch("script.audio_assets.subprocess.run", side_effect=_fake_extract_run(-1))
def test_extract_audio_track_stream_copy_success(run_m, tmp_path):
    video = tmp_path / "會議.mp4"
    video.write_bytes(b"VIDEO")
    dst = tmp_path / "audio.m4a"
    assert extract_audio_track(video, dst) is True
    assert dst.exists() and dst.stat().st_size > 0
    # Only one ffmpeg call: the stream copy succeeded, no re-encode fallback.
    assert run_m.call_count == 1
    assert "copy" in run_m.call_args_list[0].args[0]


@patch("script.audio_assets.subprocess.run",
       side_effect=_fake_extract_run(-1, fail_on_copy=True))
def test_extract_audio_track_reencode_fallback(run_m, tmp_path):
    video = tmp_path / "會議.mp4"
    video.write_bytes(b"VIDEO")
    dst = tmp_path / "audio.m4a"
    assert extract_audio_track(video, dst) is True
    # copy attempt failed, re-encode attempt succeeded → two calls.
    assert run_m.call_count == 2
    assert "aac" in run_m.call_args_list[1].args[0]


def _fake_extract_run_copy_container_only(dst_index: int):
    """Stream copy returns rc=0 but writes only a 44-byte container header
    (ffmpeg's silent-fail mode); re-encode writes a real file."""
    def _run(cmd, **kw):
        if "copy" in cmd:
            Path(cmd[dst_index]).write_bytes(b"\x00" * 44)  # container-only
            return MagicMock(returncode=0, stdout=b"", stderr=b"")
        Path(cmd[dst_index]).write_bytes(b"AUDIO" * 300)  # real re-encode
        return MagicMock(returncode=0, stdout=b"", stderr=b"")
    return _run


@patch("script.audio_assets.subprocess.run",
       side_effect=_fake_extract_run_copy_container_only(-1))
def test_extract_audio_track_rejects_container_only_copy(run_m, tmp_path):
    video = tmp_path / "會議.mp4"
    video.write_bytes(b"VIDEO")
    dst = tmp_path / "audio.m4a"
    # copy produced a 44-byte header → rejected → re-encode fallback succeeds.
    assert extract_audio_track(video, dst) is True
    assert run_m.call_count == 2
    assert dst.stat().st_size >= 1024


@patch("script.audio_assets.subprocess.run",
       side_effect=FileNotFoundError("ffmpeg not on PATH"))
def test_extract_audio_track_missing_ffmpeg_returns_false(run_m, tmp_path):
    video = tmp_path / "會議.mp4"
    video.write_bytes(b"VIDEO")
    assert extract_audio_track(video, tmp_path / "audio.m4a") is False


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


def test_output_audio_prefers_extension_order(tmp_path):
    (tmp_path / "audio.aac").write_text("a", encoding="utf-8")
    (tmp_path / "audio.m4a").write_text("a", encoding="utf-8")
    got = output_audio(tmp_path)
    assert got is not None and got.name == "audio.m4a"  # .m4a beats .aac


def test_output_audio_none_when_absent(tmp_path):
    (tmp_path / "audio.json").write_text("{}", encoding="utf-8")  # not an audio ext
    assert output_audio(tmp_path) is None


def _fake_run_writes(dst_index: int):
    """Build a subprocess.run replacement that writes a sufficiently large
    file to the path given by argv[dst_index] (last positional). Returns
    rc=0. Payload must clear cut_clips' 1KB minimum-real-clip threshold so
    it's not mistaken for an HE-AAC seek-failure container-only output."""
    def _run(cmd, **kw):
        Path(cmd[dst_index]).write_bytes(b"FAKECLIP" * 256)  # 2048 bytes
        return MagicMock(returncode=0, stdout=b"", stderr=b"")
    return _run


@patch("script.audio_assets.subprocess.run", side_effect=_fake_run_writes(-1))
def test_cut_clips_writes_one_file_per_unique_start(run_m, tmp_path):
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"SRC")
    got = cut_clips(audio, [345, 82, 345], duration=10, out_dir=tmp_path)
    assert got == {82: "clip_82.m4a", 345: "clip_345.m4a"}
    assert (tmp_path / "clip_82.m4a").exists()
    assert (tmp_path / "clip_345.m4a").exists()
    # one ffmpeg invocation per unique start
    assert run_m.call_count == 2


@patch("script.audio_assets.subprocess.run", side_effect=_fake_run_writes(-1))
def test_cut_clips_ignores_none_starts(run_m, tmp_path):
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"SRC")
    got = cut_clips(audio, [10, None, 20], duration=10, out_dir=tmp_path)
    assert set(got.keys()) == {10, 20}


@patch("script.audio_assets.subprocess.run", side_effect=_fake_run_writes(-1))
def test_cut_clips_clears_stale_same_ext(run_m, tmp_path):
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"SRC")
    (tmp_path / "clip_999.m4a").write_bytes(b"STALE")  # should be wiped
    (tmp_path / "clip_999.mp3").write_bytes(b"OTHER EXT")  # untouched
    got = cut_clips(audio, [10], duration=10, out_dir=tmp_path)
    assert got == {10: "clip_10.m4a"}
    assert not (tmp_path / "clip_999.m4a").exists()
    assert (tmp_path / "clip_999.mp3").exists()


@patch("script.audio_assets.subprocess.run",
       side_effect=FileNotFoundError("ffmpeg not on PATH"))
def test_cut_clips_returns_empty_when_ffmpeg_missing(run_m, tmp_path):
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"SRC")
    assert cut_clips(audio, [10], duration=10, out_dir=tmp_path) == {}


@patch("script.audio_assets.subprocess.run",
       return_value=MagicMock(returncode=1, stdout=b"", stderr=b"bad input"))
def test_cut_clips_returns_empty_on_ffmpeg_error(run_m, tmp_path):
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"SRC")
    assert cut_clips(audio, [10], duration=10, out_dir=tmp_path) == {}


def _fake_run_writes_tiny(dst_index: int):
    """Mimic ffmpeg's HE-AAC-seek-failure mode: rc=0 but only the m4a
    container header is written (~44 bytes, no audio). Real cuts are KB+."""
    def _run(cmd, **kw):
        Path(cmd[dst_index]).write_bytes(b"\x00" * 44)  # 44-byte empty m4a
        return MagicMock(returncode=0, stdout=b"", stderr=b"")
    return _run


@patch("script.audio_assets.subprocess.run", side_effect=_fake_run_writes_tiny(-1))
def test_cut_clips_rejects_container_only_output(run_m, tmp_path):
    """Regression: ffmpeg's HE-AAC seek can return rc=0 with a 44-byte
    file containing no audio data. Such outputs were previously accepted
    and inlined as base64, producing a ▶ that did nothing when clicked.
    Now the size threshold rejects them so they trigger retry → skip."""
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"SRC")
    # subprocess.run is called twice per start (1 attempt + 1 retry); both
    # produce 44-byte files, so the start is skipped, returning {}.
    assert cut_clips(audio, [10], duration=10, out_dir=tmp_path) == {}
    # And the empty placeholder file should not be left behind.
    assert not (tmp_path / "clip_10.m4a").exists()
