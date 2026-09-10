"""Provider selection and the single point of AI usage logging.

Two responsibilities, both deliberately centralized:

* **Selection** — turns ``ELIGICORE_AI_PROVIDER`` into a provider instance. Services ask for
  "the AI provider", never for Gemini (ADR-004, INV-5).
* **Usage logging** — one place, so cost and volume are observable without scattering log
  calls through the codebase (``standards/ai.md`` §7).

What gets logged: provider, model, outcome category, duration, input length. What never
gets logged: prompt text, response content, resume text, or any candidate field (INV-4).
Input *length* is a number and carries no content.
"""

from __future__ import annotations

import logging
import time

from app.ai.errors import AIConfigurationError, AIError
from app.ai.providers.base import AIProvider
from app.ai.providers.mock import MockAIProvider
from app.config import AIProviderName, Settings, get_settings
from app.schemas.resume import ResumeExtraction

logger = logging.getLogger("eligicore.ai")


def build_provider(settings: Settings | None = None) -> AIProvider:
    """Construct the configured AI provider.

    The Gemini import is deliberately function-local: importing this module must not pull
    in provider-specific code, so a mock-only run (which is every test run and every
    unconfigured checkout) never touches it.

    Raises:
        AIConfigurationError: The configured provider cannot be constructed.
    """
    settings = settings or get_settings()

    if settings.ai_provider is AIProviderName.MOCK:
        return MockAIProvider()

    if settings.ai_provider is AIProviderName.GEMINI:
        from app.ai.providers.gemini import GeminiFlashProvider

        return GeminiFlashProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            api_base=settings.gemini_api_base,
            timeout_seconds=settings.ai_timeout_seconds,
            max_retries=settings.ai_max_retries,
        )

    raise AIConfigurationError(f"Unsupported AI provider: {settings.ai_provider!r}")


class AIService:
    """Thin wrapper over a provider that records safe usage metadata.

    Holds no business logic. It exists so every AI call passes one point where usage can be
    observed and where provider-specific behaviour is already gone.
    """

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def model(self) -> str:
        return self._provider.model

    async def extract_resume(self, resume_text: str) -> ResumeExtraction:
        """Extract a structured profile, logging only safe metadata.

        Args:
            resume_text: Sensitive. Passed straight through; never logged, never retained.

        Raises:
            AIError: Any provider failure, already translated at the provider boundary.
        """
        started = time.perf_counter()
        try:
            result = await self._provider.extract_resume(resume_text)
        except AIError as exc:
            logger.warning(
                "ai_call provider=%s model=%s operation=extract_resume outcome=error "
                "error_type=%s input_chars=%d duration_ms=%.1f",
                self._provider.name,
                self._provider.model,
                type(exc).__name__,
                len(resume_text),
                (time.perf_counter() - started) * 1000,
            )
            raise

        logger.info(
            "ai_call provider=%s model=%s operation=extract_resume outcome=success "
            "input_chars=%d duration_ms=%.1f",
            self._provider.name,
            self._provider.model,
            len(resume_text),
            (time.perf_counter() - started) * 1000,
        )
        return result


def get_ai_service() -> AIService:
    """FastAPI dependency returning the configured AI service.

    Overridden in tests via ``app.dependency_overrides`` so a test can inject a mock with
    specific behaviour without touching global configuration.
    """
    return AIService(build_provider())
