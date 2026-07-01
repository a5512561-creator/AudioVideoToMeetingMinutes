"""Background progress heartbeat for the LLM stages.

A slow / sluggish LLM endpoint (the on-prem `medium` model in particular)
can make a stage sit silent for minutes, indistinguishable from a hang. The
Heartbeat thread does two things so the user can see the run is alive:

1. A `progress` **log line** on a fixed interval (``interval`` seconds) —
   goes through the logger, so it lands in the run log file and any redirected
   output. This is the durable, greppable record.
2. A **live single-line progress bar** that refreshes in place (carriage
   return) every ``bar_interval`` seconds — only when the output stream is an
   interactive TTY. It shows a spinner so the eye can tell the run is moving
   even while a single LLM call is in flight and the % has not budged.

The % is an approximation — completed-LLM-calls / estimated-total-calls. It
cannot advance *within* a single in-flight call (we get no sub-call token
stream), but the spinner, `stage`, and `elapsed` keep moving so silence never
looks like a crash. Estimate slightly over-counts so the bar under-promises
rather than sticking at 100%.
"""
import sys
import threading
import time

from script.logger import log_kv

# Fancy glyphs when the console encoding supports them, ASCII otherwise so a
# cp950 / legacy Windows console never crashes on a UnicodeEncodeError.
_UNICODE_FILL, _UNICODE_EMPTY = "▓", "░"          # ▓ ░
_UNICODE_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"  # braille spinner
_ASCII_FILL, _ASCII_EMPTY = "#", "-"
_ASCII_FRAMES = "|/-\\"

_BAR_WIDTH = 10


class Heartbeat:
    """Daemon thread that logs pipeline progress and paints a live bar.

    Use start()/stop() around the LLM stages. stop() is idempotent and the
    thread is a daemon, so an unhandled exception in the pipeline can never
    leave it hanging the process. stop() also erases the live bar line so
    whatever prints next starts on a clean line.

    Args:
        interval:     seconds between `progress` *log lines*. 0 disables the
                      heartbeat entirely (no thread, no bar) — the opt-out.
        bar:          True = always draw the live bar, False = never, None =
                      auto (only when ``bar_stream`` is an interactive TTY).
        bar_interval: seconds between live-bar refreshes (finer than
                      ``interval`` so the spinner moves between log lines).
        bar_stream:   stream the bar is painted to (defaults to sys.stderr,
                      matching the logger's StreamHandler). Injectable for tests.
    """

    def __init__(
        self,
        logger,
        *,
        calls_done_fn,
        total_estimate: int,
        interval: int = 60,
        bar: bool | None = None,
        bar_interval: float = 1.0,
        bar_stream=None,
    ):
        self._logger = logger
        self._calls_done_fn = calls_done_fn
        self._total = max(1, total_estimate)
        self._interval = interval
        self._bar_interval = max(0.1, bar_interval)
        self._stage = "starting"
        self._t0 = time.monotonic()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self._stream = bar_stream if bar_stream is not None else sys.stderr
        self._bar_enabled = self._decide_bar(bar)
        self._spin_i = 0
        self._last_len = 0
        if self._bar_enabled and self._encodable(
            _UNICODE_FILL + _UNICODE_EMPTY + _UNICODE_FRAMES
        ):
            self._fill, self._empty, self._frames = (
                _UNICODE_FILL, _UNICODE_EMPTY, _UNICODE_FRAMES,
            )
        else:
            self._fill, self._empty, self._frames = (
                _ASCII_FILL, _ASCII_EMPTY, _ASCII_FRAMES,
            )

    def _decide_bar(self, bar: bool | None) -> bool:
        if bar is not None:
            return bool(bar)
        try:
            return bool(self._stream.isatty())
        except Exception:
            return False

    def _encodable(self, s: str) -> bool:
        enc = getattr(self._stream, "encoding", None) or "utf-8"
        try:
            s.encode(enc)
            return True
        except (UnicodeEncodeError, LookupError):
            return False

    def set_stage(self, stage: str) -> None:
        self._stage = stage

    def _pct(self, done: int) -> int:
        return min(99, int(100 * done / self._total))

    def _emit(self) -> None:
        done = self._calls_done_fn()
        elapsed = int(time.monotonic() - self._t0)
        log_kv(
            self._logger, "INFO", "progress",
            stage=self._stage,
            calls=f"{done}/~{self._total}",
            pct=f"{self._pct(done)}%",
            elapsed=f"{elapsed // 60}m{elapsed % 60:02d}s",
        )

    def _draw_bar(self) -> None:
        if not self._bar_enabled:
            return
        done = self._calls_done_fn()
        pct = self._pct(done)
        elapsed = int(time.monotonic() - self._t0)
        filled = pct * _BAR_WIDTH // 100
        bar = self._fill * filled + self._empty * (_BAR_WIDTH - filled)
        spin = self._frames[self._spin_i % len(self._frames)]
        self._spin_i += 1
        line = (
            f"{self._stage:<14} {bar} {pct:3d}%  "
            f"({done}/~{self._total})  {elapsed // 60}m{elapsed % 60:02d}s {spin}"
        )
        pad = max(0, self._last_len - len(line))
        try:
            self._stream.write("\r" + line + " " * pad)
            self._stream.flush()
        except (UnicodeEncodeError, ValueError, OSError):
            # Stream closed or can't encode — give up on the bar quietly; the
            # periodic log line keeps the run observable.
            self._bar_enabled = False
            return
        self._last_len = len(line)

    def _clear_bar_line(self) -> None:
        if self._bar_enabled and self._last_len:
            try:
                self._stream.write("\r" + " " * self._last_len + "\r")
                self._stream.flush()
            except (ValueError, OSError):
                pass
        self._last_len = 0

    def _run(self) -> None:
        # Tick at the finer of (bar cadence, log cadence) so the live bar
        # refreshes often even though the `progress` log line only fires every
        # `interval` seconds. Event.wait returns True when stop is requested.
        tick = min(self._bar_interval, self._interval)
        last_log = time.monotonic()
        while not self._stop.wait(tick):
            now = time.monotonic()
            if now - last_log >= self._interval:
                self._clear_bar_line()   # keep the log line on its own row
                self._emit()
                last_log = now
            self._draw_bar()

    def start(self) -> "Heartbeat":
        if self._interval and self._interval > 0:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self._clear_bar_line()

    def __enter__(self) -> "Heartbeat":
        return self.start()

    def __exit__(self, *exc) -> bool:
        self.stop()
        return False
