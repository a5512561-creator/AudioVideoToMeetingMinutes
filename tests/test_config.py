import pytest
from pydantic import ValidationError
from script.config import Settings


def test_required_fields_raise_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError) as exc:
        Settings()
    msg = str(exc.value)
    assert "OPENAI_API_KEY" in msg
    assert "OPENAI_API_BASE" in msg
    assert "OPENAI_MODEL" in msg


def test_defaults_when_only_required_provided(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_BASE", "https://x.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.llm_chunk_tokens == 4000
    assert s.llm_chunk_overlap_ratio == 0.10
    assert s.llm_parallel_map == 3
    assert s.out_dir == "out"


def test_no_audio_settings_remain():
    for attr in (
        "whisper_model", "whisper_device", "enable_diarization",
        "hf_token", "diarization_model", "alignment_model",
    ):
        assert not hasattr(Settings, attr) and attr not in Settings.model_fields


def test_proper_noun_correction_default_false(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_BASE", "https://x.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.enable_proper_noun_correction is False
    assert s.glossary_file == "script/prompts/glossary.md"
