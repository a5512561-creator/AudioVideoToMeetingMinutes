import time
from unittest.mock import MagicMock

from script.progress import Heartbeat


class FakeStream:
    """Minimal stream stand-in: captures writes, fakes isatty()/encoding."""

    def __init__(self, *, isatty=True, encoding="utf-8"):
        self.buf = []
        self._isatty = isatty
        self.encoding = encoding

    def write(self, s):
        if self.encoding:
            s.encode(self.encoding)  # raise like a real stream on bad glyphs
        self.buf.append(s)

    def flush(self):
        pass

    def isatty(self):
        return self._isatty

    @property
    def text(self):
        return "".join(self.buf)


def test_heartbeat_emits_on_interval():
    """With a tiny interval the heartbeat fires at least once and reports the
    current stage, calls-done/estimate, a %, and elapsed time."""
    logger = MagicMock()
    calls = {"n": 0}
    hb = Heartbeat(
        logger,
        calls_done_fn=lambda: calls["n"],
        total_estimate=4,
        interval=1,  # the wait granularity below is generous enough
    )
    # monkeypatch the interval to be sub-second via the private field
    hb._interval = 0.05
    hb.set_stage("minutes:map")
    hb.start()
    calls["n"] = 2
    time.sleep(0.18)  # ~3 ticks
    hb.stop()

    assert logger.log.called
    # Inspect one emitted line: "progress stage=... calls=2/~4 pct=50% elapsed=..."
    line = logger.log.call_args.args[1]
    assert line.startswith("progress ")
    assert "stage=minutes:map" in line
    assert "calls=2/~4" in line
    assert "pct=50%" in line
    assert "elapsed=" in line


def test_heartbeat_disabled_when_interval_zero():
    """interval=0 → no thread, no emissions (opt-out)."""
    logger = MagicMock()
    hb = Heartbeat(logger, calls_done_fn=lambda: 0, total_estimate=4, interval=0)
    hb.start()
    time.sleep(0.05)
    hb.stop()
    assert not logger.log.called


def test_heartbeat_pct_capped_at_99():
    """Even if calls-done meets/exceeds the estimate, % never shows 100 —
    pipeline.done is the real completion signal."""
    logger = MagicMock()
    hb = Heartbeat(logger, calls_done_fn=lambda: 99, total_estimate=4, interval=1)
    hb._interval = 0.05
    hb.start()
    time.sleep(0.12)
    hb.stop()
    line = logger.log.call_args.args[1]
    assert "pct=99%" in line


def test_heartbeat_stop_is_idempotent():
    logger = MagicMock()
    hb = Heartbeat(logger, calls_done_fn=lambda: 0, total_estimate=1, interval=0)
    hb.start()
    hb.stop()
    hb.stop()  # must not raise


def _make_bar_hb(stream, *, done=2, total=4, bar=True):
    """Heartbeat wired for direct _draw_bar() testing (interval=0 → no thread,
    so the render path is exercised deterministically, no timing races)."""
    return Heartbeat(
        MagicMock(),
        calls_done_fn=lambda: done,
        total_estimate=total,
        interval=0,
        bar=bar,
        bar_stream=stream,
    )


def test_live_bar_draws_in_place_on_tty():
    """When enabled the bar paints a carriage-return-prefixed line carrying the
    stage, %, calls, and elapsed — refreshing the same terminal row."""
    stream = FakeStream(isatty=True)
    hb = _make_bar_hb(stream, done=2, total=4)
    hb.set_stage("minutes:map")
    hb._draw_bar()

    assert "\r" in stream.text          # in-place refresh, not newline-scrolling
    assert "minutes:map" in stream.text
    assert "50%" in stream.text
    assert "(2/~4)" in stream.text


def test_live_bar_refreshes_same_row():
    """Repeated draws each start with a carriage return and never emit a
    newline, so the bar stays on one row instead of scrolling."""
    stream = FakeStream(isatty=True)
    hb = _make_bar_hb(stream)
    hb.set_stage("minutes:map")
    hb._draw_bar()
    hb._draw_bar()

    assert stream.text.count("\r") >= 2
    assert "\n" not in stream.text


def test_live_bar_suppressed_when_not_a_tty():
    """auto mode (bar=None): a redirected / non-tty stream gets no bar spam so
    log files stay clean — only the `progress` log line remains."""
    stream = FakeStream(isatty=False)
    hb = _make_bar_hb(stream, bar=None)
    hb._draw_bar()

    assert stream.text == ""


def test_live_bar_falls_back_to_ascii_on_legacy_encoding():
    """A cp950 console can't encode ▓/braille — the bar must degrade to ASCII
    glyphs instead of crashing the run."""
    stream = FakeStream(isatty=True, encoding="cp950")
    hb = _make_bar_hb(stream)
    hb._draw_bar()

    assert "#" in stream.text            # ASCII fill
    assert "▓" not in stream.text
    assert "░" not in stream.text


def test_live_bar_cleared_on_stop():
    """stop() erases the bar row (CR + blanks + CR) so the next console output
    doesn't collide with a half-drawn bar."""
    stream = FakeStream(isatty=True)
    hb = _make_bar_hb(stream)
    hb._draw_bar()
    hb.stop()

    # Last write is the clear sequence: carriage return, only spaces, CR.
    last = stream.buf[-1]
    assert last.startswith("\r") and last.endswith("\r")
    assert set(last.strip("\r")) <= {" "}
