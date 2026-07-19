# P4 — Audio-Clip Zip + E2E Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **⚠️ NEEDS USER SIGN-OFF BEFORE EXECUTION (gate C2).** One design choice is open — the browser-E2E mechanism (Task 4). The recommended approach is written below, but confirm it before executing. Everything else (Tasks 1-3, 5) is settled.

**Goal:** Produce `minutes_audio.zip` (an `email_with_audio.html` + the 10-second clips it references) alongside the P3 outputs, and verify every clip is really playable before declaring the zip good — quick structural check, then a real-browser click-through of every clip, deleting the temp unzip folder only when all pass.

**Architecture:** Reuse the existing `cut_clips()` ffmpeg cutter. Build a self-contained `email_with_audio.html` that references clips by **relative** path (works once unzipped locally). A pure-Python pre-zip check + `ffprobe`-based audibility proxy gate the zip; a browser-automation pass (recommended: Playwright headless Chromium) then loads the unzipped page and plays every clip to confirm real playback. On full pass the temp unzip folder is removed; any failure is reported and the temp kept.

**Tech Stack:** Python 3.11+, stdlib `zipfile`, existing `audio_assets.cut_clips` (ffmpeg), `ffprobe` (ships with ffmpeg), pytest. **New dependency (pending C2 approval): `playwright`** for the browser E2E — see Task 4's decision note.

**Design reference:** `docs/superpowers/specs/2026-07-18-minutes-workflow-design.md` §3 (Layer 3) + §5. Depends on P3 (email content pipeline) and existing `script/audio_assets.py`.

---

## Open decision for C2 review (the browser-E2E mechanism)

Design §7 left the E2E driver open (Claude-in-Chrome / Playwright / headless). This plan RECOMMENDS **Playwright headless Chromium** for Task 4 because it is:
- Repeatable + automatable in pytest/CI (unlike Claude-in-Chrome, which needs the live Claude runtime).
- Able to load a local `file://` HTML, trigger each `<audio>.play()`, and read back `duration` / `currentTime` / `error` to confirm real decode+playback.

Alternatives if you prefer no new dependency:
- **(B) ffprobe-only** (Task 3): verify each clip has an audio stream + `duration>0` and every HTML link maps to a real clip — a strong "playable" proxy without a browser. Skips the literal "click in a browser" step.
- **(C) Claude-in-Chrome manual pass**: the session drives your real Chrome to click each clip. Not automatable; belongs in a manual checklist, not code.

**Recommendation:** ship (B) as the always-on gate (Task 3) AND (A) Playwright as the thorough automated E2E (Task 4), with Task 4 skipping gracefully (clear message) when Playwright isn't installed. Confirm before executing Task 4.

---

## File Structure

- **Create** `script/audio_zip.py` — build the audio zip: cut clips, render `email_with_audio.html` (relative refs), assemble `minutes_audio.zip`. One responsibility: produce the zip artifact.
- **Create** `script/templates/email_with_audio.html.j2` — email content + ▶ buttons referencing `clip_<sec>.<ext>` relatively + tiny play JS.
- **Create** `script/audio_verify.py` — verification: pre-zip structural check, ffprobe audibility, unzip-verify-cleanup orchestration.
- **Create** `script/audio_e2e_playwright.py` — the Playwright browser pass (Task 4; behind an availability guard).
- **Modify** `script/main.py` — add an `audiozip` command.
- **Test** `tests/test_audio_zip.py`, `tests/test_audio_verify.py` (new).

**Reused:** `script/audio_assets.py` (`find_sibling_audio`, `output_audio`, `clip_start`, `cut_clips`), `script/email_writer.py` (email HTML pieces), `script/schemas.py` (`SynthesizedMinutes`).

---

## Task 1: Build the audio zip (clips + relative-ref HTML + zip)

**Files:**
- Create: `script/audio_zip.py`, `script/templates/email_with_audio.html.j2`
- Test: `tests/test_audio_zip.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_audio_zip.py`:

