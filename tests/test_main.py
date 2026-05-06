from unittest.mock import patch
from typer.testing import CliRunner
from script.main import app


def test_cli_passes_basic_args(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("OPENAI_API_BASE", "https://x/v1")
    monkeypatch.setenv("OPENAI_MODEL", "m")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(app, ["meeting.mp4", "--name", "test", "--force"])
    assert result.exit_code == 0, result.output
    args, kwargs = run.call_args
    assert args[0] == "meeting.mp4"
    assert kwargs["name"] == "test"
    assert kwargs["force"] is True
    assert kwargs["skip_transcribe"] is False
    assert kwargs["diarize_override"] is None


def test_cli_diarize_flag_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("OPENAI_API_BASE", "https://x/v1")
    monkeypatch.setenv("OPENAI_MODEL", "m")
    monkeypatch.setenv("HF_TOKEN", "hf_x")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(app, ["meeting.mp4", "--diarize"])
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["diarize_override"] is True
