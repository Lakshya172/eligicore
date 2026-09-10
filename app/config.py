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


class AIProviderName(str, Enum):
    """Which AI provider implementation to use.

    Provider selection is configuration, never a code branch in a service
    (``standards/ai.md`` §1). Adding a provider means adding a member here and one class
    under ``app/ai/providers/`` — nothing in the service layer changes (ADR-004).
    """

    MOCK = "mock"
    GEMINI = "gemini"


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

    # --- Resume upload bounds -----------------------------------------------------------
    # Enforced before the file is read into memory (standards/security_privacy.md §4).
    max_resume_bytes: int = Field(default=5 * 1024 * 1024, ge=1024)
    # Guards against a pathological document consuming the AI budget in one request.
    max_resume_characters: int = Field(default=100_000, ge=1000)
    # Below this, extraction is treated as having failed rather than having succeeded
    # with almost nothing — a scanned image PDF typically yields a handful of characters.
    min_resume_characters: int = Field(default=50, ge=0)

    # --- AI provider (ADR-004 abstraction, ADR-013 Phase 1 default) ----------------------
    # Default is MOCK, deliberately: an unconfigured checkout and CI must never be able to
    # make a paid API call by accident.
    ai_provider: AIProviderName = AIProviderName.MOCK
    gemini_api_key: str | None = None
    # Configurable so the model can change without touching source. Not verified against a
    # live API from this environment — confirm before first live use (ADR-013 § Unverified).
    gemini_model: str = "gemini-2.0-flash"
    gemini_api_base: str = "https://generativelanguage.googleapis.com/v1beta"
    ai_timeout_seconds: float = Field(default=30.0, gt=0)
    # An unbounded retry loop against a paid API is a financial bug (standards/ai.md §7).
    ai_max_retries: int = Field(default=2, ge=0, le=5)

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
