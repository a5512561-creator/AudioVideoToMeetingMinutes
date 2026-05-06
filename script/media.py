import shutil
import subprocess
from pathlib import Path


class FFmpegMissingError(RuntimeError):
    """ffmpeg not found on PATH."""


class FFmpegFailedError(RuntimeError):
    """ffmpeg exited non-zero."""


def extract_audio(src: str, dst: str) -> None:
    """Extract 16kHz mono PCM WAV from an audio/video file."""
    if shutil.which("ffmpeg") is None:
        raise FFmpegMissingError(
            "ffmpeg not found on PATH. Install ffmpeg and add it to PATH."
        )
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i", src,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        dst,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegFailedError(proc.stderr)