```python
import zipfile
from pathlib import Path

from script.schemas import SynthesizedMinutes, SynthTopic, SynthAction
from script.audio_zip import build_audio_zip


def _synth():
    return SynthesizedMinutes(
        topics=[SynthTopic(title="議題A", summary="s", decisions=["決議一"],
                           source_timestamps=["00:00:30"])],
        action_items=[SynthAction(task="做 X", owner="小王", due="下週五",
                                  priority="high", source_timestamps=["00:01:10"])],
    )


def test_build_audio_zip_packs_html_and_clips(tmp_path, monkeypatch):
    out = tmp_path / "mtg"
    out.mkdir()
    (out / "audio.m4a").write_bytes(b"FAKEAUDIO")

    # Stub the ffmpeg cut: pretend it produced two clip files.
    def _fake_cut(audio, starts, duration, out_dir):
        result = {}
        for s in sorted({int(x) for x in starts if x is not None}):
            name = f"clip_{s}.m4a"
            (Path(out_dir) / name).write_bytes(b"CLIPDATA" * 200)  # > 1KB
            result[s] = name
        return result
    monkeypatch.setattr("script.audio_zip.cut_clips", _fake_cut)

    zip_path = build_audio_zip(_synth(), out, pre_seconds=5, duration=10)

    assert zip_path == out / "minutes_audio.zip"
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        assert "email_with_audio.html" in names
        assert any(n.startswith("clip_") and n.endswith(".m4a") for n in names)
        html = z.read("email_with_audio.html").decode("utf-8")
        # clips referenced RELATIVELY (no data: URL, no absolute path)
        assert "clip_" in html
        assert "data:audio" not in html
        assert "議題A" in html


def test_build_audio_zip_no_audio_returns_none(tmp_path):
    out = tmp_path / "mtg"
    out.mkdir()  # no audio.* present
    assert build_audio_zip(_synth(), out, pre_seconds=5, duration=10) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_audio_zip.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'script.audio_zip'`

- [ ] **Step 3: Write minimal implementation**

Create `script/templates/email_with_audio.html.j2`:

```jinja
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <title>會議記錄（含音檔） — {{ meeting_name }}</title>
  <style>
    body{font-family:"Noto Sans TC","Microsoft JhengHei",Arial,sans-serif;max-width:900px;margin:0 auto;padding:16px;color:#2d3748}
    h3{margin:14px 0 4px}
    .decisions{color:#0563c1}
    table{width:100%;border-collapse:collapse;margin-top:8px}
    th,td{border:1px solid #e2e8f0;padding:6px 8px;text-align:left}
    .play{border:1px solid #cbd5e0;background:#edf2f7;color:#2b6cb0;border-radius:4px;padding:0 7px;cursor:pointer;margin-left:6px}
  </style>
</head>
<body>
  <h1>會議記錄：{{ meeting_name }}</h1>
  {% for t in topics %}
  <article>
    <h3>{{ t.title }}</h3>
    <p>{{ t.summary }}</p>
    {% if t.decisions %}<div class="decisions"><b>■ 決議</b><ul>
      {% for d in t.decisions %}<li>{{ d }}{% if t.clip %} <button type="button" class="play" data-clip="{{ t.clip }}">▶ 聽</button>{% endif %}</li>{% endfor %}
    </ul></div>{% endif %}
  </article>
  {% endfor %}
  <h2>Action Items</h2>
  <table><tr><th>#</th><th>任務</th><th>負責人</th><th>期限</th><th>聽</th></tr>
  {% for a in actions %}
    <tr><td>{{ a.idx }}</td><td>{{ a.task }}</td><td>{{ a.owner }}</td><td>{{ a.due }}</td>
    <td>{% if a.clip %}<button type="button" class="play" data-clip="{{ a.clip }}">▶ 聽</button>{% endif %}</td></tr>
  {% endfor %}
  </table>
  <audio id="player" preload="none"></audio>
  <script>
    var CLIPS = {{ clips_js|safe }};
    var player = document.getElementById('player');
    document.querySelectorAll('.play').forEach(function(b){
      b.addEventListener('click', function(){
        var f = CLIPS[b.dataset.clip];
        if(!f) return;
        player.src = f;   // relative path to clip_<sec>.<ext>
        player.play();
      });
    });
  </script>
</body>
</html>
```

