import pytest
from pydantic import ValidationError
from script.config import Settings


def test_required_fields_raise_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env present
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
    assert s.whisper_model == "large-v3"
    assert s.enable_diarization is False
    assert s.llm_chunk_tokens == 4000
    assert s.llm_chunk_overlap_ratio == 0.10
    assert s.llm_parallel_map == 3


def test_diarization_requires_hf_token_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_BASE", "https://x.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("ENABLE_DIARIZATION", "true")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError, match="HF_TOKEN"):
        Settings()
