"""Provider selection and the single point of AI usage logging.

Two responsibilities, both deliberately centralized:

* **Selection** — turns ``ELIGICORE_AI_PROVIDER`` into a provider instance. Services ask for
  "the AI provider", never for Gemini (ADR-004, INV-5).
* **Usage logging** — one place, so cost and volume are observable without scattering log
  calls through the codebase (``standards/ai.md`` §7).

What gets logged: provider, model, outcome category, duration, input length. What never
gets logged: prompt text, response content, resume text, or any candidate field (INV-4).
Input *length* is a number and carries no content. For field relatedness not even the
assessment's result is logged — it is a statement about one candidate's eligibility.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from app.ai.errors import AIConfigurationError, AIError, AIResponseInvalidError
from app.ai.providers.base import AIProvider
from app.ai.providers.mock import MockAIProvider
from app.config import AIProviderName, Settings, get_settings
from app.schemas.eligibility import FieldRelatednessAssessment
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

    Constructed either with a ready ``provider``, or with a ``builder`` that is called only
    when the first AI call is actually made. The lazy form is what the eligibility endpoint
    uses: a request whose jobs need no AI never constructs a provider at all, and a
    misconfigured provider only matters to a request that genuinely needs one (ADR-019).
    """

    def __init__(
        self,
        provider: AIProvider | None = None,
        *,
        builder: Callable[[], AIProvider] | None = None,
    ) -> None:
        if (provider is None) == (builder is None):
            raise ValueError("AIService needs exactly one of provider or builder.")
        self._provider = provider
        self._builder = builder
        self._build_error: AIError | None = None

    @property
    def provider_built(self) -> bool:
        """True once a provider exists. Stays False for a lazy service that was never used."""
        return self._provider is not None

    def _get_provider(self) -> AIProvider:
        """Return the provider, building it on first use.

        A build failure is remembered, so one misconfigured request does not retry the
        construction once per ambiguous job.

        Raises:
            AIError: The provider could not be constructed.
        """
        if self._provider is not None:
            return self._provider
        if self._build_error is not None:
            raise self._build_error
        assert self._builder is not None  # guaranteed by __init__
        try:
            self._provider = self._builder()
        except AIError as exc:
            self._build_error = exc
            logger.warning("ai_provider_build outcome=error error_type=%s", type(exc).__name__)
            raise
        return self._provider

    @property
    def provider_name(self) -> str:
        return self._get_provider().name

    @property
    def model(self) -> str:
        return self._get_provider().model

    async def extract_resume(self, resume_text: str) -> ResumeExtraction:
        """Extract a structured profile, logging only safe metadata.

        Args:
            resume_text: Sensitive. Passed straight through; never logged, never retained.

        Raises:
            AIError: Any provider failure, already translated at the provider boundary.
        """
        started = time.perf_counter()
        provider = self._get_provider()
        try:
            result = await provider.extract_resume(resume_text)
        except AIError as exc:
            logger.warning(
                "ai_call provider=%s model=%s operation=extract_resume outcome=error "
                "error_type=%s input_chars=%d duration_ms=%.1f",
                provider.name,
                provider.model,
                type(exc).__name__,
                len(resume_text),
                (time.perf_counter() - started) * 1000,
            )
            raise

        logger.info(
            "ai_call provider=%s model=%s operation=extract_resume outcome=success "
            "input_chars=%d duration_ms=%.1f",
            provider.name,
            provider.model,
            len(resume_text),
            (time.perf_counter() - started) * 1000,
        )
        return result

    async def assess_field_relatedness(
        self, field_of_study: str, allowed_fields: list[str]
    ) -> FieldRelatednessAssessment:
        """Ask the provider whether a field of study falls within permitted fields.

        Logs provider, model, outcome, the *number* of permitted fields and timing. Never
        the field, the permitted fields, the prompt, the reply, or the assessment's result.

        Raises:
            AIError: Construction or provider failure, or a reply that is not a validated
                :class:`FieldRelatednessAssessment`.
        """
        started = time.perf_counter()
        provider = self._get_provider()
        try:
            result = await provider.assess_field_relatedness(
                field_of_study, list(allowed_fields)
            )
            if not isinstance(result, FieldRelatednessAssessment):
                raise AIResponseInvalidError(
                    "Provider returned an unvalidated field-relatedness result."
                )
        except AIError as exc:
            logger.warning(
                "ai_call provider=%s model=%s operation=assess_field_relatedness "
                "outcome=error error_type=%s allowed_fields=%d duration_ms=%.1f",
                provider.name,
                provider.model,
                type(exc).__name__,
                len(allowed_fields),
                (time.perf_counter() - started) * 1000,
            )
            raise

        logger.info(
            "ai_call provider=%s model=%s operation=assess_field_relatedness "
            "outcome=success allowed_fields=%d duration_ms=%.1f",
            provider.name,
            provider.model,
            len(allowed_fields),
            (time.perf_counter() - started) * 1000,
        )
        return result


def get_ai_service() -> AIService:
    """FastAPI dependency returning the configured AI service.

    Overridden in tests via ``app.dependency_overrides`` so a test can inject a mock with
    specific behaviour without touching global configuration.
    """
    return AIService(build_provider())


def get_lazy_ai_service() -> AIService:
    """FastAPI dependency returning an AI service that builds its provider on first use.

    For endpoints where most requests need no AI call. Eligibility checks consult AI only
    for an ambiguous field of study on a job with no verified hard failure, so constructing
    a provider up front would be wasted work — and would turn a provider configuration
    problem into a failure for requests that never needed a provider (ADR-019).
    """
    return AIService(builder=build_provider)
