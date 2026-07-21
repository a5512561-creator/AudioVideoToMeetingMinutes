"""Real-browser E2E: load email_with_audio.html in headless Chromium, click
every clip, and confirm each actually plays (decodes to a finite duration, no
MediaError, and play() leaves it actively playing / currentTime advancing).
Skips gracefully if Playwright/Chromium is unavailable."""
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
            browser = p.chromium.launch(
                headless=True,
                args=["--autoplay-policy=no-user-gesture-required"])
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
                    " err: !!a.error, paused: a.paused}; }")
                # A real clip decodes to a finite duration with no MediaError and
                # play() leaves the element un-paused. currentTime advancing is the
                # strongest signal, but headless Chromium has no audio sink so it
                # can stall at 0 even while actively playing a valid clip — so we
                # also accept "playing (not paused) with a decoded duration".
                played_ok = (not state["err"] and state["dur"] > 0
                             and (state["cur"] > 0 or not state["paused"]))
                (played if played_ok else failed).append(clip)
            browser.close()
    except Exception as e:  # any Playwright/runtime failure -> report, don't crash
        return {"ok": False, "played": played, "failed": failed,
                "skipped": False, "error": str(e)}

    return {"ok": not failed, "played": played, "failed": failed, "skipped": False}
