"""
app/config.py
─────────────
Centralised settings loaded from environment variables.
"""
from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",   # ignore any extra env vars not defined here
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_name: str = "Aegis GRC Platform"
    app_env: Literal["development", "staging", "production"] = "development"
    app_version: str = "0.1.0"
    debug: bool = True
    secret_key: str = "change-me"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://aegis:aegis@localhost:5432/aegis"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ── Auth ──────────────────────────────────────────────────────────────────
    jwt_secret_key: str = "change-me-jwt"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # ── AI ────────────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    claude_model: str = "claude-sonnet-4-6"

    # ── Integrations ──────────────────────────────────────────────────────────
    okta_domain: str = ""
    aws_region: str = "eu-west-1"
    nvd_api_key: str = ""

    # ── Storage ───────────────────────────────────────────────────────────────
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket_name: str = "aegis-evidence"
    s3_region: str = "auto"

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Comma-separated list; "*" means allow all (development default)
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins(self) -> list[str]:
        origins = [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        return origins if origins else ["*"]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
