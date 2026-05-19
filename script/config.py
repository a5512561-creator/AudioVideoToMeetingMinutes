from pydantic import Field
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

    # === Audio clip (minutes.html ▶) ===
    audio_clip_pre_seconds: int = Field(5, alias="AUDIO_CLIP_PRE_SECONDS")
    audio_clip_duration_seconds: int = Field(10, alias="AUDIO_CLIP_DURATION_SECONDS")

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
