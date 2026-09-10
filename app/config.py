"""Environment-based application configuration.

All settings are read from environment variables prefixed ``ELIGICORE_`` (dossier §1), or
from a local ``.env`` file. Secrets never appear in source — see
``standards/security_privacy.md`` §5.

Import :func:`get_settings` rather than reading ``os.environ`` elsewhere in the codebase
(``standards/code_quality.md`` §9).
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings, loaded from the environment.

    Every field maps to an ``ELIGICORE_``-prefixed environment variable, so
    ``database_url`` is read from ``ELIGICORE_DATABASE_URL``.
    """

    model_config = SettingsConfigDict(
        env_prefix="ELIGICORE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_name: str = "EligiCore"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False

    api_v1_prefix: str = "/api/v1"

    # Operational database only. Candidate personal data is never stored here (ADR-001,
    # ADR-011, INV-1). SQLite in development, PostgreSQL in production (ADR-009).
    database_url: str = "sqlite:///./eligicore.db"

    # Safe operational logging only: request id, method, path, status, duration.
    # Never candidate payloads, resume contents or PII (INV-4).
    log_level: str = "INFO"

    # Bounds on incoming profile payloads. These cap request size rather than expressing
    # any eligibility rule.
    max_education_entries: int = Field(default=20, ge=1)
    max_experience_entries: int = Field(default=50, ge=1)
    max_skills: int = Field(default=200, ge=1)

    @property
    def is_production(self) -> bool:
        """True when running in the production environment."""
        return self.environment is Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings.

    Cached so configuration is read once per process. Tests that need different settings
    should call ``get_settings.cache_clear()`` or override the FastAPI dependency.
    """
    return Settings()
