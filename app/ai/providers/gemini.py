"""Google Gemini Flash provider — the Phase 1 concrete implementation (ADR-013).

**This file is the only place in the codebase that knows Gemini exists.** Everything above
it depends on :class:`~app.ai.providers.base.AIProvider` (INV-5). Replacing Gemini means
adding a sibling class and changing ``ELIGICORE_AI_PROVIDER`` — no service, router or
schema changes.

Calls the official Gemini REST API through httpx rather than the ``google-genai`` SDK. The
dossier's approved stack already names httpx for calling AI provider APIs (§9), and adding
an SDK would introduce a dependency outside it. Reasoning and trade-off are recorded in
ADR-013 § Sub-decision.

**Not verified against the live service.** No API key is configured in this environment and
the test suite runs without one, so the request shape follows the documented REST contract
but has not been exercised end to end. See ADR-013 § Unverified.

Privacy: the resume-extraction prompt contains resume text, and its response contains
candidate data. The field-relatedness prompt contains only a field of study and a job's
permitted fields (ADR-019). The job-requirement prompt contains only one job description,
untrusted third-party text passed inside a labelled data block (ADR-030 D25), and never
anything about a candidate (D24). **No prompt or response is ever logged** (INV-4). Logging in
this module is confined to provider name, model, status category and timing. **No request
is stored by Google either:** every body sets ``store: false``, which takes precedence over a
project's own logging setting — and new paid projects store ``generateContent`` requests by
default.

Request configuration follows ADR-030 D15 for ``gemini-3.8-flash``: no sampling parameter
(they are deprecated and ignored), an explicit ``thinkingLevel``, and structured JSON output.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from app.ai.errors import (
    AIConfigurationError,
    AIProviderRejectedError,
    AIProviderUnavailableError,
    AIResponseInvalidError,
)
from app.ai.prompts import load_prompt
from app.ai.providers.base import AIProvider
from app.ai.usage import UsageSink
from app.schemas.application import (
    ApplicationDraft,
    ApplicationEvidence,
    ApplicationQuestion,
    GenerationLimits,
    JobBrief,
)
from app.schemas.candidate import Confidence, GradeScale
from app.schemas.eligibility import FieldRelatednessAssessment, RequirementType
from app.schemas.extraction import (
    DerivedValue,
    ExtractionProposal,
    GradYearWindowValue,
    MaxBacklogsValue,
    MinCgpaValue,
    RequirementStrength,
)
from app.schemas.resume import ResumeExtraction

logger = logging.getLogger("eligicore.ai.gemini")

# Response schema handed to Gemini so it returns structured JSON rather than prose.
# Mirrors ResumeExtraction; the reply is still validated against the Pydantic model on
# arrival, because a declared schema is a request, not a guarantee (standards/ai.md §4).
_CONFIDENCE_ENUM = ["HIGH", "MEDIUM", "LOW"]
_SCALE_ENUM = ["SCALE_4", "SCALE_5", "SCALE_10", "PERCENTAGE", "UNKNOWN"]

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "name": {"type": "STRING", "nullable": True},
        "email": {"type": "STRING", "nullable": True},
        "phone": {"type": "STRING", "nullable": True},
        "location": {"type": "STRING", "nullable": True},
        "education": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "degree": {"type": "STRING", "nullable": True},
                    "field_of_study": {"type": "STRING", "nullable": True},
                    "institution": {"type": "STRING", "nullable": True},
                    "grad_year": {"type": "INTEGER", "nullable": True},
                    "cgpa": {"type": "NUMBER", "nullable": True},
                    "scale": {"type": "STRING", "enum": _SCALE_ENUM},
                },
            },
        },
        "experience": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING", "nullable": True},
                    "company": {"type": "STRING", "nullable": True},
                    "duration": {"type": "STRING", "nullable": True},
                    "description": {"type": "STRING", "nullable": True},
                },
            },
        },
        "skills": {"type": "ARRAY", "items": {"type": "STRING"}},
        "languages": {"type": "ARRAY", "items": {"type": "STRING"}},
        "backlogs": {"type": "INTEGER", "nullable": True},
        "field_confidence": {
            "type": "OBJECT",
            "description": "Field name to confidence.",
            "properties": {
                "name": {"type": "STRING", "enum": _CONFIDENCE_ENUM},
                "email": {"type": "STRING", "enum": _CONFIDENCE_ENUM},
                "phone": {"type": "STRING", "enum": _CONFIDENCE_ENUM},
                "skills": {"type": "STRING", "enum": _CONFIDENCE_ENUM},
            },
        },
    },
}


#: Response schema for field relatedness. Three fields, each constrained; the reply is still
#: validated against FieldRelatednessAssessment on arrival.
_RELATEDNESS_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "result": {"type": "STRING", "enum": ["RELATED", "NOT_RELATED", "UNCERTAIN"]},
        "confidence": {"type": "STRING", "enum": _CONFIDENCE_ENUM},
        "reason": {"type": "STRING"},
    },
    "required": ["result", "confidence", "reason"],
}


#: Response schema for job-requirement extraction (ADR-030 D15). Every string but the evidence
#: is an enum, and there is **no free-form explanatory field**: unrestricted prose is the
#: channel an injected instruction or an unverifiable rationalisation travels through. There is
#: no ``provenance`` either — a model cannot claim ``SOURCE_STATED``, and the provider sets
#: every field that says who produced a proposal.
_JOB_REQUIREMENT_TYPES = ["MIN_CGPA", "GRAD_YEAR_WINDOW", "MAX_BACKLOGS"]
_STRENGTH_ENUM = ["REQUIRED", "PREFERRED", "CONDITIONAL", "INFORMATIONAL"]

_JOB_REQUIREMENTS_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "proposals": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "requirement_type": {"type": "STRING", "enum": _JOB_REQUIREMENT_TYPES},
                    "evidence_text": {"type": "STRING"},
                    "min_cgpa": {"type": "NUMBER", "nullable": True},
                    "min_cgpa_scale": {
                        "type": "STRING",
                        "enum": ["SCALE_4", "SCALE_5", "SCALE_10", "PERCENTAGE"],
                        "nullable": True,
                    },
                    "min_grad_year": {"type": "INTEGER", "nullable": True},
                    "max_grad_year": {"type": "INTEGER", "nullable": True},
                    "max_backlogs": {"type": "INTEGER", "nullable": True},
                    "reported_strength": {
                        "type": "STRING", "enum": _STRENGTH_ENUM, "nullable": True
                    },
                    "reported_confidence": {
                        "type": "STRING", "enum": _CONFIDENCE_ENUM, "nullable": True
                    },
                },
                "required": ["requirement_type", "evidence_text"],
            },
        },
    },
    "required": ["proposals"],
}

#: Who produced a Gemini proposal, recorded with it (ADR-030 D18, D22). Bump the version with
#: any change to the prompt or the schema, so a stale extraction is detectable from stored
#: provenance rather than by bookkeeping.
_JOB_REQUIREMENTS_EXTRACTOR = "gemini.job_requirements"
_JOB_REQUIREMENTS_EXTRACTOR_VERSION = "1"

#: The value fields each requirement type owns. A field belonging to another type must be
#: absent or null: an item mixing them is malformed, not merely over-generous.
_VALUE_FIELDS: dict[str, tuple[str, ...]] = {
    "MIN_CGPA": ("min_cgpa", "min_cgpa_scale"),
    "GRAD_YEAR_WINDOW": ("min_grad_year", "max_grad_year"),
    "MAX_BACKLOGS": ("max_backlogs",),
}

#: The prompt's data-block markers, in any case and spacing. A description that contains one
#: could close the block early and speak outside it, so it is never sent (ADR-030 D25).
_DATA_BLOCK_MARKER = re.compile(r"\b(?:BEGIN|END)\s+JOB\s+DESCRIPTION\b", re.IGNORECASE)


class _WireProposal(BaseModel):
    """One proposal exactly as the reply must carry it. Strict: nothing is coerced.

    ``strict`` refuses ``"7.0"`` for a number, ``true`` for a count and ``2026.0`` for a year;
    ``extra="forbid"`` refuses any key the schema does not name, including ``provenance``
    and ``explanation``. Either refuses the **whole reply** (ADR-030 D26).
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    requirement_type: Literal["MIN_CGPA", "GRAD_YEAR_WINDOW", "MAX_BACKLOGS"]
    evidence_text: str
    min_cgpa: float | None = None
    min_cgpa_scale: Literal["SCALE_4", "SCALE_5", "SCALE_10", "PERCENTAGE"] | None = None
    min_grad_year: int | None = None
    max_grad_year: int | None = None
    max_backlogs: int | None = None
    reported_strength: Literal["REQUIRED", "PREFERRED", "CONDITIONAL", "INFORMATIONAL"] | None = (
        None
    )
    reported_confidence: Literal["HIGH", "MEDIUM", "LOW"] | None = None

    @model_validator(mode="after")
    def _fields_belong_to_the_type(self) -> _WireProposal:
        own = _VALUE_FIELDS[self.requirement_type]
        for kind, fields in _VALUE_FIELDS.items():
            if kind != self.requirement_type and any(
                getattr(self, name) is not None for name in fields
            ):
                raise ValueError("value field of another requirement type")
        if self.requirement_type != "GRAD_YEAR_WINDOW" and any(
            getattr(self, name) is None for name in own
        ):
            # A window may omit a bound; the verifier decides whether it has enough.
            raise ValueError("missing value field")
        return self

    def value(self) -> DerivedValue:
        if self.requirement_type == "MIN_CGPA":
            assert self.min_cgpa is not None and self.min_cgpa_scale is not None
            return MinCgpaValue(
                min_cgpa=self.min_cgpa, min_cgpa_scale=GradeScale(self.min_cgpa_scale)
            )
        if self.requirement_type == "GRAD_YEAR_WINDOW":
            return GradYearWindowValue(
                min_grad_year=self.min_grad_year, max_grad_year=self.max_grad_year
            )
        assert self.max_backlogs is not None
        return MaxBacklogsValue(max_backlogs=self.max_backlogs)