Create `script/audio_zip.py`:

```python
"""Build minutes_audio.zip: a self-contained email_with_audio.html that
references 10-second clips by RELATIVE path, plus the clip files. Relative
refs work once the zip is unzipped locally (unlike the SharePoint-viewer case
that needs data: URLs).
"""
import json
import zipfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from script.audio_assets import output_audio, clip_start, cut_clips

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _clip_key(timestamps, pre, cut_map):
    if not timestamps:
        return None
    s = clip_start(timestamps[0], pre)
    if s is None or s not in cut_map:
        return None
    return str(s)


def build_audio_zip(synth, out_dir, *, pre_seconds: int, duration: int):
    """Cut clips, render the relative-ref HTML, and zip both. Returns the zip
    Path, or None when no sibling audio is available in out_dir."""
    out_dir = Path(out_dir)
    audio = output_audio(out_dir)
    if audio is None:
        return None

    starts = []
    for t in synth.topics:
        if t.source_timestamps:
            s = clip_start(t.source_timestamps[0], pre_seconds)
            if s is not None:
                starts.append(s)
    for a in synth.action_items:
        if a.source_timestamps:
            s = clip_start(a.source_timestamps[0], pre_seconds)
            if s is not None:
                starts.append(s)

    cut_map = cut_clips(audio, starts, duration, out_dir)  # {start: filename}
    clips_js = {str(s): name for s, name in cut_map.items()}

    topics = [
        {"title": t.title, "summary": t.summary, "decisions": list(t.decisions),
         "clip": _clip_key(t.source_timestamps, pre_seconds, cut_map)}
        for t in synth.topics
    ]
    actions = [
        {"idx": i, "task": a.task, "owner": a.owner, "due": a.due,
         "clip": _clip_key(a.source_timestamps, pre_seconds, cut_map)}
        for i, a in enumerate(synth.action_items, start=1)
    ]

    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)
    html = env.get_template("email_with_audio.html.j2").render(
        meeting_name=out_dir.name, topics=topics, actions=actions,
        clips_js=json.dumps(clips_js, ensure_ascii=True),
    )

    zip_path = out_dir / "minutes_audio.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("email_with_audio.html", html)
        for name in cut_map.values():
            z.write(out_dir / name, arcname=name)
    return zip_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_audio_zip.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```
git add script/audio_zip.py script/templates/email_with_audio.html.j2 tests/test_audio_zip.py
git commit -m "feat: build minutes_audio.zip (relative-ref html + 10s clips)"
```

---

## Task 2: Pre-zip structural check

**Files:**
- Create: `script/audio_verify.py`
- Test: `tests/test_audio_verify.py`

Before trusting the zip, confirm every clip the HTML references actually exists,
is a plausible size, and that there are no orphan clips / broken links.

- [ ] **Step 1: Write the failing test**

Create `tests/test_audio_verify.py`:

```python
import zipfile
from pathlib import Path

from script.audio_verify import prezip_check


def _make_zip(tmp_path, html, clip_names, clip_bytes=b"X" * 2048):
    z = tmp_path / "minutes_audio.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("email_with_audio.html", html)
        for n in clip_names:
            zf.writestr(n, clip_bytes)
    return z


def test_prezip_check_ok(tmp_path):
    html = '<audio></audio><script>var CLIPS={"30":"clip_30.m4a"};</script>'
    z = _make_zip(tmp_path, html, ["clip_30.m4a"])
    r = prezip_check(z)
    assert r["ok"] is True
    assert r["clip_count"] == 1


def test_prezip_check_flags_broken_link(tmp_path):
    # HTML references clip_99 but it is not in the zip
    html = '<script>var CLIPS={"99":"clip_99.m4a"};</script>'
    z = _make_zip(tmp_path, html, ["clip_30.m4a"])
    r = prezip_check(z)
    assert r["ok"] is False
    assert "clip_99.m4a" in r["missing"]


