"""Provider selection and the single point of AI usage logging.

Two responsibilities, both deliberately centralized:

* **Selection** — turns ``ELIGICORE_AI_PROVIDER`` into a provider instance. Services ask for
  "the AI provider", never for Gemini (ADR-004, INV-5).
* **Usage logging** — one place, so cost and volume are observable without scattering log
  calls through the codebase (``standards/ai.md`` §7).

What gets logged: provider, model, outcome category, duration, input length, and — for the
two operations ADR-026 instruments — token counts and cost. What never gets logged: prompt
text, response content, resume text, or any candidate field (INV-4). Input *length* is a
number and carries no content. For field relatedness not even the assessment's result is
logged — it is a statement about one candidate's eligibility.

**Cost accounting covers ``extract_resume`` and ``assess_field_relatedness`` only.**
``generate_application_content`` is excluded (ADR-026 D8): ADR-025 bars logging any length
that could characterize one candidate's content, and a token count is such a length. The
exclusion is structural rather than conditional — that method is passed no sink, its provider
signature has no parameter for one, and no setting exists that could change either. Its log
line below is unchanged from Week 7.

**No cost record is keyed by a candidate.** ``candidate_id`` appears in no field here, and
nothing is persisted: these are operational log lines, not a ledger (ADR-026 D9).

Accounting is inert. A missing rate, an unreported token count or a malformed usage block
yields ``unknown``, and a defect in this file's arithmetic cannot turn a working AI call into
a failed one (ADR-026 D6).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from app.ai.errors import AIConfigurationError, AIError, AIResponseInvalidError
from app.ai.providers.base import AIProvider
from app.ai.providers.mock import MockAIProvider
from app.ai.usage import UsageSink, cost_micros
from app.config import AIProviderName, Settings, get_settings
from app.schemas.application import (
    ApplicationDraft,
    ApplicationEvidence,
    ApplicationQuestion,
    GenerationLimits,
    JobBrief,
)
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

    ``settings`` supplies the cost rates. It is read lazily, so a service that makes no AI
    call reads no configuration, and an unpriced or unreadable configuration costs the call
    nothing but an ``unknown``.
    """

    def __init__(
        self,
        provider: AIProvider | None = None,
        *,
        builder: Callable[[], AIProvider] | None = None,
        settings: Settings | None = None,
    ) -> None:
        if (provider is None) == (builder is None):
            raise ValueError("AIService needs exactly one of provider or builder.")
        self._provider = provider
        self._builder = builder
        self._build_error: AIError | None = None
        self._settings = settings

    def _accounting(self, provider: AIProvider, sink: UsageSink) -> str:
        """Render one call's token and cost fields, as ``unknown`` wherever unknowable.

        Never raises. Every failure here — an unreadable configuration, an unpriced model, a
        provider that reported nothing — degrades to ``unknown``, because an accounting
        defect must not be able to change the outcome of an AI call that worked (D6).

        Counts and one derived number. No identifier, no content, nothing candidate-specific.
        """
        usage = UsageSink().usage
        cost: int | None = None
        try:
            usage = sink.usage
            settings = self._settings or get_settings()
            rate = settings.cost_rate_for(provider.name, provider.model)
            cost = cost_micros(
                usage,
                rate.prompt_micros_per_1k if rate else None,
                rate.completion_micros_per_1k if rate else None,
            )
        except Exception:  # noqa: BLE001 - accounting is inert by contract (D6)
            logger.debug("ai_usage_accounting outcome=unavailable")

        def shown(value: int | None) -> str:
            return "unknown" if value is None else str(value)

        return (
            f"prompt_tokens={shown(usage.prompt_tokens)} "
            f"completion_tokens={shown(usage.completion_tokens)} "
            f"total_tokens={shown(usage.total_tokens)} "
            f"cost_micros={shown(cost)}"
        )

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
        # One sink per call, never shared and never stored on the provider (ADR-026 D3).
        sink = UsageSink()
        try:
            result = await provider.extract_resume(resume_text, usage=sink)
        except AIError as exc:
            # Logged on the failure path too: a reply that arrived and then failed
            # validation still consumed tokens, and unreported cost is hidden cost.
            logger.warning(
                "ai_call provider=%s model=%s operation=extract_resume outcome=error "
                "error_type=%s input_chars=%d %s duration_ms=%.1f",
                provider.name,
                provider.model,
                type(exc).__name__,
                len(resume_text),
                self._accounting(provider, sink),
                (time.perf_counter() - started) * 1000,
            )
            raise

        logger.info(
            "ai_call provider=%s model=%s operation=extract_resume outcome=success "
            "input_chars=%d %s duration_ms=%.1f",
            provider.name,
            provider.model,
            len(resume_text),
            self._accounting(provider, sink),
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
        # One sink per call. Relatedness is the concurrent path — eligibility fans these out
        # through asyncio.gather — so a sink that lived on the provider would let two
        # candidates' assessments contaminate each other's totals (ADR-026 D3).
        sink = UsageSink()
        try:
            result = await provider.assess_field_relatedness(
                field_of_study, list(allowed_fields), usage=sink
            )
            if not isinstance(result, FieldRelatednessAssessment):
                raise AIResponseInvalidError(
                    "Provider returned an unvalidated field-relatedness result."
                )
        except AIError as exc:
            logger.warning(
                "ai_call provider=%s model=%s operation=assess_field_relatedness "
                "outcome=error error_type=%s allowed_fields=%d %s duration_ms=%.1f",
                provider.name,
                provider.model,
                type(exc).__name__,
                len(allowed_fields),
                self._accounting(provider, sink),
                (time.perf_counter() - started) * 1000,
            )
            raise

        logger.info(
            "ai_call provider=%s model=%s operation=assess_field_relatedness "
            "outcome=success allowed_fields=%d %s duration_ms=%.1f",
            provider.name,
            provider.model,
            len(allowed_fields),
            self._accounting(provider, sink),
            (time.perf_counter() - started) * 1000,
        )
        return result


    async def generate_application_content(
        self,
        evidence: ApplicationEvidence,
        job: JobBrief,
        questions: list[ApplicationQuestion],
        limits: GenerationLimits,
    ) -> ApplicationDraft:
        """Ask the provider for an application draft, logging only safe metadata.

        Logs provider, model, outcome, the **number** of questions and timing. Never the
        evidence, the job text, a question, the draft, or any length that could characterize
        one candidate's content — counts only (INV-4, ADR-025 § Failure semantics).

        Raises:
            AIError: Construction or provider failure, or a reply that is not a validated
                :class:`~app.schemas.application.ApplicationDraft`.
        """
        started = time.perf_counter()
        provider = self._get_provider()
        try:
            result = await provider.generate_application_content(
                evidence, job, list(questions), limits
            )
            if not isinstance(result, ApplicationDraft):
                raise AIResponseInvalidError(
                    "Provider returned an unvalidated application draft."
                )
        except AIError as exc:
            logger.warning(
                "ai_call provider=%s model=%s operation=generate_application_content "
                "outcome=error error_type=%s questions=%d duration_ms=%.1f",
                provider.name,
                provider.model,
                type(exc).__name__,
                len(questions),
                (time.perf_counter() - started) * 1000,
            )
            raise

        logger.info(
            "ai_call provider=%s model=%s operation=generate_application_content "
            "outcome=success questions=%d duration_ms=%.1f",
            provider.name,
            provider.model,
            len(questions),
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
