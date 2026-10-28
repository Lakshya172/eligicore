"""The exact request each existing Gemini call puts on the wire, pinned whole.

Resume extraction and field relatedness are the two Gemini paths that work today. ADR-030
Step 8 changes how they are configured, so their full request contract is pinned here first:
URL, method, headers and the complete JSON body, compared by equality rather than by spot
checks, so that anything added, dropped or renamed fails a test.

**No network and no key.** Every request goes to an ``httpx.MockTransport``; the key is a
placeholder that the transport only compares (``standards/testing.md`` §1).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.ai.prompts import load_prompt
from app.ai.providers.gemini import (
    _RELATEDNESS_SCHEMA,
    _RESPONSE_SCHEMA,
    GeminiFlashProvider,
)

API_BASE = "https://generativelanguage.example.invalid/v1beta"
MODEL = "gemini-contract-model"
KEY = "test-key-not-real"

RESUME = "Contract Candidate\ncontract.candidate@example.com\nB.Tech CSE, CGPA 8.4/10\n"
FIELD = "Computer Science"
ALLOWED = ["Computer Science", "Information Technology"]

RESUME_REPLY = {"skills": ["Python"]}
RELATEDNESS_REPLY = {"result": "RELATED", "confidence": "HIGH", "reason": "Same field."}


class Capture:
    """Records every request and answers with a fixed sequence of replies."""

    def __init__(self, *replies: httpx.Response) -> None:
        self.requests: list[httpx.Request] = []
        self._replies = list(replies)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]

    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(request.content) for request in self.requests]


def _reply(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}
    )


def _gemini(capture: Capture, *, max_retries: int = 0) -> GeminiFlashProvider:
    return GeminiFlashProvider(
        api_key=KEY,
        model=MODEL,
        api_base=API_BASE,
        timeout_seconds=5,
        max_retries=max_retries,
        client=httpx.AsyncClient(transport=httpx.MockTransport(capture)),
    )


def _resume_body() -> dict[str, Any]:
    """The whole resume-extraction request body, as the provider must send it."""
    return {
        "contents": [{"parts": [{"text": load_prompt("resume_extraction") + RESUME}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _RESPONSE_SCHEMA,
            "temperature": 0.0,
        },
    }


def _relatedness_body() -> dict[str, Any]:
    """The whole field-relatedness request body, as the provider must send it."""
    data = json.dumps(
        {"candidate_field_of_study": FIELD, "allowed_fields": ALLOWED}, ensure_ascii=False
    )
    return {
        "contents": [{"parts": [{"text": f"{load_prompt('field_relatedness')}\n{data}\n"}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _RELATEDNESS_SCHEMA,
            "temperature": 0.0,
        },
    }


async def _extract(capture: Capture, **kwargs: Any) -> None:
    await _gemini(capture, **kwargs).extract_resume(RESUME)


async def _relate(capture: Capture, **kwargs: Any) -> None:
    await _gemini(capture, **kwargs).assess_field_relatedness(FIELD, ALLOWED)


#: (operation, its call, the body it must send, a valid reply to it)
OPERATIONS = [
    pytest.param(_extract, _resume_body, RESUME_REPLY, id="extract_resume"),
    pytest.param(_relate, _relatedness_body, RELATEDNESS_REPLY, id="assess_field_relatedness"),
]


# ---------------------------------------------------------------------------------------
# The request, whole
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(("call", "expected_body", "reply"), OPERATIONS)
async def test_the_request_body_is_exactly_the_contract(
    call: Any, expected_body: Any, reply: dict[str, Any]
) -> None:
    capture = Capture(_reply(reply))
    await call(capture)

    assert capture.bodies() == [expected_body()]


@pytest.mark.anyio
@pytest.mark.parametrize(("call", "expected_body", "reply"), OPERATIONS)
async def test_the_request_goes_to_generate_content_with_the_key_as_a_header(
    call: Any, expected_body: Any, reply: dict[str, Any]
) -> None:
    capture = Capture(_reply(reply))
    await call(capture)

    (request,) = capture.requests
    assert request.method == "POST"
    assert str(request.url) == f"{API_BASE}/models/{MODEL}:generateContent"
    assert request.headers["x-goog-api-key"] == KEY
    assert request.headers["content-type"] == "application/json"
    assert KEY not in str(request.url)


@pytest.mark.anyio
@pytest.mark.parametrize(("call", "expected_body", "reply"), OPERATIONS)
async def test_a_retried_request_sends_the_same_body_every_time(
    call: Any, expected_body: Any, reply: dict[str, Any]
) -> None:
    """Every attempt is a full request, so every attempt must carry the whole contract."""
    capture = Capture(httpx.Response(503), _reply(reply))
    await call(capture, max_retries=1)

    assert capture.bodies() == [expected_body(), expected_body()]


# ---------------------------------------------------------------------------------------
# The reply: what the two operations already do with it, kept as it is
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_resume_extraction_still_parses_its_reply() -> None:
    capture = Capture(_reply({"name": "Contract Candidate", "skills": ["Python", "SQL"]}))
    result = await _gemini(capture).extract_resume(RESUME)

    assert result.name == "Contract Candidate"
    assert result.skills == ["Python", "SQL"]


@pytest.mark.anyio
async def test_field_relatedness_still_parses_its_reply() -> None:
    capture = Capture(_reply(RELATEDNESS_REPLY))
    result = await _gemini(capture).assess_field_relatedness(FIELD, ALLOWED)

    assert (result.result.value, result.confidence.value) == ("RELATED", "HIGH")


@pytest.mark.anyio
async def test_text_split_across_parts_is_still_joined_in_order() -> None:
    text = json.dumps(RELATEDNESS_REPLY)
    split = httpx.Response(
        200,
        json={"candidates": [{"content": {"parts": [{"text": text[:10]}, {"text": text[10:]}]}}]},
    )
    result = await _gemini(Capture(split)).assess_field_relatedness(FIELD, ALLOWED)

    assert result.reason == "Same field."