def test_prezip_check_flags_tiny_clip(tmp_path):
    html = '<script>var CLIPS={"30":"clip_30.m4a"};</script>'
    z = _make_zip(tmp_path, html, ["clip_30.m4a"], clip_bytes=b"tiny")
    r = prezip_check(z)
    assert r["ok"] is False
    assert "clip_30.m4a" in r["too_small"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_audio_verify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'script.audio_verify'`

- [ ] **Step 3: Write minimal implementation**

Create `script/audio_verify.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_audio_verify.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```
git add script/audio_verify.py tests/test_audio_verify.py
git commit -m "feat: pre-zip structural check for the audio zip"
```

---

## Task 3: ffprobe audibility + unzip-verify-cleanup

**Files:**
- Modify: `script/audio_verify.py`
- Test: `tests/test_audio_verify.py`

Unzip to a temp dir, confirm each clip has an audio stream with `duration>0`
(an audibility proxy that needs no browser), and delete the temp dir only when
everything passes.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_audio_verify.py`:

```python
def test_verify_and_cleanup_all_pass(tmp_path, monkeypatch):
    from script.audio_verify import verify_zip
    html = '<script>var CLIPS={"30":"clip_30.m4a"};</script>'
    z = _make_zip(tmp_path, html, ["clip_30.m4a"])
    # stub ffprobe: every clip reports 10.0s of audio
    monkeypatch.setattr("script.audio_verify._probe_duration", lambda p: 10.0)

    r = verify_zip(z, run_browser=False)

    assert r["ok"] is True
    assert r["audible"] == ["clip_30.m4a"]
    # temp unzip dir removed on success
    assert r["temp_dir"] is None or not Path(r["temp_dir"]).exists()


def test_verify_keeps_temp_on_silent_clip(tmp_path, monkeypatch):
    from script.audio_verify import verify_zip
    html = '<script>var CLIPS={"30":"clip_30.m4a"};</script>'
    z = _make_zip(tmp_path, html, ["clip_30.m4a"])
    monkeypatch.setattr("script.audio_verify._probe_duration", lambda p: 0.0)  # silent/broken

    r = verify_zip(z, run_browser=False)

    assert r["ok"] is False
    assert "clip_30.m4a" in r["silent"]
    # temp kept for inspection on failure
    assert r["temp_dir"] is not None and Path(r["temp_dir"]).exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_audio_verify.py::test_verify_and_cleanup_all_pass -v`
Expected: FAIL with `ImportError: cannot import name 'verify_zip'`

- [ ] **Step 3: Write minimal implementation**

Add to `script/audio_verify.py`:

```python
import shutil
import subprocess
import tempfile


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_audio_verify.py -v`
Expected: PASS (5 tests; the browser step is not exercised here — `run_browser=False`)

- [ ] **Step 5: Commit**

```
git add script/audio_verify.py tests/test_audio_verify.py
git commit -m "feat: ffprobe audibility + unzip-verify-cleanup for the audio zip"
```

---

## Task 4: Browser E2E (Playwright) — PENDING C2 SIGN-OFF

**Files:**
- Create: `script/audio_e2e_playwright.py`
- Test: `tests/test_audio_verify.py` (guarded)

**Do not start this task until the user confirms the Playwright approach (see the
top decision note).** If they pick ffprobe-only (option B), skip this task and
make `verify_zip`'s default `run_browser=False`.

Load the unzipped `email_with_audio.html` in headless Chromium, click every ▶,
and for each assert the `<audio>` actually played: `duration>0`, no `error`, and
`currentTime` advanced after `play()`.

- [ ] **Step 1: Write the failing test (guarded by availability)**

Add to `tests/test_audio_verify.py`:

```python
import pytest


def _playwright_available():
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _playwright_available(), reason="playwright not installed")
def test_play_every_clip_reports_result(tmp_path):
    from script.audio_e2e_playwright import play_every_clip
    # A page with one .play button and a real (tiny) wav data URL so headless
    # Chromium can actually decode + advance currentTime.
    html = (
        '<button class="play" data-clip="a"></button>'
        '<audio id="player"></audio>'
        '<script>var CLIPS={"a":"data:audio/wav;base64,UklGR... (tiny wav)"};'
        'var p=document.getElementById("player");'
        'document.querySelectorAll(".play").forEach(function(b){'
        'b.addEventListener("click",function(){p.src=CLIPS[b.dataset.clip];p.play();});});'
        '</script>'
    )
    page = tmp_path / "email_with_audio.html"
    page.write_text(html, encoding="utf-8")
    r = play_every_clip(page)
    assert "ok" in r and "played" in r
