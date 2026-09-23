"""Week 8 Slice 8A — cost and usage accounting (ADR-026 D2–D6).

Four things are pinned here, in rising order of how badly getting them wrong would hurt:

1. **Arithmetic.** Integer micro-units, truncating, with rates quoted per 1000 tokens.
2. **Unknown means unknown.** An unreported count, a malformed block, an unpriced model and
   an unreadable configuration all produce ``unknown`` — never ``0``, which would read as a
   free call, and never a fallback figure, which would read as a measurement.
3. **Accumulation.** A call that spoke to a provider more than once reports the sum, because
   under-reported cost is the failure the accumulation exists to prevent.
4. **Inertness.** Accounting can fail in any way it likes without changing what an AI call
   returns or raises (D6).

Offline throughout: the mock provider, or Gemini through an injected ``httpx.MockTransport``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx
import pytest

from app.ai.ai_service import AIService
from app.ai.errors import AIProviderUnavailableError, AIResponseInvalidError
from app.ai.providers.gemini import GeminiFlashProvider
from app.ai.providers.mock import MockAIProvider
from app.ai.usage import TOKENS_PER_RATE_UNIT, AIUsage, UsageSink, cost_micros
from app.config import ModelCostRate, Settings

RESUME = "Candidate resume text for accounting tests. CGPA 8.4/10."
FIELD = "Information Technology"
ALLOWED = ["Computer Science"]
MOCK_KEY = "mock:mock-deterministic-v1"


def priced(prompt: int = 100, completion: int = 400) -> Settings:
    """Settings that price the mock, so the cost path produces a real number."""
    return Settings(
        ai_cost_rates={
            MOCK_KEY: ModelCostRate(
                prompt_micros_per_1k=prompt, completion_micros_per_1k=completion
            )
        }
    )


def field_of(caplog: pytest.LogCaptureFixture, name: str) -> str:
    """The value of one ``key=value`` field in the single ai_call line captured."""
    lines = [r.getMessage() for r in caplog.records if "ai_call" in r.getMessage()]
    assert len(lines) == 1, lines
    match = re.search(rf"\b{name}=(\S+)", lines[0])
    assert match is not None, f"{name} missing from: {lines[0]}"
    return match.group(1)


# ---------------------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------------------


def test_cost_is_tokens_times_rate_per_thousand() -> None:
    usage = AIUsage(prompt_tokens=2000, completion_tokens=1000, total_tokens=3000)
    assert cost_micros(usage, 100, 400) == 2 * 100 + 1 * 400


def test_rates_are_quoted_per_thousand_tokens() -> None:
    assert TOKENS_PER_RATE_UNIT == 1000
    assert cost_micros(AIUsage(prompt_tokens=1000, completion_tokens=0, total_tokens=1000), 7, 9) == 7


def test_cost_truncates_rather_than_rounding_or_drifting() -> None:
    """Integer arithmetic. A sub-micro remainder is discarded, not floated."""
    result = cost_micros(AIUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2), 100, 400)
    assert result == 0
    assert isinstance(result, int)


def test_cost_of_a_zero_token_call_is_zero_not_unknown() -> None:
    """Zero tokens is a measurement. It must not be confused with an absent one."""
    assert cost_micros(AIUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0), 100, 400) == 0


def test_large_counts_stay_exact() -> None:
    usage = AIUsage(prompt_tokens=10_000_000, completion_tokens=10_000_000, total_tokens=20_000_000)
    assert cost_micros(usage, 100, 400) == 1_000_000 + 4_000_000


# ---------------------------------------------------------------------------------------
# Unknown degradation
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "usage",
    [
        AIUsage(),
        AIUsage(prompt_tokens=10),
        AIUsage(completion_tokens=10),
        AIUsage(total_tokens=10),
        AIUsage(prompt_tokens=10, total_tokens=10),
    ],
)
def test_a_missing_token_count_makes_cost_unknown(usage: AIUsage) -> None:
    """Prompt and completion are priced differently, so a known total cannot stand in."""
    assert cost_micros(usage, 100, 400) is None


@pytest.mark.parametrize("rates", [(None, 400), (100, None), (None, None), (-1, 400), (100, -1)])
def test_an_unusable_rate_makes_cost_unknown(rates: tuple[int | None, int | None]) -> None:
    usage = AIUsage(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000)
    assert cost_micros(usage, *rates) is None


@pytest.mark.parametrize(
    "value", [None, "120", 3.5, -1, True, False, [], {}, float("nan")]
)
def test_a_malformed_token_count_is_unknown_never_a_number(value: Any) -> None:
    sink = UsageSink()
    sink.record(prompt_tokens=value, completion_tokens=value, total_tokens=value)
    assert sink.usage == AIUsage()


def test_an_empty_sink_is_unknown_not_zero() -> None:
    usage = UsageSink().usage
    assert usage == AIUsage() and usage.is_unknown
    # None, not 0. A zero would read as "this call was free", which is a different claim.
    assert usage.prompt_tokens is None
    assert cost_micros(usage, 100, 400) is None


def test_zero_is_recorded_as_zero_and_is_not_unknown() -> None:
    sink = UsageSink()
    sink.record(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    assert sink.usage == AIUsage(0, 0, 0)
    assert not sink.usage.is_unknown


def test_fields_degrade_independently() -> None:
    sink = UsageSink()
    sink.record(prompt_tokens=10, completion_tokens="nonsense", total_tokens=42)
    assert sink.usage == AIUsage(prompt_tokens=10, completion_tokens=None, total_tokens=42)


def test_an_unreadable_response_makes_every_field_unknown() -> None:
    """A response that arrived consumed tokens; a missing count is not a count of nothing."""
    sink = UsageSink()
    sink.record(prompt_tokens=10, completion_tokens=2, total_tokens=12)
    sink.record_unreadable()
    assert sink.usage == AIUsage()


@pytest.mark.anyio
async def test_unpriced_model_logs_unknown_cost_with_known_tokens(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="eligicore.ai"):
        await AIService(MockAIProvider(), settings=Settings()).extract_resume(RESUME)
    assert field_of(caplog, "cost_micros") == "unknown"
    assert field_of(caplog, "total_tokens") != "unknown"


@pytest.mark.anyio
async def test_no_rate_is_shipped_in_source() -> None:
    """W8-H: default configuration prices nothing, so nothing is a guess."""
    assert Settings().ai_cost_rates == {}
    assert Settings().cost_rate_for("gemini", "gemini-2.0-flash") is None


@pytest.mark.anyio
async def test_provider_that_reports_no_usage_logs_unknown_throughout(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="eligicore.ai"):
        await AIService(MockAIProvider(report_usage=False), settings=priced()).extract_resume(
            RESUME
        )
    for name in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_micros"):
        assert field_of(caplog, name) == "unknown", name


# ---------------------------------------------------------------------------------------
# Accumulation across retries
# ---------------------------------------------------------------------------------------


def test_a_sink_sums_every_response_it_is_given() -> None:
    sink = UsageSink()
    for _ in range(3):
        sink.record(prompt_tokens=100, completion_tokens=10, total_tokens=110)
    assert sink.usage == AIUsage(prompt_tokens=300, completion_tokens=30, total_tokens=330)


def test_accumulated_cost_reflects_every_attempt_not_only_the_last() -> None:
    once, thrice = UsageSink(), UsageSink()
    once.record(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000)
    for _ in range(3):
        thrice.record(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000)
    assert cost_micros(thrice.usage, 100, 400) == 3 * cost_micros(once.usage, 100, 400)


def _gemini(handler: Any, *, max_retries: int = 2) -> GeminiFlashProvider:
    return GeminiFlashProvider(
        api_key="test-key-not-real",
        model="gemini-2.0-flash",
        api_base="https://generativelanguage.example.invalid/v1beta",
        timeout_seconds=5,
        max_retries=max_retries,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _reply(payload: dict[str, Any], usage: dict[str, Any] | None) -> httpx.Response:
    body: dict[str, Any] = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]
    }
    if usage is not None:
        body["usageMetadata"] = usage
    return httpx.Response(200, json=body)


RELATED = {"result": "RELATED", "confidence": "HIGH", "reason": "Adjacent disciplines."}
USAGE = {"promptTokenCount": 120, "candidatesTokenCount": 30, "totalTokenCount": 150}


@pytest.mark.anyio
async def test_usage_survives_two_failed_attempts_before_success() -> None:
    """The requirement: a third-attempt success still accounts for the call."""
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(503, json={"error": "unavailable"})
        return _reply(RELATED, USAGE)

    sink = UsageSink()
    result = await _gemini(handler).assess_field_relatedness(FIELD, ALLOWED, usage=sink)

    assert len(attempts) == 3
    assert result.result.value == "RELATED"
    assert sink.usage == AIUsage(prompt_tokens=120, completion_tokens=30, total_tokens=150)


@pytest.mark.anyio
async def test_failed_attempts_do_not_zero_or_invalidate_the_successful_one() -> None:
    """A 5xx carries no token count. It must not be recorded as an unreadable response."""

    calls: list[int] = []

    def counting(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500) if len(calls) == 1 else _reply(RELATED, USAGE)

    sink = UsageSink()
    await _gemini(counting).assess_field_relatedness(FIELD, ALLOWED, usage=sink)
    assert not sink.usage.is_unknown
    assert sink.usage.total_tokens == 150


@pytest.mark.anyio
async def test_tokens_are_accounted_even_when_the_reply_is_later_rejected() -> None:
    """A truncated reply still cost money. Unreported cost is hidden cost."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": []}}],
                "usageMetadata": USAGE,
            },
        )

    sink = UsageSink()
    with pytest.raises(AIResponseInvalidError):
        await _gemini(handler, max_retries=0).assess_field_relatedness(FIELD, ALLOWED, usage=sink)
    assert sink.usage.total_tokens == 150


