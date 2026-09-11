"""Central runtime configuration for Diaglob.

Keep environment parsing here so application bootstrap and infrastructure modules do
not each grow their own ``os.getenv`` conventions. Provider-specific secrets can be
migrated into this object incrementally; this first hardening pass centralizes the
settings that affect process startup and HTTP behavior.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "diaglob.db"
DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:5173,"
    "http://127.0.0.1:5173,"
    "http://localhost:5174,"
    "http://127.0.0.1:5174,"
    "https://diaglob.tech,"
    "https://www.diaglob.tech,"
    "https://app.diaglob.tech"
)


class Settings(BaseSettings):
    """Validated process-level settings.

    ``extra='ignore'`` is intentional: Diaglob has many provider-specific variables
    that have not yet been migrated into this model, and introducing this module must
    not make an existing deployment fail because unrelated environment variables are
    present.
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    database_url: str = Field(
        default=f"sqlite:///{DEFAULT_DB_PATH.as_posix()}",
        validation_alias="DATABASE_URL",
    )
    cors_allowed_origins: str = Field(
        default=DEFAULT_ALLOWED_ORIGINS,
        validation_alias="CORS_ALLOWED_ORIGINS",
    )
    knowledge_reconcile_on_startup: bool = Field(
        default=True,
        validation_alias="KNOWLEDGE_RECONCILE_ON_STARTUP",
    )
    rate_limit_enabled: bool = Field(
        default=True,
        validation_alias="RATE_LIMIT_ENABLED",
    )

    @field_validator("environment")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        normalized = (value or "development").strip().lower()
        aliases = {
            "dev": "development",
            "prod": "production",
        }
        return aliases.get(normalized, normalized)

    @property
    def allowed_origins(self) -> list[str]:
        """Return normalized, de-duplicated origins while preserving order."""
        seen: set[str] = set()
        origins: list[str] = []
        for item in self.cors_allowed_origins.split(","):
            origin = item.strip().rstrip("/")
            if not origin or origin in seen:
                continue
            seen.add(origin)
            origins.append(origin)
        return origins

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one immutable-by-convention settings snapshot per process."""
    return Settings()
