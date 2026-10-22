from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Voice Notes API"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "sqlite:///./data/app.db"

    max_audio_mb: int = 25
    ffmpeg_bin: str = "ffmpeg"
    ffmpeg_timeout_seconds: int = 60
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str = "en"
    whisper_beam_size: int = 5

    llm_base_url: str = "http://127.0.0.1:8080/v1"
    llm_api_key: str = "local"
    llm_model: str = "qwen3.5-4b"
    llm_timeout_seconds: float = 60.0
    llm_temperature: float = 0.0
    llm_max_tokens: int = 512
    llm_max_attempts: int = 2

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
