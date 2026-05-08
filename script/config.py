from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # === Required: company LLM ===
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_api_base: str = Field(..., alias="OPENAI_API_BASE")
    openai_model: str = Field(..., alias="OPENAI_MODEL")

    # === ASR ===
    whisper_model: str = Field("large-v3", alias="WHISPER_MODEL")
    whisper_device: str = Field("auto", alias="WHISPER_DEVICE")
    whisper_compute_type: str = Field("auto", alias="WHISPER_COMPUTE_TYPE")
    whisper_language: str = Field("zh", alias="WHISPER_LANGUAGE")
    whisper_initial_prompt: str = Field(
        "以下是繁體中文會議記錄，可能包含英文技術名詞如 API、Roadmap、Sprint。",
        alias="WHISPER_INITIAL_PROMPT",
    )
    whisper_vad_filter: bool = Field(True, alias="WHISPER_VAD_FILTER")

    # === Diarization (optional) ===
    enable_diarization: bool = Field(False, alias="ENABLE_DIARIZATION")
    hf_token: str = Field("", alias="HF_TOKEN")
    diarization_model: str = Field(
        # pyannote 3.1 (Apache-2.0, free): works with pyannote.audio 3.x.
        # Community-1 (CC-BY-4.0) requires pyannote.audio 4.x which on Windows
        # currently brings dep-hell (torchcodec/k2). Switch to Community-1 once
        # those upstream issues are resolved.
        "pyannote/speaker-diarization-3.1", alias="DIARIZATION_MODEL"
    )
    alignment_model: str = Field(
        "jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn", alias="ALIGNMENT_MODEL"
    )

    # === Transcript Correction (Stage 2.95) ===
    enable_proper_noun_correction: bool = Field(False, alias="ENABLE_PROPER_NOUN_CORRECTION")
    glossary_file: str = Field("script/prompts/glossary.md", alias="GLOSSARY_FILE")

    # === Chunking / LLM ===
    llm_chunk_tokens: int = Field(4000, alias="LLM_CHUNK_TOKENS")
    llm_chunk_overlap_ratio: float = Field(0.10, alias="LLM_CHUNK_OVERLAP_RATIO")
    llm_temperature: float = Field(0.2, alias="LLM_TEMPERATURE")
    llm_max_retries: int = Field(3, alias="LLM_MAX_RETRIES")
    llm_timeout_secs: int = Field(180, alias="LLM_TIMEOUT_SECS")
    llm_parallel_map: int = Field(3, alias="LLM_PARALLEL_MAP")

    # === Pricing (optional; used only for cost estimate display) ===
    # Set to your provider's per-million-tokens rates. Defaults to 0
    # (no cost shown — only token volume reported).
    llm_price_per_1m_input: float = Field(0.0, alias="LLM_PRICE_PER_1M_INPUT")
    llm_price_per_1m_output: float = Field(0.0, alias="LLM_PRICE_PER_1M_OUTPUT")
    llm_currency: str = Field("USD", alias="LLM_CURRENCY")

    # === I/O ===
    out_dir: str = Field("out", alias="OUT_DIR")
    log_dir: str = Field("log", alias="LOG_DIR")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    keep_intermediate: bool = Field(True, alias="KEEP_INTERMEDIATE")

    @model_validator(mode="after")
    def _check_diarization_token(self):
        if self.enable_diarization and not self.hf_token:
            raise ValueError("HF_TOKEN is required when ENABLE_DIARIZATION=true")
        return self
