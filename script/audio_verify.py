"""Verify minutes_audio.zip before declaring it good: structural pre-check
(clip files present, plausible size, links resolve), and the unzip-verify-
cleanup orchestration (audibility via ffprobe; optional browser E2E)."""
import re
import zipfile
from pathlib import Path

# Real 48kbps-mono clips are ~6 KB/sec; anything under 1 KB is a broken cut.
_MIN_CLIP_BYTES = 1024
# Pull the clip filenames the HTML references out of the CLIPS map.
_CLIP_REF_RE = re.compile(r'"(clip_\d+\.[a-z0-9]+)"')


def prezip_check(zip_path) -> dict:
    """Structural check on the zip: every HTML-referenced clip exists in the
    zip and is a plausible size; no broken links. Returns a result dict."""
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
        html = z.read("email_with_audio.html").decode("utf-8")
        sizes = {i.filename: i.file_size for i in z.infolist()}

    referenced = set(_CLIP_REF_RE.findall(html))
    clip_files = {n for n in names if n.startswith("clip_")}

    missing = sorted(referenced - clip_files)          # link with no file
    too_small = sorted(n for n in clip_files if sizes.get(n, 0) < _MIN_CLIP_BYTES)
    orphan = sorted(clip_files - referenced)           # file no link points to

    ok = not missing and not too_small
    return {
        "ok": ok,
        "clip_count": len(clip_files),
        "missing": missing,
        "too_small": too_small,
        "orphan": orphan,
    }
