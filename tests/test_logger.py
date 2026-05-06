import logging
import re
from script.logger import setup_logger, log_kv


def test_log_kv_format(caplog):
    logger = setup_logger("test", log_dir=None, level="INFO")
    with caplog.at_level(logging.INFO, logger="test"):
        log_kv(logger, "INFO", "stage.start", file="x.mp4", duration=1.2)
    assert len(caplog.records) == 1
    msg = caplog.records[0].getMessage()
    assert msg == "stage.start file=x.mp4 duration=1.2"


def test_setup_logger_writes_to_file(tmp_path):
    logger = setup_logger("test_file", log_dir=str(tmp_path), level="INFO")
    log_kv(logger, "INFO", "hello", k="v")
    for h in logger.handlers:
        h.flush()
    files = list(tmp_path.glob("run_*.log"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "hello k=v" in content
    assert re.search(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]", content)