```

> NOTE for the implementer: the tiny-wav data URL above is a placeholder — before
> running, replace `UklGR... (tiny wav)` with a real minimal base64 WAV (a
> 0.1s silent 8kHz mono WAV is ~", enough for `duration>0`). Generate one with
> `python -c "import base64,io,wave; b=io.BytesIO(); w=wave.open(b,'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b'\x00\x00'*800); w.close(); print(base64.b64encode(b.getvalue()).decode())"`
> and paste the output. This keeps the test hermetic (no external clip file).

- [ ] **Step 2: Run test to verify it fails / skips**

Run: `.venv\Scripts\python.exe -m pytest tests/test_audio_verify.py -k play_every_clip -v`
Expected: SKIP (if playwright absent) or FAIL with `ModuleNotFoundError: script.audio_e2e_playwright`.

- [ ] **Step 3: Write minimal implementation**

First install the dependency (add `playwright` to `requirements.txt`, then):
`.venv\Scripts\python.exe -m pip install playwright` and `.venv\Scripts\python.exe -m playwright install chromium`.

Create `script/audio_e2e_playwright.py`:

```python
"""Real-browser E2E: load email_with_audio.html in headless Chromium, click
every clip, and confirm each actually plays (duration>0, no error,
currentTime advanced). Skips gracefully if Playwright/Chromium is unavailable."""
from pathlib import Path


def play_every_clip(html_path) -> dict:
    """Click every .play button and verify real playback of each clip.

    Returns {"ok": bool, "played": [...], "failed": [...], "skipped": bool}.
    `skipped` is True (with ok=True) when Playwright/Chromium isn't installed —
    the ffprobe audibility gate remains the always-on check."""
    html_path = Path(html_path)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": True, "played": [], "failed": [], "skipped": True}

    played, failed = [], []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(html_path.as_uri())
            buttons = page.query_selector_all(".play")
            for i, btn in enumerate(buttons):
                clip = btn.get_attribute("data-clip") or str(i)
                btn.click()
                # give the audio element a moment to start decoding + advancing
                page.wait_for_timeout(600)
                state = page.evaluate(
                    "() => { const a = document.getElementById('player');"
                    " return {dur: a.duration||0, cur: a.currentTime||0,"
                    " err: !!a.error}; }")
                if (not state["err"] and state["dur"] > 0
                        and state["cur"] > 0):
                    played.append(clip)
                else:
                    failed.append(clip)
            browser.close()
    except Exception as e:  # any Playwright/runtime failure -> report, don't crash
        return {"ok": False, "played": played, "failed": failed,
                "skipped": False, "error": str(e)}

    return {"ok": not failed, "played": played, "failed": failed, "skipped": False}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_audio_verify.py -k play_every_clip -v`
Expected: PASS (with Playwright+Chromium installed) or SKIP (without).

- [ ] **Step 5: Commit**

```
git add script/audio_e2e_playwright.py tests/test_audio_verify.py requirements.txt
git commit -m "feat: Playwright headless E2E — play every clip, confirm real playback"
```

---

## Task 5: `audiozip` CLI command

**Files:**
- Modify: `script/main.py`
- Test: `tests/test_main.py`

Wire building + verifying the zip behind one command:
`python -m script.main audiozip <name>`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_main.py`:

