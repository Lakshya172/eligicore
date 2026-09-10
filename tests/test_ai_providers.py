"""AI provider abstraction, mock provider, and Gemini provider tests.

**Not one test in this file makes a network call or needs an API key.** The Gemini provider
is exercised entirely through an injected `httpx.MockTransport`, so its request shaping,
status handling and response validation are all covered without touching the live service
(``standards/testing.md`` §1).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.ai.ai_service import AIService, build_provider
from app.ai.errors import (
    AIConfigurationError,
    AIProviderRejectedError,
    AIProviderUnavailableError,
    AIResponseInvalidError,
)
from app.ai.prompts import load_prompt
from app.ai.providers.base import AIProvider
from app.ai.providers.gemini import GeminiFlashProvider
from app.ai.providers.mock import MockAIProvider
from app.config import AIProviderName, Settings
from app.schemas.candidate import Confidence, GradeScale
from app.schemas.resume import ResumeExtraction

RESUME = "\n".join(
    [
        "Test Candidate",
        "test.candidate@example.com",
        "B.Tech Information Technology",
        "CGPA 8.2/10",
        "Graduating 2027",
        "Skills: Python, React, SQL",
    ]
)


# ---------------------------------------------------------------------------------------
# The interface
# ---------------------------------------------------------------------------------------


def test_providers_implement_the_interface() -> None:
    assert issubclass(MockAIProvider, AIProvider)
    assert issubclass(GeminiFlashProvider, AIProvider)


def test_interface_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        AIProvider()  # type: ignore[abstract]


def test_service_layer_imports_no_vendor_sdk() -> None:
    """INV-5: business logic must not know a vendor exists."""
    import app.routers.resumes as router_module
    import app.services.candidate_normalizer as normalizer
    import app.services.resume_parser as parser

    for module in (parser, normalizer, router_module):
        source = open(module.__file__, encoding="utf-8").read()  # noqa: SIM115
        for vendor in ("gemini", "openai", "anthropic", "google.generativeai"):
            assert f"import {vendor}" not in source.lower()
            assert f"from {vendor}" not in source.lower()


def test_importing_ai_service_does_not_load_gemini() -> None:
    """The Gemini import is function-local so a mock-only run never touches provider code."""
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.ai.ai_service, sys; "
            "print('app.ai.providers.gemini' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"


# ---------------------------------------------------------------------------------------
# Mock provider
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_mock_extracts_deterministically() -> None:
    provider = MockAIProvider()
    first = await provider.extract_resume(RESUME)
    second = await provider.extract_resume(RESUME)
    assert first == second


@pytest.mark.anyio
async def test_mock_extracts_expected_fields() -> None:
    result = await MockAIProvider().extract_resume(RESUME)

    assert result.email == "test.candidate@example.com"
    assert "Python" in result.skills
    assert result.education[0].cgpa == 8.2
    assert result.education[0].scale is GradeScale.SCALE_10


@pytest.mark.anyio
async def test_mock_leaves_unstated_scale_unknown() -> None:
    """Even the mock must not assume a 10-point scale."""
    result = await MockAIProvider().extract_resume("B.Tech\nCGPA 8.2\nGraduating 2027")

    assert result.education[0].cgpa == 8.2
    assert result.education[0].scale is GradeScale.UNKNOWN
    assert result.field_confidence["education[0].cgpa"] is Confidence.LOW


@pytest.mark.anyio
async def test_mock_never_invents_backlogs() -> None:
    result = await MockAIProvider().extract_resume(RESUME)
    assert result.backlogs is None


@pytest.mark.anyio
async def test_mock_records_lengths_not_content() -> None:
    """An assertion about calls must not itself become a way to leak resume text."""
    provider = MockAIProvider()
    await provider.extract_resume(RESUME)

    assert provider.call_count == 1
    assert provider.received_text_lengths == [len(RESUME)]
    assert all(isinstance(v, int) for v in provider.received_text_lengths)


@pytest.mark.anyio
async def test_mock_can_inject_failure() -> None:
    provider = MockAIProvider(fail_with=AIProviderUnavailableError("simulated"))
    with pytest.raises(AIProviderUnavailableError):
        await provider.extract_resume(RESUME)


@pytest.mark.anyio
async def test_mock_can_inject_invalid_response() -> None:
    with pytest.raises(AIResponseInvalidError):
        await MockAIProvider(raise_invalid_response=True).extract_resume(RESUME)


@pytest.mark.anyio
async def test_mock_can_pin_exact_output() -> None:
    pinned = ResumeExtraction(name="Pinned Name", skills=["Python"])
    result = await MockAIProvider(return_extraction=pinned).extract_resume(RESUME)
    assert result is pinned


@pytest.mark.anyio
async def test_mock_does_not_match_c_inside_other_words() -> None:
    result = await MockAIProvider().extract_resume("Excellent communication. CGPA 8.0/10")
    assert "C" not in result.skills


# ---------------------------------------------------------------------------------------
# Gemini provider — configuration
# ---------------------------------------------------------------------------------------


def test_gemini_requires_an_api_key() -> None:
    with pytest.raises(AIConfigurationError):
        GeminiFlashProvider(
            api_key=None,
            model="gemini-2.0-flash",
            api_base="https://example.invalid",
            timeout_seconds=5,
            max_retries=0,
        )


def test_gemini_requires_a_model() -> None:
    with pytest.raises(AIConfigurationError):
        GeminiFlashProvider(
            api_key="test-key-not-real",
            model="",
            api_base="https://example.invalid",
            timeout_seconds=5,
            max_retries=0,
        )


def test_gemini_model_is_configurable() -> None:
    provider = _gemini(model="some-other-flash-model")
    assert provider.model == "some-other-flash-model"
    assert provider.name == "gemini"


# ---------------------------------------------------------------------------------------
# Gemini provider — behaviour, via MockTransport (no network)
# ---------------------------------------------------------------------------------------


def _gemini(
    *,
    handler: Any = None,
    model: str = "gemini-2.0-flash",
    max_retries: int = 0,
) -> GeminiFlashProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler)) if handler else None
    return GeminiFlashProvider(
        api_key="test-key-not-real",
        model=model,
        api_base="https://generativelanguage.example.invalid/v1beta",
        timeout_seconds=5,
        max_retries=max_retries,
        client=client,
    )


def _gemini_reply(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]},
    )


@pytest.mark.anyio
async def test_gemini_parses_a_valid_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _gemini_reply(
            {
                "name": "Test Candidate",
                "email": "test.candidate@example.com",
                "skills": ["Python", "React"],
                "education": [{"degree": "B.Tech", "cgpa": 8.2, "scale": "SCALE_10"}],
                "field_confidence": {"email": "HIGH"},
            }
        )

    result = await _gemini(handler=handler).extract_resume(RESUME)

    assert result.name == "Test Candidate"
    assert result.education[0].scale is GradeScale.SCALE_10
    assert result.field_confidence["email"] is Confidence.HIGH


@pytest.mark.anyio
async def test_gemini_sends_key_as_header_never_in_url() -> None:
    """A key in a query string lands in access logs and proxy logs."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["header"] = request.headers.get("x-goog-api-key")
        return _gemini_reply({"skills": []})

    await _gemini(handler=handler).extract_resume(RESUME)

    assert captured["header"] == "test-key-not-real"
    assert "test-key-not-real" not in captured["url"]
    assert "key=" not in captured["url"]