@pytest.mark.anyio
async def test_a_reply_without_usage_metadata_is_unreadable_not_free() -> None:
    sink = UsageSink()
    await _gemini(lambda r: _reply(RELATED, None), max_retries=0).assess_field_relatedness(
        FIELD, ALLOWED, usage=sink
    )
    assert sink.usage == AIUsage()


@pytest.mark.anyio
async def test_a_malformed_usage_block_degrades_without_failing_the_call() -> None:
    sink = UsageSink()
    result = await _gemini(
        lambda r: _reply(RELATED, {"promptTokenCount": "many", "candidatesTokenCount": -3}),
        max_retries=0,
    ).assess_field_relatedness(FIELD, ALLOWED, usage=sink)
    assert result.result.value == "RELATED"
    assert sink.usage == AIUsage()


@pytest.mark.anyio
async def test_exhausted_retries_report_no_usage_rather_than_a_guess() -> None:
    sink = UsageSink()
    with pytest.raises(AIProviderUnavailableError):
        await _gemini(lambda r: httpx.Response(503)).assess_field_relatedness(
            FIELD, ALLOWED, usage=sink
        )
    assert sink.usage == AIUsage()


@pytest.mark.anyio
async def test_retry_semantics_are_unchanged_by_accounting() -> None:
    """A 4xx is still not retried; the cap is still max_retries + 1 attempts."""
    rejected: list[int] = []

    def reject(request: httpx.Request) -> httpx.Response:
        rejected.append(1)
        return httpx.Response(400, json={"error": "bad"})

    with pytest.raises(Exception):
        await _gemini(reject).assess_field_relatedness(FIELD, ALLOWED, usage=UsageSink())
    assert len(rejected) == 1

    attempts: list[int] = []

    def unavailable(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(503)

    with pytest.raises(AIProviderUnavailableError):
        await _gemini(unavailable, max_retries=2).assess_field_relatedness(
            FIELD, ALLOWED, usage=UsageSink()
        )
    assert len(attempts) == 3


# ---------------------------------------------------------------------------------------
# Inertness — accounting cannot change an outcome
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_broken_settings_lookup_does_not_break_a_working_call(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Exploding(Settings):
        def cost_rate_for(self, provider: str, model: str) -> Any:
            raise RuntimeError("configuration is on fire")

    with caplog.at_level(logging.INFO, logger="eligicore.ai"):
        result = await AIService(MockAIProvider(), settings=Exploding()).extract_resume(RESUME)

    assert result is not None
    assert field_of(caplog, "cost_micros") == "unknown"
    assert field_of(caplog, "outcome") == "success"


@pytest.mark.anyio
async def test_a_sink_that_raises_does_not_break_a_working_call(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Hostile(MockAIProvider):
        async def extract_resume(self, resume_text: str, *, usage: Any = None) -> Any:
            if usage is not None:
                usage.record_unreadable()
            return await super().extract_resume(resume_text)

    with caplog.at_level(logging.INFO, logger="eligicore.ai"):
        result = await AIService(Hostile(), settings=priced()).extract_resume(RESUME)

    assert result is not None
    assert field_of(caplog, "total_tokens") == "unknown"


@pytest.mark.anyio
async def test_accounting_appears_on_the_failure_path_too(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = MockAIProvider(fail_with=AIProviderUnavailableError("down"))
    with caplog.at_level(logging.INFO, logger="eligicore.ai"):
        with pytest.raises(AIProviderUnavailableError):
            await AIService(provider, settings=priced()).assess_field_relatedness(FIELD, ALLOWED)

    assert field_of(caplog, "outcome") == "error"
    for name in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_micros"):
        field_of(caplog, name)


# ---------------------------------------------------------------------------------------
# Concurrency — the reason a sink is per call
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_concurrent_calls_do_not_share_a_sink() -> None:
    """Relatedness fans out through asyncio.gather. Shared usage state would cross wires."""
    seen: list[int] = []

    class Recording(MockAIProvider):
        async def assess_field_relatedness(
            self, field_of_study: str, allowed_fields: list[str], *, usage: Any = None
        ) -> Any:
            seen.append(id(usage))
            await asyncio.sleep(0)
            usage.record(prompt_tokens=int(field_of_study), completion_tokens=1, total_tokens=2)
            return await super().assess_field_relatedness(
                field_of_study, allowed_fields, usage=None
            )

    service = AIService(Recording(), settings=priced())
    await asyncio.gather(*(service.assess_field_relatedness(str(n), ALLOWED) for n in (1, 2, 3)))

    assert len(set(seen)) == 3, "each concurrent call must receive its own sink"


@pytest.mark.anyio
async def test_a_provider_holds_no_usage_between_calls() -> None:
    """No last_usage attribute, however tempting: ADR-026 D3 rejects shared provider state."""
    provider = MockAIProvider()
    assert not [name for name in dir(provider) if "last_usage" in name]

    first, second = UsageSink(), UsageSink()
    await provider.extract_resume("a" * 400, usage=first)
    await provider.extract_resume("b" * 40, usage=second)
    assert first.usage.prompt_tokens == 100
    assert second.usage.prompt_tokens == 10


@pytest.mark.anyio
async def test_sequential_service_calls_report_their_own_usage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = AIService(MockAIProvider(), settings=priced())
    with caplog.at_level(logging.INFO, logger="eligicore.ai"):
        await service.extract_resume("a" * 400)
        await service.extract_resume("b" * 40)

    totals = [
        re.search(r"\btotal_tokens=(\S+)", r.getMessage()).group(1)  # type: ignore[union-attr]
        for r in caplog.records
        if "ai_call" in r.getMessage()
    ]
    assert totals == ["112", "22"], "a second call must not inherit the first call's totals"


# ---------------------------------------------------------------------------------------
# The mock's numbers are arithmetic, not measurements
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_mock_usage_is_deterministic() -> None:
    sinks = [UsageSink(), UsageSink()]
    for sink in sinks:
        await MockAIProvider().extract_resume(RESUME, usage=sink)
    assert sinks[0].usage == sinks[1].usage


def test_the_mock_is_unpriced_by_default() -> None:
    """So a synthetic token count can never surface as a cost figure by accident."""
    assert Settings().cost_rate_for("mock", "mock-deterministic-v1") is None


# ---------------------------------------------------------------------------------------
# Exact values through the service — closing the gap that let a field swap survive
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_every_logged_field_carries_its_own_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Each field must hold *its* number. Asserting only the total lets a swap through."""
    with caplog.at_level(logging.INFO, logger="eligicore.ai"):
        await AIService(MockAIProvider(), settings=priced()).extract_resume("x" * 400)

    # 400 chars -> 100 prompt tokens; completion is the mock's flat 12.
    assert field_of(caplog, "prompt_tokens") == "100"
    assert field_of(caplog, "completion_tokens") == "12"
    assert field_of(caplog, "total_tokens") == "112"
    # 100 * 100 // 1000 + 12 * 400 // 1000 = 10 + 4
    assert field_of(caplog, "cost_micros") == "14"


@pytest.mark.anyio
async def test_a_priced_model_logs_a_real_cost_not_unknown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Without this, a lookup that always missed would be indistinguishable from working."""
    with caplog.at_level(logging.INFO, logger="eligicore.ai"):
        await AIService(MockAIProvider(), settings=priced()).extract_resume("x" * 4000)

    cost = field_of(caplog, "cost_micros")
    assert cost != "unknown"
    assert int(cost) == 1000 * 100 // 1000 + 12 * 400 // 1000


@pytest.mark.anyio
async def test_cost_tracks_the_configured_rate(caplog: pytest.LogCaptureFixture) -> None:
    """Doubling the prompt rate doubles the prompt half of the bill."""
    costs: list[int] = []
    for prompt_rate in (100, 200):
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="eligicore.ai"):
            await AIService(
                MockAIProvider(), settings=priced(prompt=prompt_rate, completion=0)
            ).extract_resume("x" * 4000)
        costs.append(int(field_of(caplog, "cost_micros")))
    assert costs[1] == 2 * costs[0] != 0


@pytest.mark.anyio
async def test_relatedness_logs_the_exact_synthetic_counts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Pins that the mock measures the whole relatedness input, not just part of it."""
    field, allowed = "A" * 40, ["B" * 40]
    with caplog.at_level(logging.INFO, logger="eligicore.ai"):
        await AIService(MockAIProvider(), settings=priced()).assess_field_relatedness(
            field, allowed
        )
    assert field_of(caplog, "prompt_tokens") == str((40 + 40) // 4)
    assert field_of(caplog, "completion_tokens") == "12"


# ---------------------------------------------------------------------------------------
# Rate lookup — closing the gap that let a key swap survive
# ---------------------------------------------------------------------------------------


def test_the_rate_key_is_provider_then_model_in_that_order() -> None:
    rate = ModelCostRate(prompt_micros_per_1k=1, completion_micros_per_1k=2)
    settings = Settings(ai_cost_rates={"alpha:beta": rate})
    assert settings.cost_rate_for("alpha", "beta") == rate
    assert settings.cost_rate_for("beta", "alpha") is None
    assert settings.cost_rate_for("alpha", "") is None
    assert settings.cost_rate_for("alpha", "beta2") is None


def test_a_rate_for_one_model_does_not_price_another() -> None:
    settings = priced()
    assert settings.cost_rate_for("mock", "mock-deterministic-v1") is not None
    assert settings.cost_rate_for("mock", "mock-deterministic-v2") is None
    assert settings.cost_rate_for("gemini", "mock-deterministic-v1") is None


@pytest.mark.parametrize("bad", [-1, -1000])
def test_a_negative_rate_is_refused_by_configuration(bad: int) -> None:
    """Rejected at the boundary, not merely survived by the arithmetic downstream."""
    with pytest.raises(ValueError):
        ModelCostRate(prompt_micros_per_1k=bad, completion_micros_per_1k=1)
    with pytest.raises(ValueError):
        ModelCostRate(prompt_micros_per_1k=1, completion_micros_per_1k=bad)


def test_a_rate_rejects_unknown_keys_and_is_frozen() -> None:
    with pytest.raises(ValueError):
        ModelCostRate(prompt_micros_per_1k=1, completion_micros_per_1k=1, currency="USD")
    rate = ModelCostRate(prompt_micros_per_1k=1, completion_micros_per_1k=1)
    with pytest.raises(ValueError):
        rate.prompt_micros_per_1k = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------------------
# is_unknown is about *all* fields
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "usage",
    [
        AIUsage(prompt_tokens=1),
        AIUsage(completion_tokens=1),
        AIUsage(total_tokens=1),
        AIUsage(prompt_tokens=0),
    ],
)
def test_partial_usage_is_not_unknown(usage: AIUsage) -> None:
    """One known field means something was learned; "unknown" would overstate the loss."""
    assert not usage.is_unknown


def test_only_a_wholly_empty_usage_is_unknown() -> None:
    assert AIUsage().is_unknown
    assert not AIUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0).is_unknown


# ---------------------------------------------------------------------------------------
# Gemini's reader, directly
# ---------------------------------------------------------------------------------------


def test_record_usage_marks_a_missing_metadata_block_unreadable() -> None:
    """Not merely "records nothing": a prior attempt's total must be invalidated too."""
    from app.ai.providers.gemini import _record_usage

    sink = UsageSink()
    sink.record(prompt_tokens=10, completion_tokens=2, total_tokens=12)
    _record_usage(sink, {"candidates": []})
    assert sink.usage == AIUsage()


@pytest.mark.parametrize("metadata", [None, "none", 7, [], {"promptTokenCount": None}])
def test_record_usage_survives_any_shape_of_metadata(metadata: Any) -> None:
    from app.ai.providers.gemini import _record_usage

    sink = UsageSink()
    _record_usage(sink, {"usageMetadata": metadata} if metadata is not None else {})
    assert sink.usage == AIUsage()


def test_record_usage_without_a_sink_does_nothing() -> None:
    from app.ai.providers.gemini import _record_usage

    _record_usage(None, {"usageMetadata": USAGE})


@pytest.mark.anyio
async def test_gemini_resume_extraction_reports_usage_too() -> None:
    """Both instrumented operations must be wired, not just the one with more tests."""
    payload = {"name": "Test Candidate", "skills": ["Python"], "field_confidence": {}}
    sink = UsageSink()
    await _gemini(lambda r: _reply(payload, USAGE), max_retries=0).extract_resume(
        RESUME, usage=sink
    )
    assert sink.usage == AIUsage(prompt_tokens=120, completion_tokens=30, total_tokens=150)
