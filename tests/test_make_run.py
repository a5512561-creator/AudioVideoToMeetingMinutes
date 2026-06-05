from unittest.mock import patch, MagicMock

import scripts._make_run as mr


def _run(argv):
    """Invoke _make_run.main with subprocess mocked; return the built cmd."""
    with patch("scripts._make_run.subprocess.run",
               return_value=MagicMock(returncode=0)) as sp:
        rc = mr.main(argv)
    assert rc == 0
    return sp.call_args.args[0]


def test_positional_file_only():
    cmd = _run(["src/m.txt"])
    assert cmd[-4:] == ["-m", "script.main", "process", "src/m.txt"]
    assert "--name" not in cmd
    assert "--model" not in cmd


def test_positional_file_and_name():
    cmd = _run(["src/m.txt", "q2"])
    assert "--name" in cmd and cmd[cmd.index("--name") + 1] == "q2"
    assert "--model" not in cmd


def test_positional_file_name_model():
    cmd = _run(["src/m.txt", "q2", "claude-opus-4-7"])
    assert cmd[cmd.index("--name") + 1] == "q2"
    assert cmd[cmd.index("--model") + 1] == "claude-opus-4-7"


def test_kv_model_form():
    cmd = _run(["src/m.txt", "q2", "MODEL=gpt-latest"])
    assert cmd[cmd.index("--model") + 1] == "gpt-latest"
    # MODEL=... must not be mistaken for a positional name
    assert cmd[cmd.index("--name") + 1] == "q2"


def test_run_prefix_is_skipped():
    """Makefile dispatches with a leading 'run' token; it must be dropped."""
    cmd = _run(["run", "src/m.txt", "q2", "MODEL=fast"])
    assert cmd[cmd.index("script.main") + 1] == "process"
    assert cmd[cmd.index("script.main") + 2] == "src/m.txt"
    assert cmd[cmd.index("--model") + 1] == "fast"


def test_missing_file_returns_error():
    with patch("scripts._make_run.subprocess.run") as sp:
        rc = mr.main([])
    assert rc == 1
    sp.assert_not_called()