@pytest.mark.anyio
async def test_gemini_requests_structured_json_output() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _gemini_reply({"skills": []})

    await _gemini(handler=handler).extract_resume(RESUME)

    config = captured["body"]["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["temperature"] == 0.0, "extraction must be deterministic, not creative"
    assert "responseSchema" in config


@pytest.mark.anyio
async def test_gemini_sends_the_prompt_file_contents() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["text"] = json.loads(request.content)["contents"][0]["parts"][0]["text"]
        return _gemini_reply({"skills": []})

    await _gemini(handler=handler).extract_resume(RESUME)

    assert load_prompt("resume_extraction") in captured["text"]
    assert RESUME in captured["text"]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (500, AIProviderUnavailableError),
        (503, AIProviderUnavailableError),
        (429, AIProviderUnavailableError),
        (401, AIProviderRejectedError),
        (403, AIProviderRejectedError),
        (400, AIProviderRejectedError),
    ],
)
@pytest.mark.anyio
async def test_gemini_translates_http_statuses(status: int, expected: type) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "SENSITIVE-ECHO-1a2b"}})

    with pytest.raises(expected) as exc:
        await _gemini(handler=handler).extract_resume(RESUME)

    assert "SENSITIVE-ECHO-1a2b" not in str(exc.value), "provider body must not surface"


@pytest.mark.anyio
async def test_gemini_timeout_becomes_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    with pytest.raises(AIProviderUnavailableError):
        await _gemini(handler=handler).extract_resume(RESUME)


@pytest.mark.anyio
async def test_gemini_transport_error_does_not_leak_request_body() -> None:
    """An httpx error can echo the request URL and body, and the body is resume text."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"failed connecting while sending {RESUME}")

    with pytest.raises(AIProviderUnavailableError) as exc:
        await _gemini(handler=handler).extract_resume(RESUME)

    assert "test.candidate@example.com" not in str(exc.value)


@pytest.mark.anyio
async def test_gemini_retries_retryable_failures_then_gives_up() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503, json={})

    with pytest.raises(AIProviderUnavailableError):
        await _gemini(handler=handler, max_retries=2).extract_resume(RESUME)

    assert attempts["n"] == 3, "initial attempt plus two retries, then stop"


@pytest.mark.anyio
async def test_gemini_does_not_retry_a_rejection() -> None:
    """Repeating a rejected request produces the same rejection and costs money."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(401, json={})

    with pytest.raises(AIProviderRejectedError):
        await _gemini(handler=handler, max_retries=3).extract_resume(RESUME)

    assert attempts["n"] == 1


