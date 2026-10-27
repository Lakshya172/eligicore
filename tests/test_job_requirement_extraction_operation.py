"""ADR-030 Step 7: the job-requirement extraction provider operation (D13) and its mock (D14).

The operation exists and is reachable from nothing in production. These tests pin:

* the signature as the privacy boundary — a description and an output-only usage sink;
* the mock as silent by default, and configurable only by a test;
* proposals as untrusted — whatever a provider returns still has to pass the verifier;
* the literal zero-call guarantee — ingestion, derivation and evaluation never reach it;
* Gemini failing closed with no network call until Step 8;
* ADR-026 accounting on the new operation, with no description or proposal in any log.

Every provider and network assertion uses a mock, a spy or ``httpx.MockTransport``.
Nothing here can reach a real provider.
"""

from __future__ import annotations

import ast
import inspect
import logging
import pathlib
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.ai.ai_service import AIService, build_provider
from app.ai.errors import AIProviderUnavailableError, AIResponseInvalidError
from app.ai.providers.base import AIProvider
from app.ai.providers.gemini import GeminiFlashProvider
from app.ai.providers.mock import MockAIProvider
from app.ai.usage import UsageSink
from app.config import AIProviderName, Settings
from app.database import Base
from app.models.extracted_requirement import ExtractedRequirement
from app.schemas.candidate import Confidence, GradeScale
from app.schemas.eligibility import RequirementType
from app.schemas.extraction import ExtractionProposal, MinCgpaValue, RequirementStrength
from app.services.job_ingestion import ingest_source
from app.services.requirement_verifier import verify_proposals
from tests.test_derived_requirement_wiring import (  # noqa: F401 - fixtures
    CGPA_ONLY,
    FULL,
    NO_STRUCTURED,
    check,
    profile,
    reads_enabled,
    recommendations,
    store,
)
from tests.test_job_ingestion import FakeAdapter, make_raw

DESCRIPTION_MARKER = "JOB-DESCRIPTION-MARKER-4c"
EVIDENCE_MARKER = "Eligibility: minimum CGPA 8.0/10 required."
RATED = Settings(
    ai_cost_rates={
        "mock:mock-deterministic-v1": {"prompt_micros_per_1k": 75, "completion_micros_per_1k": 300}
    }
)


def proposal(
    minimum: float = 8.0,
    evidence: str = EVIDENCE_MARKER,
    **overrides: Any,
) -> ExtractionProposal:
    base: dict[str, Any] = {
        "requirement_type": RequirementType.MIN_CGPA,
        "value": MinCgpaValue(min_cgpa=minimum, min_cgpa_scale=GradeScale.SCALE_10),
        "evidence_text": evidence,
        "extractor": "test.mock",
        "extractor_version": "1",
        "provider": "mock",
        "model": "mock-deterministic-v1",
    }
    base.update(overrides)
    return ExtractionProposal(**base)


def gemini(handler: Any = None) -> tuple[GeminiFlashProvider, list[httpx.Request]]:
    """A Gemini provider whose only transport records requests and refuses them."""
    seen: list[httpx.Request] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        raise AssertionError("Gemini made a network request")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler or refuse))
    provider = GeminiFlashProvider(
        api_key="test-placeholder-not-a-key",
        model="gemini-test-model",
        api_base="https://gemini.invalid",
        timeout_seconds=1.0,
        max_retries=0,
        client=client,
    )
    return provider, seen


