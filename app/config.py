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

from pydantic import BaseModel, ConfigDict, Field
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


class ModelCostRate(BaseModel):
    """What one provider's model costs, per 1000 tokens, in micro-units of currency.

    **No rate is shipped in source.** Published provider pricing is a third-party fact that
    changes, and a stale constant in a repository is a wrong number presented as a
    measurement. Rates are supplied by whoever operates the deployment, and a model with no
    configured rate is reported as ``cost_micros=unknown`` rather than as free (ADR-026 D5).

    Integer micro-units, because a cost is an accounting figure and float drift in one is a
    defect (``app.ai.usage.cost_micros``).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_micros_per_1k: int = Field(ge=0)
    completion_micros_per_1k: int = Field(ge=0)


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

    # --- AI cost accounting (ADR-026, dossier §9.2, §10.2) ------------------------------
    # Maps "<provider>:<model>" to its rate, e.g.
    #   ELIGICORE_AI_COST_RATES={"gemini:gemini-2.0-flash":
    #                            {"prompt_micros_per_1k": 75, "completion_micros_per_1k": 300}}
    # Empty by default and deliberately so: an unpriced model logs cost=unknown, which is
    # honest, where a shipped default would be a guess about somebody else's price list.
    # Operational accounting only — never a per-candidate ledger (ADR-026 D9).
    ai_cost_rates: dict[str, ModelCostRate] = Field(default_factory=dict)

    def cost_rate_for(self, provider: str, model: str) -> ModelCostRate | None:
        """The configured rate for one provider and model, or ``None`` when unpriced."""
        return self.ai_cost_rates.get(f"{provider}:{model}")

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
