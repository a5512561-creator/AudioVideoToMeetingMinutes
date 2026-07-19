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
        result = runner.invoke(app, ["process", "transcript.txt", "--name", "test", "--force"])
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
        result = runner.invoke(app, ["process", "transcript.txt", "--name", "t", "--rerender"])
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["rerender_only"] is True


def test_cli_rejects_removed_diarize_flag(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline"):
        result = runner.invoke(app, ["process", "transcript.txt", "--diarize"])
    assert result.exit_code != 0


def test_cli_model_override(monkeypatch, tmp_path):
    """--model overrides the .env OPENAI_MODEL for this run only."""
    _env(monkeypatch, tmp_path)  # .env model is "m"
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(
            app, ["process", "transcript.txt", "--name", "t", "--model", "claude-opus-4-7"]
        )
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["settings"].openai_model == "claude-opus-4-7"


def test_cli_no_model_keeps_env_default(monkeypatch, tmp_path):
    """Without --model, settings.openai_model stays the .env value."""
    _env(monkeypatch, tmp_path)  # OPENAI_MODEL="m"
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(app, ["process", "transcript.txt", "--name", "t"])
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["settings"].openai_model == "m"


def test_cli_finalize_resolves_name_and_calls_run(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_finalize") as run:
        result = runner.invoke(app, ["finalize", "transcript.txt", "--name", "t"])
    assert result.exit_code == 0, result.output
    args = run.call_args.args
    kwargs = run.call_args.kwargs
    assert args[0].replace("\\", "/").endswith("out/t")
    assert kwargs["default_subject"] == "transcript"
    assert kwargs["reuse"] is False


def test_cli_finalize_reuse_flag(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_finalize") as run:
        result = runner.invoke(app, ["finalize", "x.txt", "--name", "t", "--reuse"])
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["reuse"] is True


def test_cli_validate_ok(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    src = tmp_path / "mtg.txt"
    src.write_text("00:00 hi\n00:10 bye\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 0, result.output
    assert "OK" in result.output
    # metadata only — no transcript text echoed
    assert "hi" not in result.output


def test_cli_validate_bad_exits_nonzero(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    src = tmp_path / "flat.txt"
    src.write_text("沒有時間戳\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code != 0
    assert "時間戳" in result.output
