import logging
import os
import re
from datetime import datetime
from pathlib import Path

# Windows-illegal filename chars + whitespace → underscore. CJK is valid on
# NTFS so we keep it; only the truly unsafe set is replaced.
_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\s]+')


def _safe_label(label: str) -> str:
    """Turn a meeting/run name into a filename-safe postfix (trimmed to 60)."""
    cleaned = _UNSAFE_FILENAME.sub("_", label).strip("_")
    return cleaned[:60]


def setup_logger(
    name: str,
    log_dir: str | None,
    level: str = "INFO",
    run_label: str | None = None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level))
    logger.handlers.clear()

    fmt = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        # Meeting name as a postfix so logs are identifiable at a glance:
        # run_20260526-144430_I2S_FPGA_20260526.log
        label = _safe_label(run_label) if run_label else ""
        fname = f"run_{ts}_{label}.log" if label else f"run_{ts}.log"
        fh = logging.FileHandler(
            os.path.join(log_dir, fname), encoding="utf-8"
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


def log_kv(logger: logging.Logger, level: str, event: str, **kv) -> None:
    """Emit a structured `event k1=v1 k2=v2` log line."""
    parts = [event] + [f"{k}={v}" for k, v in kv.items()]
    logger.log(getattr(logging, level), " ".join(parts))
