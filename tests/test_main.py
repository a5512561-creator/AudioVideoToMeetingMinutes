from unittest.mock import patch
from typer.testing import CliRunner
from script.main import app


def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("OPENAI_API_BASE", "https://x/v1")
    monkeypatch.setenv("OPENAI_MODEL", "m")
    monkeypatch.chdir(tmp_path)


def test_cli_passes_basic_args(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(app, ["transcript.txt", "--name", "test", "--force"])
    assert result.exit_code == 0, result.output
    args, kwargs = run.call_args
    assert args[0] == "transcript.txt"
    assert kwargs["name"] == "test"
    assert kwargs["force"] is True
    assert kwargs["rerender_only"] is False


def test_cli_rerender_flag(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(app, ["transcript.txt", "--name", "t", "--rerender"])
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["rerender_only"] is True


def test_cli_rejects_removed_diarize_flag(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline"):
        result = runner.invoke(app, ["transcript.txt", "--diarize"])
    assert result.exit_code != 0
