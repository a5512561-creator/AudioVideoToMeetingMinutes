import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
from script.media import extract_audio, FFmpegMissingError, FFmpegFailedError, _find_ffmpeg


def test_extract_audio_builds_correct_command(tmp_path):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    dst = tmp_path / "out.wav"

    with patch("script.media._find_ffmpeg", return_value="ffmpeg"), \
         patch("script.media.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        extract_audio(str(src), str(dst))

    args = run.call_args[0][0]
    assert args[0] == "ffmpeg"
    assert "-i" in args and str(src) in args
    assert "-vn" in args
    assert "-ac" in args and "1" in args
    assert "-ar" in args and "16000" in args
    assert "-c:a" in args and "pcm_s16le" in args
    assert str(dst) in args


def test_extract_audio_disables_stdin_to_prevent_truncation(tmp_path):
    """Regression: without -nostdin + stdin=DEVNULL, ffmpeg can read random
    bytes from a piped parent stdin and interpret them as 'q' (quit), silently
    truncating output mid-extraction while still returning exit 0. We saw a
    75-min meeting truncated to 20 min in production.
    """
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    dst = tmp_path / "out.wav"

    with patch("script.media._find_ffmpeg", return_value="ffmpeg"), \
         patch("script.media.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        extract_audio(str(src), str(dst))

    args = run.call_args[0][0]
    assert "-nostdin" in args
    assert run.call_args.kwargs["stdin"] == subprocess.DEVNULL


def test_extract_audio_raises_when_ffmpeg_missing(tmp_path):
    with patch("script.media._find_ffmpeg", return_value=None):
        with pytest.raises(FFmpegMissingError):
            extract_audio(str(tmp_path / "in.mp4"), str(tmp_path / "out.wav"))


def test_extract_audio_raises_on_nonzero_exit(tmp_path):
    with patch("script.media._find_ffmpeg", return_value="ffmpeg"), \
         patch("script.media.subprocess.run") as run:
        run.return_value.returncode = 1
        run.return_value.stderr = "boom"
        with pytest.raises(FFmpegFailedError, match="boom"):
            extract_audio(str(tmp_path / "in.mp4"), str(tmp_path / "out.wav"))


def test_find_ffmpeg_prefers_path_then_venv(tmp_path):
    # PATH hit returns immediately
    with patch("script.media.shutil.which", return_value="/sys/ffmpeg"):
        assert _find_ffmpeg() == "/sys/ffmpeg"

    # PATH miss → fall back to <sys.prefix>/Scripts/ffmpeg.exe (Windows venv shape)
    fake_prefix = tmp_path / "venv"
    (fake_prefix / "Scripts").mkdir(parents=True)
    bundled = fake_prefix / "Scripts" / "ffmpeg.exe"
    bundled.write_bytes(b"")
    with patch("script.media.shutil.which", return_value=None), \
         patch("script.media.sys.prefix", str(fake_prefix)), \
         patch("script.media.os.name", "nt"):
        assert _find_ffmpeg() == str(bundled)

    # Both miss → None
    with patch("script.media.shutil.which", return_value=None), \
         patch("script.media.sys.prefix", str(tmp_path / "no_venv")):
        assert _find_ffmpeg() is None
