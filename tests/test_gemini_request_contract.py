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
import logging
import re
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.ai.ai_service import AIService, build_provider
from app.ai.errors import AIResponseInvalidError
from app.ai.prompts import load_prompt
from app.ai.providers.gemini import (
    _RELATEDNESS_SCHEMA,
    _RESPONSE_SCHEMA,
    GeminiFlashProvider,
)
from app.ai.providers.mock import MockAIProvider
from app.ai.usage import AIUsage, UsageSink, cost_micros
from app.config import AIProviderName, Settings

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


#: ADR-030 D15 and Google's Gemini 3.8 Flash migration notes: sampling controls are deprecated
#: and ignored (``temperature``, ``topP``, ``topK``), and the rest are rejected
#: (``candidateCount`` above 1, the penalties). Both spellings, because a request that sent
#: either would be sending one.
DEPRECATED_SAMPLING = frozenset(
    {
        "temperature", "topP", "topK", "candidateCount", "presencePenalty", "frequencyPenalty",
        "top_p", "top_k", "candidate_count", "presence_penalty", "frequency_penalty",
    }
)

#: The thinking levels ``gemini-3.8-flash`` accepts; ``MINIMAL`` is rejected on that model.
SUPPORTED_THINKING_LEVELS = frozenset({"LOW", "MEDIUM", "HIGH"})


def _generation_config(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "responseMimeType": "application/json",
        "responseSchema": schema,
        "thinkingConfig": {"thinkingLevel": "LOW"},
    }


def _resume_body() -> dict[str, Any]:
    """The whole resume-extraction request body, as the provider must send it."""
    return {
        "contents": [{"parts": [{"text": load_prompt("resume_extraction") + RESUME}]}],
        "generationConfig": _generation_config(_RESPONSE_SCHEMA),
        "store": False,
    }


def _relatedness_body() -> dict[str, Any]:
    """The whole field-relatedness request body, as the provider must send it."""
    data = json.dumps(
        {"candidate_field_of_study": FIELD, "allowed_fields": ALLOWED}, ensure_ascii=False
    )
    return {
        "contents": [{"parts": [{"text": f"{load_prompt('field_relatedness')}\n{data}\n"}]}],
        "generationConfig": _generation_config(_RELATEDNESS_SCHEMA),
        "store": False,
    }


def _keys(value: Any) -> set[str]:
    """Every key anywhere in a JSON value, at any depth."""
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


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


# ---------------------------------------------------------------------------------------
# ADR-030 Step 8a: no sampling parameters, no stored requests, an explicit thinking level
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(("call", "expected_body", "reply"), OPERATIONS)
async def test_no_deprecated_sampling_parameter_is_sent_anywhere(
    call: Any, expected_body: Any, reply: dict[str, Any]
) -> None:
    capture = Capture(_reply(reply))
    await call(capture)

    assert _keys(capture.bodies()[0]) & DEPRECATED_SAMPLING == set()


@pytest.mark.anyio
@pytest.mark.parametrize(("call", "expected_body", "reply"), OPERATIONS)
async def test_every_request_and_every_retry_opts_out_of_request_storage(
    call: Any, expected_body: Any, reply: dict[str, Any]
) -> None:
    """Both calls carry candidate data: resume text, or a field of study.

    Google stores ``generateContent`` requests by default on new paid projects; a
    request-level ``store`` takes precedence over the project setting. It is top-level, and it
    is ``False`` itself, not merely falsy, on every attempt.
    """
    capture = Capture(httpx.Response(503), _reply(reply))
    await call(capture, max_retries=1)

    bodies = capture.bodies()
    assert len(bodies) == 2
    assert all(body["store"] is False for body in bodies)
    assert all("store" not in body["generationConfig"] for body in bodies)


@pytest.mark.anyio
@pytest.mark.parametrize(("call", "expected_body", "reply"), OPERATIONS)
async def test_the_thinking_level_is_explicit_and_supported(
    call: Any, expected_body: Any, reply: dict[str, Any]
) -> None:
    """Explicit, because Google documents two different defaults for an unset level."""
    capture = Capture(_reply(reply))
    await call(capture)

    thinking = capture.bodies()[0]["generationConfig"]["thinkingConfig"]
    assert set(thinking) == {"thinkingLevel"}, "no thinkingBudget, no includeThoughts"
    assert thinking["thinkingLevel"] in SUPPORTED_THINKING_LEVELS


