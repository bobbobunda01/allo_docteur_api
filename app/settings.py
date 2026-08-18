from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / '.env',
        env_file_encoding='utf-8',
        extra='ignore',
        case_sensitive=False,
    )

    app_name: str = 'AlloDocteur V6.4 — Clinical & Epidemiological Safety'
    app_version: str = '6.4.0'
    environment: str = 'development'
    debug: bool = False

    openai_api_key: str = ''
    openai_model: str = 'gpt-5-mini'
    openai_connect_timeout_seconds: float = 5.0
    openai_read_timeout_seconds: float = 30.0
    openai_write_timeout_seconds: float = 10.0
    openai_pool_timeout_seconds: float = 5.0
    openai_max_retries: int = 0
    openai_max_output_tokens: int = 1200
    openai_reasoning_effort: str = 'minimal'
    openai_text_verbosity: str = 'low'
    allodocteur_llm_enabled: bool = True
    default_country: str = 'République démocratique du Congo'
    enable_epidemiological_context: bool = True

    audit_dir: str = str(BASE_DIR / 'runtime' / 'audit')
    log_dir: str = str(BASE_DIR / 'runtime' / 'logs')
    log_level: str = 'INFO'
    log_json: bool = False
    admin_api_token: str = ''
    expose_technical_summary: bool = True
    allowed_hosts: list[str] = ['localhost', '127.0.0.1', 'testserver']
    cors_origins: list[str] = []

    @field_validator('openai_reasoning_effort')
    @classmethod
    def validate_reasoning_effort(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {'none', 'minimal', 'low', 'medium', 'high', 'xhigh'}
        if normalized not in allowed:
            raise ValueError(f'OPENAI_REASONING_EFFORT doit appartenir à {sorted(allowed)}')
        return normalized

    @field_validator('openai_text_verbosity')
    @classmethod
    def validate_text_verbosity(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {'low', 'medium', 'high'}
        if normalized not in allowed:
            raise ValueError(f'OPENAI_TEXT_VERBOSITY doit appartenir à {sorted(allowed)}')
        return normalized


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
