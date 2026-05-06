import os
import shutil
import subprocess
import sys
from pathlib import Path


class FFmpegMissingError(RuntimeError):
    """ffmpeg not found on PATH."""


class FFmpegFailedError(RuntimeError):
    """ffmpeg exited non-zero."""


def _find_ffmpeg() -> str | None:
    """Locate ffmpeg, preferring system PATH then venv-bundled fallbacks."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    # Fallback: bundled inside the active interpreter's bin/Scripts dir.
    # When users invoke `.venv\Scripts\python -m script.main` without activating
    # the venv, sys.prefix points at the venv but PATH doesn't include its bin.
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    for sub in ("Scripts", "bin"):
        candidate = Path(sys.prefix) / sub / exe
        if candidate.is_file():
            return str(candidate)
    return None


def extract_audio(src: str, dst: str) -> None:
    """Extract 16kHz mono PCM WAV from an audio/video file."""
    ffmpeg = _find_ffmpeg()
    if ffmpeg is None:
        raise FFmpegMissingError(
            "ffmpeg not found on PATH or in venv. Install ffmpeg and add it "
            "to PATH, or drop ffmpeg.exe into .venv/Scripts/."
        )
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
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
