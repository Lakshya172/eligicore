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

Privacy: the prompt sent to Gemini contains resume text, and the response contains candidate
data. **Neither is ever logged** (INV-4). Logging in this module is confined to provider
name, model, status category and timing.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from app.ai.errors import (
    AIConfigurationError,
    AIProviderRejectedError,
    AIProviderUnavailableError,
    AIResponseInvalidError,
)
from app.ai.prompts import load_prompt
from app.ai.providers.base import AIProvider
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


class GeminiFlashProvider(AIProvider):
    """Structured resume extraction via the Gemini API."""

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

    async def extract_resume(self, resume_text: str) -> ResumeExtraction:
        """Extract a structured profile from resume text."""
        payload = self._build_payload(resume_text)
        raw = await self._post_with_retries(payload)
        return self._parse_response(raw)

    # -- request ------------------------------------------------------------------------

    def _build_payload(self, resume_text: str) -> dict[str, Any]:
        """Build the request body.

        The prompt and the resume text are both sensitive; this returns them for immediate
        transmission and they are never retained or logged.
        """
        prompt = load_prompt("resume_extraction")
        return {
            "contents": [{"parts": [{"text": prompt + resume_text}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _RESPONSE_SCHEMA,
                # Deterministic extraction, not creative writing. Extraction should return
                # the same structure for the same resume.
                "temperature": 0.0,
            },
        }

    async def _post_with_retries(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to the API, retrying only failures that a retry could plausibly fix."""
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
                return await self._post_once(url, headers, payload)
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

        raise AIProviderUnavailableError(
            f"Gemini request failed after {self._max_retries + 1} attempt(s)."
        ) from last_error

    async def _post_once(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
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

        return self._handle_status(response)

    def _handle_status(self, response: httpx.Response) -> dict[str, Any]:
        """Translate an HTTP status into either a payload or an application error."""
        status = response.status_code

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
            return response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise AIResponseInvalidError("Gemini response was not valid JSON.") from exc

    # -- response -----------------------------------------------------------------------

    def _parse_response(self, raw: dict[str, Any]) -> ResumeExtraction:
        """Validate the reply into :class:`ResumeExtraction`.

        Provider output is untrusted input. Every failure below yields
        :class:`AIResponseInvalidError`, which the service turns into a NEEDS_REVIEW
        outcome — never a silent pass and never an unhandled crash
        (``standards/ai.md`` §4).
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
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
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

        try:
            return ResumeExtraction.model_validate(data)
        except ValidationError as exc:
            # error_count only. Pydantic's error detail embeds the offending values, which
            # here are candidate data (INV-4).
            raise AIResponseInvalidError(
                f"Gemini response failed schema validation ({exc.error_count()} error(s))."
            ) from exc