# ---------------------------------------------------------------------------------------
# Thought parts in a reply
# ---------------------------------------------------------------------------------------


def _parts_reply(*parts: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"candidates": [{"content": {"parts": list(parts)}}]})


@pytest.mark.anyio
async def test_a_thought_part_is_skipped_and_the_answer_still_parses() -> None:
    reply = _parts_reply(
        {"text": "Thinking about whether these fields match...", "thought": True},
        {"text": json.dumps(RELATEDNESS_REPLY), "thoughtSignature": "c2lnbmF0dXJl"},
    )
    result = await _gemini(Capture(reply)).assess_field_relatedness(FIELD, ALLOWED)

    assert result.reason == "Same field."


@pytest.mark.anyio
async def test_a_thought_part_never_reaches_resume_extraction() -> None:
    reply = _parts_reply(
        {"text": "The name is probably", "thought": True},
        {"text": json.dumps({"name": "Contract Candidate"})},
    )
    result = await _gemini(Capture(reply)).extract_resume(RESUME)

    assert result.name == "Contract Candidate"


@pytest.mark.anyio
async def test_a_reply_of_thoughts_alone_has_no_answer() -> None:
    reply = _parts_reply({"text": json.dumps(RELATEDNESS_REPLY), "thought": True})

    with pytest.raises(AIResponseInvalidError, match="no text"):
        await _gemini(Capture(reply)).assess_field_relatedness(FIELD, ALLOWED)


@pytest.mark.anyio
async def test_a_part_marked_not_a_thought_is_still_read() -> None:
    reply = _parts_reply({"text": json.dumps(RELATEDNESS_REPLY), "thought": False})
    result = await _gemini(Capture(reply)).assess_field_relatedness(FIELD, ALLOWED)

    assert result.reason == "Same field."


# ---------------------------------------------------------------------------------------
# Thought tokens in usage and cost
# ---------------------------------------------------------------------------------------


def _usage_reply(metadata: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"parts": [{"text": json.dumps(RELATEDNESS_REPLY)}]}}],
            "usageMetadata": metadata,
        },
    )


async def _usage_of(*replies: httpx.Response, max_retries: int = 0) -> AIUsage:
    sink = UsageSink()
    await _gemini(Capture(*replies), max_retries=max_retries).assess_field_relatedness(
        FIELD, ALLOWED, usage=sink
    )
    return sink.usage


@pytest.mark.anyio
async def test_reported_thought_tokens_are_recorded_beside_the_candidates() -> None:
    usage = await _usage_of(
        _usage_reply(
            {"promptTokenCount": 100, "candidatesTokenCount": 20,
             "thoughtsTokenCount": 30, "totalTokenCount": 150}
        )
    )
    assert usage == AIUsage(
        prompt_tokens=100, completion_tokens=20, total_tokens=150, thought_tokens=30
    )


@pytest.mark.anyio
async def test_an_absent_thought_count_is_zero_only_when_the_total_proves_it() -> None:
    """JSON omits a zero count, so absence alone proves nothing; the total does."""
    usage = await _usage_of(
        _usage_reply({"promptTokenCount": 100, "candidatesTokenCount": 20, "totalTokenCount": 120})
    )
    assert usage.thought_tokens == 0


@pytest.mark.anyio
async def test_an_absent_thought_count_counts_a_reported_tool_use_prompt() -> None:
    usage = await _usage_of(
        _usage_reply(
            {"promptTokenCount": 100, "candidatesTokenCount": 20,
             "toolUsePromptTokenCount": 5, "totalTokenCount": 125}
        )
    )
    assert usage.thought_tokens == 0


@pytest.mark.anyio
async def test_an_absent_thought_count_the_total_contradicts_is_unknown() -> None:
    usage = await _usage_of(
        _usage_reply({"promptTokenCount": 100, "candidatesTokenCount": 20, "totalTokenCount": 150})
    )
    assert usage.thought_tokens is None
    assert cost_micros(usage, 750, 3750) is None, "an unknown thought count cannot be priced"