class _WireReply(BaseModel):
    """The whole extraction reply: one ``proposals`` list and nothing else."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    proposals: list[_WireProposal]


#: ``LOW`` for every call. Each is bounded — read fields out of a resume or a posting, or
#: answer one three-valued question — and Google's guidance is that reasoning depth, not
#: sampling, is what controls determinism on this model generation. Set explicitly because Google
#: documents two different defaults for an unset level. ``MINIMAL`` is rejected by
#: ``gemini-3.8-flash``.
_THINKING_LEVEL = "LOW"


def _generate_content_body(text: str, schema: dict[str, Any]) -> dict[str, Any]:
    """The one request body every Gemini call sends, so none can drift from it.

    ``store`` is a top-level request field, not part of ``generationConfig``.
    """
    return {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "thinkingConfig": {"thinkingLevel": _THINKING_LEVEL},
        },
        "store": False,
    }


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _thought_tokens(metadata: dict[str, Any]) -> object:
    """The reply's thinking-token count, ``0`` only where the reply proves it, else ``None``.

    Gemini's JSON omits a count that is zero, so an absent ``thoughtsTokenCount`` is not by
    itself a zero. ``totalTokenCount`` is prompt + tool-use prompt + thoughts + candidates,
    so when every other part is a readable count and they already sum to the total, there
    were no thoughts. Anything less certain is ``None``, which the sink records as unknown
    rather than as a guess (ADR-026 D5). A reported value is passed through untouched; the
    sink rejects it if it is not a count.
    """
    if "thoughtsTokenCount" in metadata:
        return metadata["thoughtsTokenCount"]
    total = metadata.get("totalTokenCount")
    prompt = metadata.get("promptTokenCount")
    candidates = metadata.get("candidatesTokenCount")
    tool_use = metadata.get("toolUsePromptTokenCount", 0)
    if all(_is_count(value) for value in (total, prompt, candidates, tool_use)):
        if total == prompt + candidates + tool_use:  # type: ignore[operator]
            return 0
    return None


def _record_usage(
    sink: UsageSink | None, raw: dict[str, Any], *, tokens_certain: bool
) -> None:
    """Record one reply's token counts into ``sink``, if there are any to read.

    Gemini reports usage in ``usageMetadata``. Provider output is untrusted, so the block is
    read defensively and the sink itself rejects anything that is not a non-negative integer.

    ``tokens_certain`` distinguishes the two kinds of missing metadata, and the distinction
    is load-bearing:

    * **True** — a successful generation. Tokens were certainly spent, so a missing count is
      recorded as **unreadable**: the count being absent is not the same fact as the count
      being nothing (ADR-026 D5).
    * **False** — an error reply. The request may never have been processed, so a missing
      count records **nothing at all**. Marking it unreadable would be worse than the gap it
      closes: one usage-less 429 would turn a later successful attempt's real total into
      ``unknown``.

    Reads counts only. No part of the reply's content is touched, and nothing is logged here
    — ``AIService`` is the single logging point (dossier §9.2).
    """
    if sink is None:
        return

    metadata = raw.get("usageMetadata")
    if not isinstance(metadata, dict):
        if tokens_certain:
            sink.record_unreadable()
        return

    sink.record(
        prompt_tokens=metadata.get("promptTokenCount"),
        completion_tokens=metadata.get("candidatesTokenCount"),
        total_tokens=metadata.get("totalTokenCount"),
        thought_tokens=_thought_tokens(metadata),
    )


def _error_body(response: httpx.Response) -> dict[str, Any]:
    """The JSON object of an error reply, or an empty one.

    An error body is frequently not JSON at all — a proxy's HTML, an empty 503. Nothing here
    may raise: this runs on the way to raising the real error, and must not replace it.
    """
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return {}
    return body if isinstance(body, dict) else {}


class GeminiFlashProvider(AIProvider):
    """Resume extraction, field relatedness and job-requirement proposals via the Gemini API."""

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        api_base: str,
        timeout_seconds: float,
        max_retries: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise AIConfigurationError(
                "Gemini provider selected but ELIGICORE_GEMINI_API_KEY is not set."
            )
        if not model:
            raise AIConfigurationError("ELIGICORE_GEMINI_MODEL must not be empty.")

        self._api_key = api_key
        self._model = model
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._client = client

    @property
    def model(self) -> str:
        return self._model

    async def extract_resume(
        self, resume_text: str, *, usage: UsageSink | None = None
    ) -> ResumeExtraction:
        """Extract a structured profile from resume text."""
        payload = self._build_payload(resume_text)
        raw = await self._post_with_retries(payload, usage)
        return self._parse_response(raw)

    async def assess_field_relatedness(
        self,
        field_of_study: str,
        allowed_fields: list[str],
        *,
        usage: UsageSink | None = None,
    ) -> FieldRelatednessAssessment:
        """Judge whether a field of study falls within a job's permitted fields."""
        payload = self._build_relatedness_payload(field_of_study, allowed_fields)
        raw = await self._post_with_retries(payload, usage)
        data = self._response_object(raw)
        try:
            return FieldRelatednessAssessment.model_validate(data)
        except ValidationError as exc:
            raise AIResponseInvalidError(
                "Gemini relatedness response failed schema validation "
                f"({exc.error_count()} error(s))."
            ) from exc

    async def extract_job_requirements(
        self, description: str, *, usage: UsageSink | None = None
    ) -> list[ExtractionProposal]:
        """Propose criteria read from one job description (ADR-030 D13, D15, D25).

        **The description is untrusted third-party text** and is sent only inside the
        prompt's labelled ``BEGIN … END`` data block, after the rules. A description that
        contains a data-block marker itself could close the block and speak outside it, so it
        is refused before any request is built: nothing is sent and nothing is spent.

        **What comes back is a proposal, never a requirement.** The reply is validated whole
        against a strict wire shape, and one malformed item refuses all of it — no partial
        adoption (D26). The provider, not the model, sets provenance and who produced each
        proposal. Every proposal then has to pass the verifier against the pinned text, and
        that, not this prompt, is what makes an injection unable to produce a requirement.

        **No production path calls this.** Wiring extraction into derivation is a later,
        separately approved step.

        Raises:
            AIProviderRejectedError: The description contains a data-block marker, or Gemini
                refused or blocked the request.
            AIProviderUnavailableError, AIResponseInvalidError: As for the other operations.
        """
        if _DATA_BLOCK_MARKER.search(description):
            # The reason is a category; the description is never quoted (INV-4, D24).
            raise AIProviderRejectedError(
                "Job description contains the prompt's data-block marker; it was not sent."
            )
        payload = _generate_content_body(
            load_prompt("job_requirement_extraction").format(description=description),
            _JOB_REQUIREMENTS_SCHEMA,
        )
        raw = await self._post_with_retries(payload, usage)
        data = self._response_object(raw)
        try:
            reply = _WireReply.model_validate(data)
        except ValidationError as exc:
            # error_count only: Pydantic's detail would quote the reply, and the reply quotes
            # the description.
            raise AIResponseInvalidError(
                "Gemini job-requirement response failed schema validation "
                f"({exc.error_count()} error(s))."
            ) from exc
        return [
            ExtractionProposal(
                requirement_type=RequirementType(item.requirement_type),
                value=item.value(),
                evidence_text=item.evidence_text,
                extractor=_JOB_REQUIREMENTS_EXTRACTOR,
                extractor_version=_JOB_REQUIREMENTS_EXTRACTOR_VERSION,
                provider=self.name,
                model=self._model,
                reported_strength=(
                    None
                    if item.reported_strength is None
                    else RequirementStrength(item.reported_strength)
                ),
                reported_confidence=(
                    None
                    if item.reported_confidence is None
                    else Confidence(item.reported_confidence)
                ),
            )
            for item in reply.proposals
        ]

    # -- request ------------------------------------------------------------------------

    async def generate_application_content(
        self,
        evidence: ApplicationEvidence,
        job: JobBrief,
        questions: list[ApplicationQuestion],
        limits: GenerationLimits,
    ) -> ApplicationDraft:
        """Not implemented. Fails closed, so selecting Gemini degrades rather than misleads.

        **This is an interface stub, not a Gemini implementation.** Week 7 ships mock-provider
        generation only; the live implementation, its prompt payload and its cost accounting are
        deferred to Week 8/9 (ADR-025 § Slices). The method exists because
        :class:`~app.ai.providers.base.AIProvider` gained an abstract method and this class must
        stay concrete — an abstract Gemini would break provider construction for resume parsing
        and field relatedness, which do work.

        It makes no HTTP request, needs no API key, builds no prompt and reads no candidate data.
        The arguments are accepted and dropped: nothing is logged, retained or forwarded.

        Raising :class:`~app.ai.errors.AIProviderUnavailableError` puts this on the path the
        preparation service already handles — **HTTP 200**, ``NOTHING_VERIFIABLE``,
        ``AI_GENERATION_UNAVAILABLE`` — so an operator who switches to Gemini gets an honest
        empty package instead of a 500 or, far worse, a package that silently came from
        somewhere else.

        Raises:
            AIProviderUnavailableError: Always.
        """
        raise AIProviderUnavailableError(
            "Gemini application generation is not implemented; generation is available from "
            "the mock provider only."
        )

    def _build_relatedness_payload(
        self, field_of_study: str, allowed_fields: list[str]
    ) -> dict[str, Any]:
        """Build the relatedness request body.

        The prompt carries exactly two values: the field of study and the permitted fields.
        They are serialized as a JSON data block rather than spliced into the instructions,
        so a field of study written as an instruction is read as data (ADR-019).
        """
        prompt = load_prompt("field_relatedness")
        data = json.dumps(
            {"candidate_field_of_study": field_of_study, "allowed_fields": list(allowed_fields)},
            ensure_ascii=False,
        )
        return _generate_content_body(f"{prompt}\n{data}\n", _RELATEDNESS_SCHEMA)

    def _build_payload(self, resume_text: str) -> dict[str, Any]:
        """Build the request body.

        The prompt and the resume text are both sensitive; this returns them for immediate
        transmission and they are never retained or logged — by this service or, through
        ``store: false``, by Google.
        """
        prompt = load_prompt("resume_extraction")
        return _generate_content_body(prompt + resume_text, _RESPONSE_SCHEMA)

    async def _post_with_retries(
        self, payload: dict[str, Any], usage: UsageSink | None = None
    ) -> dict[str, Any]:
        """POST to the API, retrying only failures that a retry could plausibly fix.

        Retry eligibility, the attempt cap and the error translation below are unchanged by
        usage accounting (ADR-026 D4): the sink is written to, never consulted.

        Usage is accumulated from **every attempt that reported any**, whether that attempt
        succeeded or was throttled, rejected or failed with a server error — a retried call
        may be billed for each try, and counting only the last would under-report it. It is
        recorded before validation, so tokens spent on a reply that later fails schema
        validation or arrives truncated are still accounted for.

        An attempt that reported no usage contributes nothing: a timeout and a transport
        failure return no body at all, and an error body need not carry a count. Nothing is
        invented for them, because a guessed figure is worse than an honest ``unknown``.
        """
        url = f"{self._api_base}/models/{self._model}:generateContent"
        # The key travels as a header, never in the URL — a query string lands in access
        # logs and proxy logs (standards/security_privacy.md, privacy rules).
        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                raw = await self._post_once(url, headers, payload, usage)
            except AIProviderUnavailableError as exc:
                # Retryable: transport failure, timeout, or 5xx.
                last_error = exc
                logger.warning(
                    "provider=gemini model=%s attempt=%d/%d outcome=retryable_failure",
                    self._model,
                    attempt + 1,
                    self._max_retries + 1,
                )
            except AIProviderRejectedError:
                # Not retryable: the same request produces the same rejection.
                raise
            else:
                _record_usage(usage, raw, tokens_certain=True)
                return raw

        raise AIProviderUnavailableError(
            f"Gemini request failed after {self._max_retries + 1} attempt(s)."
        ) from last_error

    async def _post_once(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        usage: UsageSink | None = None,
    ) -> dict[str, Any]:
        """Perform one request and translate transport errors into application errors."""
        try:
            if self._client is not None:
                response = await self._client.post(
                    url, headers=headers, json=payload, timeout=self._timeout
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise AIProviderUnavailableError("Gemini request timed out.") from exc
        except httpx.HTTPError as exc:
            # Deliberately does not include str(exc): an httpx error can echo the request
            # URL and body, and the body is resume text.
            raise AIProviderUnavailableError(
                f"Gemini transport failure ({type(exc).__name__})."
            ) from exc

        return self._handle_status(response, usage)

    def _handle_status(
        self, response: httpx.Response, usage: UsageSink | None = None
    ) -> dict[str, Any]:
        """Translate an HTTP status into either a payload or an application error.

        An error reply is read for its usage block **before** the status is translated,
        because raising discards the body and a rejected or throttled attempt may still
        report what it consumed (ADR-026 D4). Nothing about the translation changes: the
        same statuses raise the same errors under the same conditions, and an error that
        reports no usage contributes nothing rather than a guess.
        """
        status = response.status_code

        if status >= 400:
            _record_usage(usage, _error_body(response), tokens_certain=False)

        if status >= 500:
            raise AIProviderUnavailableError(f"Gemini returned server error {status}.")
        if status == 429:
            raise AIProviderUnavailableError("Gemini rate limit reached.")
        if status in (401, 403):
            raise AIProviderRejectedError("Gemini rejected the credentials.")
        if status >= 400:
            # The body may quote the submitted content back, so it is not included.
            raise AIProviderRejectedError(f"Gemini rejected the request ({status}).")

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise AIResponseInvalidError("Gemini response was not valid JSON.") from exc
        return body

    # -- response -----------------------------------------------------------------------

    def _parse_response(self, raw: dict[str, Any]) -> ResumeExtraction:
        """Validate the reply into :class:`ResumeExtraction`.

        Provider output is untrusted input. Every failure below yields
        :class:`AIResponseInvalidError`, which the service turns into a NEEDS_REVIEW
        outcome — never a silent pass and never an unhandled crash
        (``standards/ai.md`` §4).
        """
        data = self._response_object(raw)
        try:
            return ResumeExtraction.model_validate(data)
        except ValidationError as exc:
            # error_count only. Pydantic's error detail embeds the offending values, which
            # here are candidate data (INV-4).
            raise AIResponseInvalidError(
                f"Gemini response failed schema validation ({exc.error_count()} error(s))."
            ) from exc

    def _response_object(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Extract the single JSON object from a Gemini reply, or raise.

        Shared by every operation; each then validates the object against its own model.
        """
        candidates = raw.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            # A blocked prompt returns no candidates. The block reason is a category, not
            # content, so it is safe to include.
            reason = (raw.get("promptFeedback") or {}).get("blockReason")
            if reason:
                raise AIProviderRejectedError(f"Gemini blocked the request ({reason}).")
            raise AIResponseInvalidError("Gemini response contained no candidates.")

        first = candidates[0]
        if first.get("finishReason") == "MAX_TOKENS":
            raise AIResponseInvalidError("Gemini response was truncated.")

        parts = (first.get("content") or {}).get("parts") or []
        # A part marked as a thought is the model's reasoning, not its answer: joining it in
        # would corrupt the JSON. A thoughtSignature on an answer part is metadata, and the
        # part's text is still read.
        text = "".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and part.get("thought") is not True
        )
        if not text.strip():
            raise AIResponseInvalidError("Gemini response contained no text.")

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIResponseInvalidError(
                "Gemini response body was not valid JSON."
            ) from exc

        if not isinstance(data, dict):
            raise AIResponseInvalidError("Gemini response JSON was not an object.")
        return data