# ---------------------------------------------------------------------------------------
# D13 — the signature is the privacy boundary
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("cls", [AIProvider, MockAIProvider, GeminiFlashProvider])
def test_the_operation_takes_a_description_and_an_output_only_sink(cls: type) -> None:
    parameters = inspect.signature(cls.extract_job_requirements).parameters
    assert list(parameters) == ["self", "description", "usage"]
    assert parameters["usage"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["usage"].default is None


def test_the_service_operation_takes_only_a_description() -> None:
    assert list(inspect.signature(AIService.extract_job_requirements).parameters) == [
        "self", "description",
    ]


def test_every_provider_must_declare_the_operation() -> None:
    assert "extract_job_requirements" in AIProvider.__abstractmethods__
    assert not MockAIProvider.__abstractmethods__
    assert not GeminiFlashProvider.__abstractmethods__


def test_the_service_never_routes_job_text_through_resume_extraction() -> None:
    source = pathlib.Path(inspect.getfile(AIService)).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "extract_job_requirements":
            called = {
                getattr(call.func, "attr", None)
                for call in ast.walk(node) if isinstance(call, ast.Call)
            }
            assert "extract_resume" not in called
            assert "extract_job_requirements" in called
            return
    raise AssertionError("AIService.extract_job_requirements not found")


# ---------------------------------------------------------------------------------------
# D14 — the mock is silent by default
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_default_provider_extracts_nothing() -> None:
    provider = build_provider(Settings())
    assert isinstance(provider, MockAIProvider)
    assert await provider.extract_job_requirements(FULL) == []
    assert await AIService(provider).extract_job_requirements(FULL) == []


@pytest.mark.anyio
async def test_the_mock_records_lengths_only_and_never_extracts_a_resume() -> None:
    mock = MockAIProvider()
    text = f"{CGPA_ONLY} {DESCRIPTION_MARKER}"
    assert await mock.extract_job_requirements(text) == []

    assert mock.job_requirement_call_count == 1
    assert mock.received_description_lengths == [len(text)]
    assert mock.call_count == 0, "job text must never reach resume extraction"
    assert DESCRIPTION_MARKER not in repr(vars(mock))


@pytest.mark.anyio
async def test_configured_proposals_are_returned_as_a_fresh_list() -> None:
    configured = [proposal(), proposal(minimum=9.0)]
    mock = MockAIProvider(return_job_requirements=configured)

    first = await mock.extract_job_requirements(CGPA_ONLY)
    first.clear()
    assert await mock.extract_job_requirements(CGPA_ONLY) == configured


# ---------------------------------------------------------------------------------------
# Proposals are untrusted: the verifier still decides
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_provider_cannot_bypass_the_verifier() -> None:
    honest = proposal(reported_confidence=Confidence.LOW)
    fabricated = proposal(evidence="A minimum CGPA of 9.5/10 is mandatory.",
                          reported_confidence=Confidence.HIGH)
    mismatched = proposal(minimum=9.0, reported_confidence=Confidence.HIGH)
    preferred = proposal(reported_strength=RequirementStrength.PREFERRED)
    mock = MockAIProvider(return_job_requirements=[fabricated, mismatched, preferred, honest])

    returned = await AIService(mock).extract_job_requirements(CGPA_ONLY)
    verification = verify_proposals(returned, CGPA_ONLY)

    assert len(returned) == 4
    assert [o.verified for o in verification.outcomes] == [False, False, False, True]
    (verified,) = verification.verified
    assert verified.value.min_cgpa == 8.0 and verified.evidence_text == EVIDENCE_MARKER


# ---------------------------------------------------------------------------------------
# The literal zero-call guarantee (D14, D21)
# ---------------------------------------------------------------------------------------


@pytest.fixture
def forbid_operation(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make every implementation of the operation fail the test if it is reached."""
    reached: list[str] = []

    def install(owner: type) -> None:
        async def forbidden(*_args: Any, **_kwargs: Any) -> Any:
            reached.append(owner.__name__)
            raise AssertionError(f"{owner.__name__}.extract_job_requirements was called")
        monkeypatch.setattr(owner, "extract_job_requirements", forbidden)

    for owner in (MockAIProvider, GeminiFlashProvider, AIService):
        install(owner)
    return reached


@pytest.mark.parametrize("enabled", [False, True], ids=["extraction-off", "extraction-on"])
def test_ingestion_never_calls_the_operation(forbid_operation: list[str], enabled: bool) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        ingest_source(
            session,
            FakeAdapter([make_raw(source_job_id="a", description=FULL, **NO_STRUCTURED)]),
            settings=Settings(extraction_enabled=enabled),
        )
        rows = session.execute(select(ExtractedRequirement)).scalars().all()
    # The deterministic path still derives when enabled; the provider path is never reached.
    assert len(rows) == (3 if enabled else 0)
    assert forbid_operation == []


def test_evaluation_never_calls_the_operation(
    store: Any, reads_enabled: None, forbid_operation: list[str]
) -> None:
    store.ingest(make_raw(source_job_id="a", description=CGPA_ONLY, **NO_STRUCTURED))
    ids = store.ids("a")
    assert check(store, ids, profile(cgpa=7.0))[ids[0]]["eligibility_state"] == "NEEDS_REVIEW"
    recommendations(store, ids, profile(cgpa=7.0))
    assert forbid_operation == []


def test_no_production_module_calls_the_operation() -> None:
    """Step 7 stops at the operation and its mock; nothing outside ``app/ai`` names it."""
    callers = sorted(
        path.as_posix()
        for path in pathlib.Path("app").rglob("*.py")
        if "extract_job_requirements" in path.read_text(encoding="utf-8")
        and not path.as_posix().startswith("app/ai/")
    )
    assert callers == []


# ---------------------------------------------------------------------------------------
# Gemini fails closed with no network call until Step 8
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gemini_fails_closed_without_a_request(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, seen = gemini()

    async def no_post(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Gemini built or sent a request")

    monkeypatch.setattr(GeminiFlashProvider, "_post_with_retries", no_post)
    sink = UsageSink()
    with pytest.raises(AIProviderUnavailableError):
        await provider.extract_job_requirements(FULL, usage=sink)

    assert seen == []
    assert sink.usage == UsageSink().usage, "nothing was reported because nothing was called"


@pytest.mark.anyio
async def test_selecting_gemini_degrades_honestly_through_the_service(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider, seen = gemini()
    with caplog.at_level(logging.DEBUG, logger="eligicore.ai"):
        with pytest.raises(AIProviderUnavailableError):
            await AIService(provider).extract_job_requirements(f"{FULL} {DESCRIPTION_MARKER}")

    assert seen == []
    assert "operation=extract_job_requirements outcome=error " in caplog.text
    assert "error_type=AIProviderUnavailableError" in caplog.text
    assert "prompt_tokens=unknown" in caplog.text
    assert DESCRIPTION_MARKER not in caplog.text


def test_gemini_is_still_selectable_and_concrete() -> None:
    provider = build_provider(Settings(ai_provider=AIProviderName.GEMINI,
                                       gemini_api_key="test-placeholder-not-a-key"))
    assert isinstance(provider, GeminiFlashProvider)


# ---------------------------------------------------------------------------------------
# ADR-026 accounting, and nothing but counts in the log
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_success_is_accounted_and_logs_no_content(caplog: pytest.LogCaptureFixture) -> None:
    text = f"{CGPA_ONLY} {DESCRIPTION_MARKER}"
    service = AIService(MockAIProvider(return_job_requirements=[proposal()]), settings=RATED)
    with caplog.at_level(logging.DEBUG):
        await service.extract_job_requirements(text)

    (line,) = [r.getMessage() for r in caplog.records
               if "operation=extract_job_requirements" in r.getMessage()]
    assert f"outcome=success input_chars={len(text)} proposals=1 " in line
    assert "prompt_tokens=" in line and "prompt_tokens=unknown" not in line
    assert "cost_micros=" in line and "cost_micros=unknown" not in line
    for secret in (DESCRIPTION_MARKER, EVIDENCE_MARKER, "8.0", "SCALE_10", "MIN_CGPA"):
        assert secret not in caplog.text


@pytest.mark.anyio
async def test_a_provider_without_usage_reports_unknown(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="eligicore.ai"):
        await AIService(MockAIProvider(report_usage=False), settings=RATED
                        ).extract_job_requirements(CGPA_ONLY)
    assert ("prompt_tokens=unknown completion_tokens=unknown total_tokens=unknown "
            "cost_micros=unknown") in caplog.text


@pytest.mark.anyio
async def test_the_failure_path_is_accounted_too(caplog: pytest.LogCaptureFixture) -> None:
    service = AIService(MockAIProvider(fail_with=AIProviderUnavailableError("down")),
                        settings=RATED)
    with caplog.at_level(logging.WARNING, logger="eligicore.ai"):
        with pytest.raises(AIProviderUnavailableError):
            await service.extract_job_requirements(f"{CGPA_ONLY} {DESCRIPTION_MARKER}")
    assert "outcome=error error_type=AIProviderUnavailableError" in caplog.text
    assert "prompt_tokens=unknown" not in caplog.text, "tokens consumed before failing count"
    assert DESCRIPTION_MARKER not in caplog.text


@pytest.mark.anyio
async def test_an_invalid_reply_is_refused() -> None:
    with pytest.raises(AIResponseInvalidError):
        await AIService(MockAIProvider(raise_invalid_response=True)).extract_job_requirements(FULL)


@pytest.mark.anyio
async def test_an_unvalidated_reply_is_refused_by_the_service() -> None:
    class Sloppy(MockAIProvider):
        async def extract_job_requirements(self, description: str, *, usage: Any = None) -> Any:
            return [{"requirement_type": "MIN_CGPA", "evidence_text": "made up"}]

    with pytest.raises(AIResponseInvalidError):
        await AIService(Sloppy()).extract_job_requirements(FULL)


def test_extraction_stays_disabled_by_default() -> None:
    assert Settings().extraction_enabled is False
    assert Settings().ai_provider is AIProviderName.MOCK
