import logging
import os
from datetime import datetime
from pathlib import Path


def setup_logger(name: str, log_dir: str | None, level: str = "INFO") -> logging.Logger:
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
        fh = logging.FileHandler(
            os.path.join(log_dir, f"run_{ts}.log"), encoding="utf-8"
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


def log_kv(logger: logging.Logger, level: str, event: str, **kv) -> None:
    """Emit a structured `event k1=v1 k2=v2` log line."""
    parts = [event] + [f"{k}={v}" for k, v in kv.items()]
    logger.log(getattr(logging, level), " ".join(parts))
