from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration applicative AlloDocteur API."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AlloDocteur Triage API"
    app_version: str = "3.9.0-render"
    environment: str = Field(default="production", validation_alias="APP_ENV")

    api_key: str | None = Field(default=None, validation_alias="API_KEY")
    kb_path: str = Field(default="data/kb_allodocteur_v3_complete.json", validation_alias="ALLODOCTEUR_KB_PATH")
    enable_request_logs: bool = Field(default=True, validation_alias="ENABLE_REQUEST_LOGS")
    log_dir: str = Field(default="logs", validation_alias="LOG_DIR")
    cors_origins: str = Field(default="*", validation_alias="CORS_ORIGINS")
    max_complaint_chars: int = Field(default=1200, validation_alias="MAX_COMPLAINT_CHARS")

    @property
    def project_root(self) -> Path:
        # app/core/config.py -> project root = parents[2]
        return Path(__file__).resolve().parents[2]

    @property
    def kb_file(self) -> Path:
        p = Path(self.kb_path).expanduser()
        if not p.is_absolute():
            p = self.project_root / p
        return p.resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
