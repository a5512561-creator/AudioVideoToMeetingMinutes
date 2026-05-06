import subprocess
from unittest.mock import patch
import pytest
from script.media import extract_audio, FFmpegMissingError, FFmpegFailedError


def test_extract_audio_builds_correct_command(tmp_path):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    dst = tmp_path / "out.wav"

    with patch("script.media.shutil.which", return_value="ffmpeg"), \
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


def test_extract_audio_raises_when_ffmpeg_missing(tmp_path):
    with patch("script.media.shutil.which", return_value=None):
        with pytest.raises(FFmpegMissingError):
            extract_audio(str(tmp_path / "in.mp4"), str(tmp_path / "out.wav"))


def test_extract_audio_raises_on_nonzero_exit(tmp_path):
    with patch("script.media.shutil.which", return_value="ffmpeg"), \
         patch("script.media.subprocess.run") as run:
        run.return_value.returncode = 1
        run.return_value.stderr = "boom"
        with pytest.raises(FFmpegFailedError, match="boom"):
            extract_audio(str(tmp_path / "in.mp4"), str(tmp_path / "out.wav"))
