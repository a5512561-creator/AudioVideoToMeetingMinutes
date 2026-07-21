"""Verify minutes_audio.zip before declaring it good: structural pre-check
(clip files present, plausible size, links resolve), and the unzip-verify-
cleanup orchestration (audibility via ffprobe; optional browser E2E)."""
import re
import shutil
import subprocess
import tempfile
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


def _probe_duration(clip_path) -> float:
    """Return the audio stream duration in seconds via ffprobe (0.0 on any
    failure / no audio stream)."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=duration", "-of",
        "default=noprint_wrappers=1:nokey=1", str(clip_path),
    ]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return 0.0
    try:
        return float((cp.stdout or "0").strip())
    except ValueError:
        return 0.0


def verify_zip(zip_path, *, run_browser: bool = True) -> dict:
    """Full verification: pre-check, unzip, ffprobe each clip (duration>0),
    optionally a browser E2E, then delete the temp dir ONLY when all pass.

    Returns a result dict; `temp_dir` is None when cleaned up, or the kept path
    when something failed (so the user can inspect)."""
    zip_path = Path(zip_path)
    pre = prezip_check(zip_path)
    if not pre["ok"]:
        return {"ok": False, "stage": "prezip", **pre, "temp_dir": None}

    temp_dir = Path(tempfile.mkdtemp(prefix="minutes_audio_"))
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(temp_dir)

    clip_files = sorted(p.name for p in temp_dir.glob("clip_*"))
    audible, silent = [], []
    for name in clip_files:
        (audible if _probe_duration(temp_dir / name) > 0 else silent).append(name)

    browser = {"ok": True, "skipped": True}
    if run_browser and not silent:
        from script.audio_e2e_playwright import play_every_clip
        browser = play_every_clip(temp_dir / "email_with_audio.html")

    ok = not silent and browser.get("ok", False)
    if ok:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return {"ok": True, "audible": audible, "silent": [],
                "browser": browser, "temp_dir": None}
    return {"ok": False, "stage": "audible" if silent else "browser",
            "audible": audible, "silent": silent, "browser": browser,
            "temp_dir": str(temp_dir)}
