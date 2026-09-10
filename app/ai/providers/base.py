"""The AI provider interface.

Every provider implements this. Nothing above this layer knows which one is configured
(ADR-004, INV-5).

The interface is deliberately narrow — one method, one task. A wide interface leaks the
capabilities of whichever provider was implemented first, and the point of the abstraction
is that swapping providers is a configuration change rather than a refactor.

**Implementations must translate their own failures into `app.ai.errors` types.** An httpx
exception, a vendor error class, or a raw JSON decode error escaping a provider is a defect:
it means the layer above has to know what the provider is made of.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

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