@pytest.mark.anyio
async def test_gemini_recovers_if_a_retry_succeeds() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(503, json={})
        return _gemini_reply({"skills": ["Python"]})

    result = await _gemini(handler=handler, max_retries=2).extract_resume(RESUME)
    assert result.skills == ["Python"]


# ---------------------------------------------------------------------------------------
# Gemini provider — malformed responses
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"candidates": []},
        {"candidates": [{"content": {"parts": []}}]},
        {"candidates": [{"content": {"parts": [{"text": "not json at all"}]}}]},
        {"candidates": [{"content": {"parts": [{"text": "[1, 2, 3]"}]}}]},
        {"candidates": [{"content": {"parts": [{"text": '{"skills": "not-a-list"}'}]}}]},
    ],
    ids=["empty", "no-candidates", "no-parts", "not-json", "json-array", "wrong-type"],
)
@pytest.mark.anyio
async def test_gemini_rejects_malformed_responses(body: dict[str, Any]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with pytest.raises(AIResponseInvalidError):
        await _gemini(handler=handler).extract_resume(RESUME)


@pytest.mark.anyio
async def test_gemini_rejects_a_truncated_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{"}]}}
                ]
            },
        )

    with pytest.raises(AIResponseInvalidError) as exc:
        await _gemini(handler=handler).extract_resume(RESUME)
    assert "truncated" in str(exc.value).lower()


@pytest.mark.anyio
async def test_gemini_reports_a_blocked_prompt_as_rejection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})

    with pytest.raises(AIProviderRejectedError) as exc:
        await _gemini(handler=handler).extract_resume(RESUME)
    assert "SAFETY" in str(exc.value)


@pytest.mark.anyio
async def test_gemini_schema_failure_does_not_echo_values() -> None:
    """Pydantic error detail embeds offending values, which here are candidate data."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _gemini_reply({"education": [{"cgpa": "SENSITIVE-GRADE-VALUE-x9"}]})

    with pytest.raises(AIResponseInvalidError) as exc:
        await _gemini(handler=handler).extract_resume(RESUME)
    assert "SENSITIVE-GRADE-VALUE-x9" not in str(exc.value)


@pytest.mark.anyio
async def test_gemini_ignores_unknown_response_keys() -> None:
    """An extra key should not fail the whole extraction."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _gemini_reply({"skills": ["Python"], "invented_field": "whatever"})

    result = await _gemini(handler=handler).extract_resume(RESUME)
    assert result.skills == ["Python"]


# ---------------------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------------------


def test_default_provider_is_mock() -> None:
    """An unconfigured checkout must not be able to make a paid call."""
    assert Settings().ai_provider is AIProviderName.MOCK
    assert isinstance(build_provider(Settings()), MockAIProvider)


def test_selecting_gemini_without_a_key_fails_loudly() -> None:
    settings = Settings(ai_provider=AIProviderName.GEMINI, gemini_api_key=None)
    with pytest.raises(AIConfigurationError):
        build_provider(settings)


def test_selecting_gemini_with_a_key_builds_the_provider() -> None:
    settings = Settings(
        ai_provider=AIProviderName.GEMINI, gemini_api_key="test-key-not-real"
    )
    provider = build_provider(settings)
    assert provider.name == "gemini"


def test_switching_provider_is_configuration_only() -> None:
    """ADR-004: swapping providers must not require a code change."""
    mock_provider = build_provider(Settings(ai_provider=AIProviderName.MOCK))
    gemini_provider = build_provider(
        Settings(ai_provider=AIProviderName.GEMINI, gemini_api_key="test-key-not-real")
    )

    assert isinstance(mock_provider, AIProvider)
    assert isinstance(gemini_provider, AIProvider)
    assert mock_provider.name != gemini_provider.name


# ---------------------------------------------------------------------------------------
# AI service logging
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ai_service_logs_metadata_not_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = AIService(MockAIProvider())
    with caplog.at_level("DEBUG", logger="eligicore.ai"):
        await service.extract_resume(RESUME)

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "provider=mock" in logged
    assert "input_chars=" in logged
    for secret in ("Test Candidate", "test.candidate@example.com", "CGPA 8.2"):
        assert secret not in logged


@pytest.mark.anyio
async def test_ai_service_logs_failures_without_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = AIService(MockAIProvider(fail_with=AIProviderUnavailableError("down")))
    with caplog.at_level("DEBUG", logger="eligicore.ai"):
        with pytest.raises(AIProviderUnavailableError):
            await service.extract_resume(RESUME)

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "outcome=error" in logged
    assert "test.candidate@example.com" not in logged


def test_prompt_loads_from_file_and_is_missing_loudly() -> None:
    assert "extraction system" in load_prompt("resume_extraction").lower()
    with pytest.raises(FileNotFoundError):
        load_prompt("no_such_prompt")
