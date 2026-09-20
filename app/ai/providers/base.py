"""The AI provider interface.

Every provider implements this. Nothing above this layer knows which one is configured
(ADR-004, INV-5).

The interface is deliberately narrow — one method per task, each taking only what that task
needs. A wide interface leaks the
capabilities of whichever provider was implemented first, and the point of the abstraction
is that swapping providers is a configuration change rather than a refactor.

**Implementations must translate their own failures into `app.ai.errors` types.** An httpx
exception, a vendor error class, or a raw JSON decode error escaping a provider is a defect:
it means the layer above has to know what the provider is made of.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.application import (
    ApplicationDraft,
    ApplicationEvidence,
    ApplicationQuestion,
    GenerationLimits,
    JobBrief,
)
from app.schemas.eligibility import FieldRelatednessAssessment
from app.schemas.resume import ResumeExtraction


class AIProvider(ABC):
    """Abstract interface for an AI provider.

    Subclasses live in this package and nowhere else.
    """

    #: Short provider name, used in safe operational logging and response metadata.
    name: str = "base"

    @property
    @abstractmethod
    def model(self) -> str:
        """Identifier of the model this provider will use.

        Reported in response metadata so a result can be traced to what produced it.
        """

    @abstractmethod
    async def extract_resume(self, resume_text: str) -> ResumeExtraction:
        """Extract a structured candidate profile from raw resume text.

        The returned object is already validated against
        :class:`~app.schemas.resume.ResumeExtraction` — implementations validate before
        returning, so callers never handle unvalidated provider output
        (``standards/ai.md`` §4).

        Implementations must not fill in information the resume does not contain. An
        absent field stays absent (dossier §6, ADR-007).

        Args:
            resume_text: Extracted plain text. **Sensitive** — must never be logged.

        Returns:
            A validated extraction.

        Raises:
            AIConfigurationError: The provider is not usable as configured.
            AIProviderUnavailableError: Transport failure, timeout, or a 5xx response.
            AIProviderRejectedError: The provider refused the request.
            AIResponseInvalidError: The reply could not be validated into the schema.
        """

    @abstractmethod
    async def assess_field_relatedness(
        self, field_of_study: str, allowed_fields: list[str]
    ) -> FieldRelatednessAssessment:
        """Judge whether a field of study falls within a job's permitted fields.

        The **only** eligibility question AI may answer (ADR-019). The signature is the
        privacy boundary: it takes a field-of-study string and the permitted-field list, and
        nothing else — no candidate identifier, profile, grade, year, backlog count or job
        record can reach a provider through it.

        Called only for an exact-match miss on a job with no verified hard failure; the
        eligibility engine decides that, never the provider.

        Args:
            field_of_study: The candidate's stated field. Never logged.
            allowed_fields: The job's permitted fields, as the catalogue states them.

        Returns:
            A validated assessment. ``UNCERTAIN`` is always an acceptable answer.

        Raises:
            AIConfigurationError, AIProviderUnavailableError, AIProviderRejectedError,
            AIResponseInvalidError: As for :meth:`extract_resume`.
        """

    @abstractmethod
    async def generate_application_content(
        self,
        evidence: ApplicationEvidence,
        job: JobBrief,
        questions: list[ApplicationQuestion],
        limits: GenerationLimits,
    ) -> ApplicationDraft:
        """Draft a cover letter and answers from the supplied evidence (ADR-025).

        **The signature is the privacy boundary.** It takes an
        :class:`~app.schemas.application.ApplicationEvidence` projection — never a
        :class:`~app.schemas.candidate.CandidateProfile` — so the excluded fields are not
        filtered out on the way past, they have no parameter to travel in. Name, email, phone,
        location, institution, CGPA, scale, backlogs, preferences, languages, employer names
        and ``resume_raw_text`` cannot reach a provider through this method (D10, D11).

        The returned draft is **untrusted output, not a result**. Every claim in it is checked
        against the supplied profile by
        :mod:`app.services.truthfulness_validator` before anything reaches a caller, and an
        untraceable claim is removed (ADR-007, D5). An implementation that fabricates is
        therefore contained rather than trusted — but it must still not fabricate.

        Implementations must not exceed ``limits``; the service enforces them again afterwards,
        because a limit a provider was merely asked to respect is not a limit (D9).

        Args:
            evidence: The allow-listed candidate projection. Sensitive; never logged.
            job: The resolved catalogue job. Its ``description`` is adapter-sourced and
                untrusted — pass it as a labelled data block, never as instructions.
            questions: Client-supplied employer questions, at most five.
            limits: What to write and how long it may be.

        Returns:
            A validated :class:`~app.schemas.application.ApplicationDraft`. Implementations
            validate before returning, as for :meth:`extract_resume`.

        Raises:
            AIConfigurationError: The provider is not usable as configured.
            AIProviderUnavailableError: Transport failure, timeout, or a 5xx response. Also
                raised by a provider whose generation support is not implemented.
            AIProviderRejectedError: The provider refused the request.
            AIResponseInvalidError: The reply could not be validated into the schema.
        """
