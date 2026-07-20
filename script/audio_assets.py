"""Sibling-audio discovery + timestamp→clip-start math for minutes.html ▶.

The transcript's MM:SS markers come from recorder.google.com and are true
offsets into the original recording, so a sibling audio file (same folder,
same stem) can be located deterministically — no ASR/diarization involved.

Since v2 (2026-05-20) the pipeline pre-cuts one short clip per ▶ via ffmpeg
(``cut_clips()``). This sidesteps HTML5 ``currentTime`` seek, which relies on
HTTP Range requests that SharePoint/Outlook do not serve reliably for
user-uploaded ``.m4a``.
"""
import base64
import subprocess
from pathlib import Path

_AUDIO_EXTS = (".m4a", ".mp3", ".wav", ".ogg", ".aac")

# Video containers we can pull an audio track out of. Teams / Zoom exports are
# .mp4; kept separate from _AUDIO_EXTS because these need an ffmpeg extraction
# (``extract_audio_track``), not a plain copy — copying a multi-hundred-MB
# recording just to cut a few audio clips wastes space, and the clip player
# only ever needs the audio.
_VIDEO_EXTS = (".mp4", ".mov", ".mkv")

_MIME_BY_EXT = {
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
}


def mime_for_ext(ext: str) -> str:
    """Return the audio MIME type for a file extension (lowercased)."""
    return _MIME_BY_EXT.get(ext.lower(), "audio/mp4")


def file_to_data_url(path) -> str:
    """Read a small audio file and return its ``data:<mime>;base64,...`` URL.

    Used to inline per-clip audio into the synthesized HTML so the file
    survives upload to viewers (OneDrive / SharePoint / Outlook) whose
    iframed renderers resolve relative URLs against the viewer's domain,
    not the user's folder — making external clip files unreachable from
    the rendered HTML. Inlining sidesteps that entirely.
    """
    path = Path(path)
    mime = mime_for_ext(path.suffix)
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def find_sibling_audio(src: str) -> Path | None:
    """Return the same-stem audio file next to `src`, trying extensions in
    a fixed preference order; None if none exists."""
    p = Path(src)
    for ext in _AUDIO_EXTS:
        cand = p.with_suffix(ext)
        if cand.exists():
            return cand
    return None


def is_video_container(path) -> bool:
    """True when ``path`` has a video-container extension we can extract audio
    from (case-insensitive)."""
    return Path(path).suffix.lower() in _VIDEO_EXTS


def find_sibling_media(src: str) -> Path | None:
    """Return the same-stem media file next to ``src``: a playable audio file
    if present, otherwise a video container we can extract audio from.

    Audio is preferred over video (audio needs only a copy; video needs an
    ffmpeg extraction), and within each group the fixed extension order wins.
    None if neither exists.
    """
    p = Path(src)
    for ext in (*_AUDIO_EXTS, *_VIDEO_EXTS):
        cand = p.with_suffix(ext)
        if cand.exists():
            return cand
    return None


def extract_audio_track(video_path, dst) -> bool:
    """Extract the audio track from a video container into ``dst`` (an .m4a).

    Tries a stream copy first (``-vn -c:a copy``): Teams / Zoom .mp4 audio is
    already AAC, so this is lossless, near-instant, and avoids rewriting the
    (large) video. Falls back to a re-encode (``-c:a aac``) when the source
    codec is not MP4-compatible. Returns True on success, False on failure or
    when ffmpeg is missing from PATH.
    """
    video_path = Path(video_path)
    dst = Path(dst)

    # ffmpeg can exit rc=0 having written only the m4a container header (~44
    # bytes, no audio) — the same failure mode cut_clips guards against. Treat
    # anything that small as a failed copy so the re-encode fallback runs.
    _MIN_REAL_AUDIO_BYTES = 1024

    def _run(codec_args) -> bool:
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(video_path),
            "-vn", *codec_args, "-map", "0:a:0",
            str(dst),
        ]
        try:
            cp = subprocess.run(cmd, capture_output=True, timeout=300)
        except FileNotFoundError:
            raise
        except (subprocess.TimeoutExpired, OSError):
            return False
        return (
            cp.returncode == 0
            and dst.exists()
            and dst.stat().st_size >= _MIN_REAL_AUDIO_BYTES
        )

    try:
        return _run(["-c:a", "copy"]) or _run(["-c:a", "aac", "-b:a", "128k"])
    except FileNotFoundError:
        return False


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


