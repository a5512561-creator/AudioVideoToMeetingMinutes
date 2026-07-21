from pathlib import Path
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
        result = runner.invoke(app, ["process", "transcript.txt", "--name", "test", "--force", "--llm", "company"])
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
            app, ["process", "transcript.txt", "--name", "t", "--model", "claude-opus-4-7", "--llm", "company"]
        )
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["settings"].openai_model == "claude-opus-4-7"


def test_cli_no_model_keeps_env_default(monkeypatch, tmp_path):
    """Without --model, settings.openai_model stays the .env value."""
    _env(monkeypatch, tmp_path)  # OPENAI_MODEL="m"
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(app, ["process", "transcript.txt", "--name", "t", "--llm", "company"])
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["settings"].openai_model == "m"


def test_cli_process_requires_llm_choice(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline"):
        result = runner.invoke(app, ["process", "transcript.txt", "--name", "t"])
    # no --llm on a full run -> refuse
    assert result.exit_code == 2
    assert "--llm" in result.output


def test_cli_process_company_proceeds(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(
            app, ["process", "transcript.txt", "--name", "t", "--llm", "company"])
    assert result.exit_code == 0, result.output
    run.assert_called_once()


def test_cli_process_claude_refuses_fullrun(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(
            app, ["process", "transcript.txt", "--name", "t", "--llm", "claude"])
    assert result.exit_code == 2
    assert "rerender" in result.output.lower() or "engine" in result.output.lower()
    run.assert_not_called()


def test_cli_rerender_exempt_from_llm_choice(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_pipeline") as run:
        result = runner.invoke(
            app, ["process", "transcript.txt", "--name", "t", "--rerender"])
    # --rerender calls no LLM -> allowed without --llm
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["rerender_only"] is True


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
    src = tmp_path / "mtg.txt"
    src.write_text("00:00 hi\n00:10 bye\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 0, result.output
    assert "OK" in result.output
    assert "NOT OK" not in result.output
    # metadata only — no transcript text echoed
    assert "hi" not in result.output


def test_cli_validate_bad_exits_nonzero(monkeypatch, tmp_path):
    src = tmp_path / "flat.txt"
    src.write_text("沒有時間戳\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code != 0
    assert "時間戳" in result.output


def test_cli_edit_calls_serve(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    inter = tmp_path / "out" / "t" / "intermediate"
    inter.mkdir(parents=True)
    (inter / "synthesized.json").write_text("{}", encoding="utf-8")
    seen = {}
    monkeypatch.setattr("script.edit_server.serve",
                        lambda o, **k: seen.update(o=str(o), k=k))
    runner = CliRunner()
    result = runner.invoke(app, ["edit", "t", "--no-browser"])
    assert result.exit_code == 0, result.output
    assert seen["o"].replace("\\", "/").endswith("out/t")
    assert seen["k"]["open_browser"] is False


def test_cli_edit_missing_synth_errors(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["edit", "nope"])
    assert result.exit_code != 0
    assert "synthesized.json" in result.output


def test_cli_audiozip_builds_verifies_and_colocates(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    from script.schemas import SynthesizedMinutes, SynthTopic
    # transcript sits in its own folder; outputs must land next to it
    mtg = tmp_path / "src" / "MeetingX"
    mtg.mkdir(parents=True)
    transcript = mtg / "MeetingX.vtt"
    transcript.write_text("WEBVTT", encoding="utf-8")
    inter = tmp_path / "out" / "MeetingX" / "intermediate"
    inter.mkdir(parents=True)
    (inter / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="A", summary="s")]).model_dump_json(),
        encoding="utf-8")

    def _fake_build(synth, out, **k):
        (Path(out) / "minutes_audio.zip").write_bytes(b"ZIP")
        return Path(out) / "minutes_audio.zip"
    monkeypatch.setattr("script.audio_zip.build_audio_zip", _fake_build)
    monkeypatch.setattr("script.audio_verify.verify_zip",
                        lambda z, **k: {"ok": True, "audible": ["clip_1.m4a"],
                                        "silent": [], "temp_dir": None})

    runner = CliRunner()
    result = runner.invoke(app, ["audiozip", str(transcript)])
    assert result.exit_code == 0, result.output
    # co-located next to the transcript
    assert (mtg / "email.html").exists()
    assert (mtg / "minutes_audio.zip").read_bytes() == b"ZIP"


def test_cli_audiozip_missing_synth_errors(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["audiozip", "nope"])
    assert result.exit_code != 0
    assert "synthesized.json" in result.output


def test_cli_check_json_ok(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    from script.schemas import MeetingMinutes, ReviewResult, SynthesizedMinutes, SynthTopic
    inter = tmp_path / "out" / "t" / "intermediate"
    inter.mkdir(parents=True)
    (inter / "minutes.json").write_text(MeetingMinutes(conclusions=[], actions=[]).model_dump_json(), encoding="utf-8")
    (inter / "review.json").write_text(ReviewResult(notes=[]).model_dump_json(), encoding="utf-8")
    (inter / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="A", summary="s")]).model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["check-json", "t"])
    assert result.exit_code == 0, result.output
    assert "OK" in result.output


def test_cli_check_json_bad_exits_nonzero(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    inter = tmp_path / "out" / "t" / "intermediate"
    inter.mkdir(parents=True)
    (inter / "minutes.json").write_text("{not json", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["check-json", "t"])
    assert result.exit_code != 0
    assert "minutes" in result.output