@pytest.mark.anyio
@pytest.mark.parametrize("bad", ["30", -1, True, None, 1.5])
async def test_a_malformed_thought_count_is_unknown(bad: object) -> None:
    usage = await _usage_of(
        _usage_reply(
            {"promptTokenCount": 100, "candidatesTokenCount": 20,
             "thoughtsTokenCount": bad, "totalTokenCount": 150}
        )
    )
    assert usage.thought_tokens is None
    assert (usage.prompt_tokens, usage.completion_tokens) == (100, 20), "fields degrade alone"


@pytest.mark.anyio
async def test_thought_tokens_are_summed_across_attempts() -> None:
    throttled = httpx.Response(
        429,
        json={"usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 0,
                                "thoughtsTokenCount": 7, "totalTokenCount": 107}},
    )
    usage = await _usage_of(
        throttled,
        _usage_reply(
            {"promptTokenCount": 100, "candidatesTokenCount": 20,
             "thoughtsTokenCount": 30, "totalTokenCount": 150}
        ),
        max_retries=1,
    )
    assert usage.thought_tokens == 37


def test_thought_tokens_are_priced_at_the_completion_rate() -> None:
    """Google bills thinking as output: response price is output tokens plus thinking tokens."""
    usage = AIUsage(
        prompt_tokens=1000, completion_tokens=1000, total_tokens=3000, thought_tokens=1000
    )
    assert cost_micros(usage, 750, 3750) == 750 + 3750 + 3750


def test_a_provider_that_reports_no_thinking_costs_exactly_what_it_did() -> None:
    """The accounting a non-thinking provider already had is unchanged, figure for figure."""
    sink = UsageSink()
    sink.record(prompt_tokens=2000, completion_tokens=1000, total_tokens=3000)
    usage = sink.usage

    assert usage.thought_tokens == 0
    assert cost_micros(usage, 100, 400) == 2000 * 100 // 1000 + 1000 * 400 // 1000
    assert usage == AIUsage(prompt_tokens=2000, completion_tokens=1000, total_tokens=3000)


def test_a_reply_with_unreadable_usage_leaves_thought_tokens_unknown() -> None:
    sink = UsageSink()
    sink.record_unreadable()
    assert sink.usage.thought_tokens is None


@pytest.mark.anyio
async def test_the_ai_call_line_appends_thought_tokens_after_every_existing_field(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Existing fields keep their names and order; the new one is added at the end."""
    capture = Capture(
        _usage_reply(
            {"promptTokenCount": 100, "candidatesTokenCount": 20,
             "thoughtsTokenCount": 30, "totalTokenCount": 150}
        )
    )
    with caplog.at_level(logging.INFO, logger="eligicore.ai"):
        await AIService(_gemini(capture)).assess_field_relatedness(FIELD, ALLOWED)

    (line,) = [r.getMessage() for r in caplog.records if "operation=assess_field" in r.getMessage()]
    assert re.search(
        r"prompt_tokens=100 completion_tokens=20 total_tokens=150 cost_micros=\S+ "
        r"thought_tokens=30 duration_ms=",
        line,
    ), line


@pytest.mark.anyio
async def test_the_mock_reports_zero_thought_tokens(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="eligicore.ai"):
        await AIService(MockAIProvider()).assess_field_relatedness(FIELD, ALLOWED)

    assert "thought_tokens=0 " in caplog.text


# ---------------------------------------------------------------------------------------
# The configured model
# ---------------------------------------------------------------------------------------


def test_the_default_gemini_model_is_gemini_3_8_flash() -> None:
    """ADR-030 D15. ``gemini-2.0-flash`` was shut down on 2026-06-01 (ADR-028 D19a)."""
    assert Settings().gemini_model == "gemini-3.8-flash"


def test_the_shut_down_model_is_no_longer_configured_anywhere_by_default() -> None:
    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assert "ELIGICORE_GEMINI_MODEL=gemini-3.8-flash" in example.splitlines()
    assert "gemini-2.0-flash" not in example


def test_selecting_gemini_uses_the_new_default_model() -> None:
    provider = build_provider(
        Settings(ai_provider=AIProviderName.GEMINI, gemini_api_key=KEY)
    )
    assert provider.model == "gemini-3.8-flash"


def test_the_model_change_selects_no_provider_and_enables_no_extraction() -> None:
    settings = Settings()
    assert settings.ai_provider is AIProviderName.MOCK
    assert settings.extraction_enabled is False
