"""Sibling-audio discovery + timestamp→clip-start math for minutes.html ▶.

The transcript's MM:SS markers come from recorder.google.com and are true
offsets into the original recording, so a sibling audio file (same folder,
same stem) can be seeked directly — no ASR/diarization involved.
"""
from pathlib import Path

_AUDIO_EXTS = (".m4a", ".mp3", ".wav", ".ogg", ".aac")


def find_sibling_audio(src: str) -> Path | None:
    """Return the same-stem audio file next to `src`, trying extensions in
    a fixed preference order; None if none exists."""
    p = Path(src)
    for ext in _AUDIO_EXTS:
        cand = p.with_suffix(ext)
        if cand.exists():
            return cand
    return None


def clip_start(ts: str, pre: int) -> int | None:
    """`HH:MM:SS` / `MM:SS` / `SS` → start second = max(0, total - pre).

    Returns None when the timestamp cannot be parsed.
    """
    parts = (ts or "").strip().split(":")
    if not 1 <= len(parts) <= 3:
        return None
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        total = nums[0] * 3600 + nums[1] * 60 + nums[2]
    elif len(nums) == 2:
        total = nums[0] * 60 + nums[1]
    else:
        total = nums[0]
    return max(0, total - pre)
