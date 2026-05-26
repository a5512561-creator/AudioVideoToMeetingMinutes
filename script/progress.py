"""Background progress heartbeat for the LLM stages.

A slow / sluggish LLM endpoint (the on-prem `medium` model in particular)
can make a stage sit silent for minutes, indistinguishable from a hang. The
Heartbeat thread emits a `progress` log line on a fixed interval so the user
can see the run is alive, which stage it's in, how many LLM calls have
completed, a rough %, and elapsed time.

The % is an approximation — completed-LLM-calls / estimated-total-calls. It
cannot advance *within* a single in-flight call (we get no sub-call token
stream), but `stage` and `elapsed` keep moving so silence never looks like a
crash. Estimate slightly over-counts so the bar under-promises rather than
sticking at 100%.
"""
import threading
import time

from script.logger import log_kv


class Heartbeat:
    """Daemon thread that logs pipeline progress every `interval` seconds.

    Use start()/stop() around the LLM stages. stop() is idempotent and the
    thread is a daemon, so an unhandled exception in the pipeline can never
    leave it hanging the process.
    """

    def __init__(self, logger, *, calls_done_fn, total_estimate: int, interval: int = 60):
        self._logger = logger
        self._calls_done_fn = calls_done_fn
        self._total = max(1, total_estimate)
        self._interval = interval
        self._stage = "starting"
        self._t0 = time.monotonic()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def set_stage(self, stage: str) -> None:
        self._stage = stage

    def _emit(self) -> None:
        done = self._calls_done_fn()
        pct = min(99, int(100 * done / self._total))
        elapsed = int(time.monotonic() - self._t0)
        log_kv(
            self._logger, "INFO", "progress",
            stage=self._stage,
            calls=f"{done}/~{self._total}",
            pct=f"{pct}%",
            elapsed=f"{elapsed // 60}m{elapsed % 60:02d}s",
        )

    def _run(self) -> None:
        # Event.wait returns True when set (stop requested) → loop ends.
        while not self._stop.wait(self._interval):
            self._emit()

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

    def __enter__(self) -> "Heartbeat":
        return self.start()

    def __exit__(self, *exc) -> bool:
        self.stop()
        return False