def output_audio(out_dir) -> Path | None:
    """Return out_dir/audio.<ext> for the first matching audio extension
    (same preference order as find_sibling_audio), else None."""
    base = Path(out_dir)
    for ext in _AUDIO_EXTS:
        cand = base / ("audio" + ext)
        if cand.exists():
            return cand
    return None


def cut_clips(
    audio_path,
    starts,
    duration: int,
    out_dir,
) -> dict[int, str]:
    """Cut one short clip per unique start-second from ``audio_path``.

    Each clip is written to ``out_dir/clip_<start>.<ext>`` via
    ``ffmpeg -ss <s> -i ... -map 0:a:0 -t <duration>`` (re-encode to the
    container's default codec). ``-c copy`` is **not** used: it silently
    produces 0-byte files when the requested start does not align with a
    keyframe, while re-encoding is always reliable for well-formed sources.

    Known limitation: HE-AAC sources (Google Recorder's ``.m4a``) exhibit
    intermittent encoder failures at arbitrary seek positions even with
    re-encode — believed to be SBR-state initialization issues during
    seek. Each failed cut is retried once; cuts that fail both times are
    skipped so the rest of the batch still succeeds (best-effort policy).
    For a 30-anchor meeting, expect 1-3 clips to be missing.

    Pre-existing ``clip_*.<ext>`` files in ``out_dir`` are removed first so
    settings changes cannot leave stale-length clips behind.

    Returns ``{start_second: clip_filename}``. Returns ``{}`` only when
    ffmpeg is missing from PATH (``FileNotFoundError``).
    """
    audio_path = Path(audio_path)
    out_dir = Path(out_dir)
    ext = audio_path.suffix.lower()

    for old in out_dir.glob(f"clip_*{ext}"):
        try:
            old.unlink()
        except OSError:
            pass

    # HE-AAC seek failures sometimes produce a "successful" rc=0 file that
    # contains only the m4a container header (~44 bytes) and no audio. The
    # naive ``st_size > 0`` check accepted these silently and a base64 of
    # the empty file rendered as a non-playing ▶. Real cuts at 48 kbps mono
    # are 6 KB/sec — any minimum-length real clip is well above 1 KB.
    _MIN_REAL_CLIP_BYTES = 1024

    def _attempt(s: int, dst: Path) -> bool:
        # Mono 48 kbps: matches HE-AAC source perceptual quality for speech
        # and cuts the inlined-base64 HTML to ~1/3 of the ffmpeg default.
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(s), "-i", str(audio_path),
            "-map", "0:a:0", "-t", str(int(duration)),
            "-ac", "1", "-b:a", "48k",
            str(dst),
        ]
        try:
            cp = subprocess.run(cmd, capture_output=True, timeout=30)
        except FileNotFoundError:
            raise
        except (subprocess.TimeoutExpired, OSError):
            return False
        return (
            cp.returncode == 0
            and dst.exists()
            and dst.stat().st_size >= _MIN_REAL_CLIP_BYTES
        )

    unique = sorted({int(s) for s in starts if s is not None})
    result: dict[int, str] = {}
    for s in unique:
        name = f"clip_{s}{ext}"
        dst = out_dir / name
        try:
            ok = _attempt(s, dst) or _attempt(s, dst)
        except FileNotFoundError:
            return {}
        if ok:
            result[s] = name
        elif dst.exists():
            try:
                dst.unlink()
            except OSError:
                pass
    return result
