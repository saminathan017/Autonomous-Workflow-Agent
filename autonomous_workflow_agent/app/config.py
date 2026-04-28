from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── OpenAI ────────────────────────────────────────────────────────────────
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o-mini", alias="OPENAI_MODEL")
    openai_max_tokens: int = Field(2048, alias="OPENAI_MAX_TOKENS")
    openai_timeout_seconds: int = Field(30, alias="OPENAI_TIMEOUT_SECONDS")
    openai_max_calls_per_run: int = Field(50, alias="OPENAI_MAX_CALLS_PER_RUN")
    # Semaphore: max concurrent outbound OpenAI requests (rate-limit protection)
    openai_concurrency_limit: int = Field(5, alias="OPENAI_CONCURRENCY_LIMIT")

    # ── Google OAuth ──────────────────────────────────────────────────────────
    google_client_id: str = Field("", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field("", alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(
        "http://localhost:8001/auth/callback", alias="GOOGLE_REDIRECT_URI"
    )
    google_sheet_id: str = Field("", alias="GOOGLE_SHEET_ID")

    # ── Database (PostgreSQL) ─────────────────────────────────────────────────
    database_url: str = Field(
        "postgresql://postgres:password@localhost:5432/workflow_agent",
        alias="DATABASE_URL",
    )
    db_pool_min: int = Field(2, alias="DB_POOL_MIN")
    db_pool_max: int = Field(10, alias="DB_POOL_MAX")

    # ── Security ──────────────────────────────────────────────────────────────
    # Set this to enforce API key authentication on /api/* routes.
    # Leave empty to disable auth (local dev only).
    api_secret_key: str = Field("", alias="API_SECRET_KEY")
    allowed_origins: str = Field(
        "http://localhost:8001,http://127.0.0.1:8001,http://localhost:8002,http://127.0.0.1:8002",
        alias="ALLOWED_ORIGINS",
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_host: str = Field("0.0.0.0", alias="APP_HOST")
    app_port: int = Field(8001, alias="APP_PORT")
    app_debug: bool = Field(False, alias="APP_DEBUG")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    # ── Redis (pub/sub event bus — multi-process WebSocket support) ───────────
    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")

    # ── Workflow ──────────────────────────────────────────────────────────────
    workflow_max_retries: int = Field(3, alias="WORKFLOW_MAX_RETRIES")
    workflow_retry_delay_seconds: float = Field(2.0, alias="WORKFLOW_RETRY_DELAY_SECONDS")

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


def get_project_root() -> Path:
    return _PROJECT_ROOT


def get_data_dir() -> Path:
    d = _PROJECT_ROOT / "data"
    d.mkdir(exist_ok=True)
    return d


def get_reports_dir() -> Path:
    r = get_data_dir() / "reports"
    r.mkdir(exist_ok=True)
    return r


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
