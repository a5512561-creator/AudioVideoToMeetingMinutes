"""Extract a short mp3 sample per speaker so the user can quickly identify
each SPEAKER_XX label when editing speaker_map.json.

The pipeline calls this after diarization to drop one mp3 per detected
speaker into out/<name>/speaker_samples/. The user listens to each, fills
in real names in speaker_map.json, then runs --rerender for the final
output.

Each sample is sourced from the speaker's longest contiguous segment,
centred to the target duration if the longest turn is shorter.
"""
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from script.diarize import SpeakerSegment


def _find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    for sub in ("Scripts", "bin"):
        candidate = Path(sys.prefix) / sub / exe
        if candidate.is_file():
            return str(candidate)
    return None


def extract_speaker_samples(
    *,
    audio_path: str,
    speakers: list[SpeakerSegment],
    out_dir: str,
    target_duration_sec: float = 10.0,
) -> list[str]:
    """Write one mp3 per detected speaker label.

    Returns list of written file paths (empty if ffmpeg missing or no speakers).
    Existing files in out_dir are left alone unless ffmpeg overwrites them with -y.
    """
    if not speakers:
        return []
    ffmpeg = _find_ffmpeg()
    if ffmpeg is None:
        return []
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    by_label: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for seg in speakers:
        by_label[seg.label].append((seg.start, seg.end))

    written: list[str] = []
    for label in sorted(by_label.keys()):
        segs = by_label[label]
        longest = max(segs, key=lambda s: s[1] - s[0])
        start, end = longest
        dur = end - start
        if dur >= target_duration_sec:
            clip_start = start
        else:
            extra = (target_duration_sec - dur) / 2.0
            clip_start = max(0.0, start - extra)
        dst = out / f"{label}.mp3"
        cmd = [
            ffmpeg, "-nostdin", "-y",
            "-ss", f"{clip_start:.2f}",
            "-i", str(audio_path),
            "-t", f"{target_duration_sec:.2f}",
            "-c:a", "libmp3lame", "-q:a", "4",
            str(dst),
        ]
        r = subprocess.run(
            cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL,
        )
        if r.returncode == 0:
            written.append(str(dst))
    return written
