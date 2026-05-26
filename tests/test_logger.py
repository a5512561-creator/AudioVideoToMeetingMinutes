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


def test_log_filename_includes_meeting_label(tmp_path):
    """run_label becomes a filename postfix so logs are identifiable."""
    setup_logger("test_lbl", log_dir=str(tmp_path), run_label="I2S_FPGA_20260526")
    files = [f.name for f in tmp_path.glob("run_*.log")]
    assert len(files) == 1
    assert files[0].endswith("_I2S_FPGA_20260526.log")
    assert re.match(r"run_\d{8}-\d{6}_I2S_FPGA_20260526\.log", files[0])


def test_log_filename_sanitizes_unsafe_label(tmp_path):
    """Spaces / path separators / illegal chars in the label become _."""
    setup_logger("test_lbl2", log_dir=str(tmp_path),
                 run_label='5月18日 下午2-07/leader:sync')
    name = next(tmp_path.glob("run_*.log")).name
    # No filename-illegal chars survive; CJK is kept (valid on NTFS).
    for bad in '<>:"/\\|?* ':
        assert bad not in name.replace(".log", "")
    assert "5月18日" in name


def test_log_filename_no_label_keeps_plain_form(tmp_path):
    setup_logger("test_lbl3", log_dir=str(tmp_path))  # no run_label
    name = next(tmp_path.glob("run_*.log")).name
    assert re.match(r"run_\d{8}-\d{6}\.log", name)