```python
def test_cli_audiozip_builds_and_verifies(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    inter = tmp_path / "out" / "t" / "intermediate"
    inter.mkdir(parents=True)
    from script.schemas import SynthesizedMinutes, SynthTopic
    (inter / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="A", summary="s")]).model_dump_json(),
        encoding="utf-8")
    calls = {}
    monkeypatch.setattr("script.audio_zip.build_audio_zip",
                        lambda synth, out, **k: calls.setdefault("zip", tmp_path / "z.zip"))
    monkeypatch.setattr("script.audio_verify.verify_zip",
                        lambda z, **k: {"ok": True, "audible": [], "silent": [], "temp_dir": None})
    runner = CliRunner()
    result = runner.invoke(app, ["audiozip", "t"])
    assert result.exit_code == 0, result.output
    assert "zip" in calls


def test_cli_audiozip_missing_synth_errors(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["audiozip", "nope"])
    assert result.exit_code != 0
    assert "synthesized.json" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main.py::test_cli_audiozip_builds_and_verifies -v`
Expected: FAIL (no `audiozip` command)

- [ ] **Step 3: Write minimal implementation**

In `script/main.py`, add after the `edit` command:

```python
@app.command()
def audiozip(
    src: str = typer.Argument(..., help="Output folder name (or transcript path) under out/."),
    name: str | None = typer.Option(None, "--name"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Skip the Playwright browser E2E (ffprobe check only)."),
) -> None:
    """Build minutes_audio.zip (clips + relative-ref HTML) and verify every clip plays."""
    from script.audio_zip import build_audio_zip
    from script.audio_verify import verify_zip
    from script.schemas import SynthesizedMinutes
    settings = Settings()
    base = name or Path(src).stem
    out_dir = Path(settings.out_dir) / base
    synth_path = out_dir / "intermediate" / "synthesized.json"
    if not synth_path.exists():
        typer.echo(f"找不到 {synth_path} — 請先跑 process 產生綜整結果。")
        raise typer.Exit(code=1)
    synth = SynthesizedMinutes.model_validate_json(synth_path.read_text(encoding="utf-8"))
    zip_path = build_audio_zip(
        synth, out_dir,
        pre_seconds=settings.audio_clip_pre_seconds,
        duration=settings.audio_clip_duration_seconds)
    if zip_path is None:
        typer.echo("此會議資料夾沒有同名音檔，無法產生音檔 zip。")
        raise typer.Exit(code=1)
    result = verify_zip(zip_path, run_browser=not no_browser)
    if result["ok"]:
        typer.echo(f"✅ {zip_path} 已產生並通過驗證（每條音檔可播放）。")
    else:
        typer.echo(f"❌ 音檔 zip 驗證未過（stage={result.get('stage')}）："
                   f"silent={result.get('silent')} 保留暫存={result.get('temp_dir')}")
        raise typer.Exit(code=1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main.py -v`
Expected: PASS (audiozip tests + all existing main tests green)

- [ ] **Step 5: Commit**

```
git add script/main.py tests/test_main.py
git commit -m "feat: add `audiozip` CLI command (build + verify audio zip)"
```

---

## Notes for the Implementer

- **Confirm the Task 4 mechanism (C2) first.** If the user picks ffprobe-only, skip Task 4 and default `verify_zip(run_browser=False)`; the `audiozip --no-browser` flag already supports that.
- **Relative refs, not data URLs.** The zip's HTML references `clip_<sec>.<ext>` relatively — correct because it is unzipped locally before viewing (opposite of the SharePoint-viewer case in `html_writer.py`, which needs data URLs).
- **Delete temp only on full pass.** `verify_zip` removes the unzip temp dir only when every clip is audible AND the browser pass (if run) is green; on any failure it keeps the temp for inspection and reports the path.
- **ffprobe ships with ffmpeg** (already required by `cut_clips`). `_probe_duration` returns 0.0 if ffprobe is missing, which surfaces as a failed (silent) clip rather than a crash.
- **No sampling.** Both the ffprobe pass and the browser pass check EVERY clip, per the design.
- **Windows/venv:** run pytest via `.venv\Scripts\python.exe`; use PowerShell for git (Bash is broken by an RTK hook here).
```
