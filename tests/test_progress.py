import time
from unittest.mock import MagicMock

from script.progress import Heartbeat


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
