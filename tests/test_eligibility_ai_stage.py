"""AI ambiguity resolution for eligibility: precedence, semantics, de-duplication, privacy.

These tests exist to prove one thing above all: **AI cannot reach a job the deterministic
engine has already decided** (INV-2, ADR-019). Every such assertion is on a literal provider
call count, or on whether a provider was even built — never only on the output, which would
pass even if AI ran and happened to agree.

No network, no API key. All data is obviously synthetic.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest

from app.ai.ai_service import AIService, get_lazy_ai_service
from app.ai.errors import AIConfigurationError, AIProviderUnavailableError
from app.ai.providers.base import AIProvider
from app.ai.providers.gemini import GeminiFlashProvider
from app.ai.providers.mock import MockAIProvider
from app.database import Base
from app.main import app
from app.schemas.candidate import CandidateProfile, Confidence, DegreeLevel
from app.schemas.eligibility import (
    EligibilityState as E,
    EvaluationMethod,
    FieldRelatednessAssessment,
    JobEligibility,
    ReasonCode,
    RequirementStatus,
    RequirementType,
)
from app.schemas.job import JobRead
from app.services.eligibility_ai import (
    MAX_AI_CONFIDENCE,
    ai_inputs,
    apply_assessment,
    check_eligibility_with_ai,
)
from app.services.eligibility_engine import evaluate_requirements
from tests.conftest import ALLOWED_OPERATIONAL_TABLES
from tests.test_eligibility_endpoint import CHECK_URL, Catalogue, catalogue  # noqa: F401
from tests.test_eligibility_engine import edu, make_job, make_profile

P, F, U = RequirementStatus.PASS, RequirementStatus.FAIL, RequirementStatus.UNKNOWN
AI = EvaluationMethod.AI_REASONING

IT = "Information Technology"
CS_FIELDS = ["Computer Science", "Computer Engineering"]

# Privacy markers, planted in every personal field of the profile.
CID = "AI-CID-MARKER-51f0"
NAME = "Aimarker Personname"
EMAIL = "ai.marker.51f0@example.com"
PHONE = "+19990005151"
RESUME = "AI-RESUME-MARKER-51f0"
INSTITUTION = "Aimarker Institute"
SKILL = "AiMarkerSkill"
CGPA = 8.63
YEAR = 2027


class SpyProvider(AIProvider):
    """Records the exact arguments of every relatedness call, and every constructor call."""

    name = "spy"
    constructed = 0

    def __init__(self, answer: FieldRelatednessAssessment | None = None, *, fail: bool = False) -> None:
        SpyProvider.constructed += 1
        self.calls: list[tuple[str, list[str]]] = []
        self.answer = answer or FieldRelatednessAssessment(
            result="RELATED", confidence="MEDIUM", reason="Closely related disciplines."
        )
        self.fail = fail

    @property
    def model(self) -> str:
        return "spy-1"

    async def extract_resume(self, resume_text: str) -> Any:
        raise AssertionError("eligibility must never call resume extraction")

    async def assess_field_relatedness(
        self, field_of_study: str, allowed_fields: list[str]
    ) -> FieldRelatednessAssessment:
        self.calls.append((field_of_study, list(allowed_fields)))
        if self.fail:
            raise AIProviderUnavailableError("spy failure")
        return self.answer


def answer(result: str, confidence: str = "MEDIUM", reason: str = "Synthetic reason.") -> FieldRelatednessAssessment:
    return FieldRelatednessAssessment(result=result, confidence=confidence, reason=reason)


def private_profile(**education: Any) -> CandidateProfile:
    entry = edu(field_of_study=IT, cgpa=CGPA, grad_year=YEAR, institution=INSTITUTION)
    entry.update(education)
    return CandidateProfile.model_validate(
        {
            "candidate_id": CID,
            "name": NAME,
            "email": EMAIL,
            "phone": PHONE,
            "education": [entry],
            "skills": [SKILL],
            "backlogs": 0,
            "resume_raw_text": RESUME,
        }
    )


async def run(
    profile: CandidateProfile, jobs: list[JobRead], provider: AIProvider
) -> dict[str, JobEligibility]:
    by_id = {job.id: job for job in jobs}
    response = await check_eligibility_with_ai(profile, list(by_id), by_id, AIService(provider))
    return {result.job_id: result for result in response.results}


def field_entry(result: JobEligibility):  # type: ignore[no-untyped-def]
    (entry,) = [e for e in result.requirement_breakdown if e.requirement_type is RequirementType.ALLOWED_FIELDS]
    return entry


AMBIGUOUS = dict(id="ambiguous", allowed_fields=CS_FIELDS, min_cgpa=7.0, min_cgpa_scale="SCALE_10")


# ---------------------------------------------------------------------------------------
# Deterministic precedence (items 1–3)
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    "hard_failure",
    [
        {"min_cgpa": 9.5, "min_cgpa_scale": "SCALE_10"},
        {"min_grad_year": 2030},
        {"max_backlogs": 0},
        {"min_degree_level": DegreeLevel.MASTERS},
    ],
)
async def test_hard_failure_is_not_eligible_with_zero_ai_calls(hard_failure: dict[str, Any]) -> None:
    job = make_job(id="hard", allowed_fields=CS_FIELDS, **hard_failure)
    profile = make_profile([edu(field_of_study=IT, grad_year=2027)], backlogs=3)
    provider = MockAIProvider(return_relatedness=answer("RELATED", "HIGH"))

    results = await run(profile, [job], provider)

    assert results["hard"].eligibility_state is E.NOT_ELIGIBLE
    assert provider.relatedness_call_count == 0
    assert field_entry(results["hard"]).reason_code is ReasonCode.SKIPPED_AFTER_HARD_FAILURE


@pytest.mark.anyio
async def test_hard_failure_generates_no_ai_input_at_all() -> None:
    job = make_job(id="hard", allowed_fields=CS_FIELDS, min_cgpa=9.5, min_cgpa_scale="SCALE_10")
    profile = private_profile()
    breakdown = evaluate_requirements(profile, job)

    assert list(ai_inputs(job, breakdown)) == []
    spy = SpyProvider()
    await run(profile, [job], spy)
    assert spy.calls == []


@pytest.mark.anyio
async def test_hard_failure_never_constructs_a_provider() -> None:
    built: list[int] = []

    def builder() -> AIProvider:
        built.append(1)
        return MockAIProvider(return_relatedness=answer("RELATED"))

    job = make_job(id="hard", allowed_fields=CS_FIELDS, min_cgpa=9.5, min_cgpa_scale="SCALE_10")
    service = AIService(builder=builder)
    response = await check_eligibility_with_ai(private_profile(), ["hard"], {"hard": job}, service)

    assert response.results[0].eligibility_state is E.NOT_ELIGIBLE
    assert built == [] and service.provider_built is False


@pytest.mark.anyio
async def test_ai_pass_cannot_rescue_a_hard_failure_even_when_forced() -> None:
    """Even a provider that would say RELATED with HIGH confidence is never asked."""
    job = make_job(id="hard", allowed_fields=CS_FIELDS, max_backlogs=0)
    provider = MockAIProvider(return_relatedness=answer("RELATED", "HIGH"))
    results = await run(make_profile([edu(field_of_study=IT)], backlogs=1), [job], provider)
    assert results["hard"].eligibility_state is E.NOT_ELIGIBLE
    assert provider.relatedness_call_count == 0


# ---------------------------------------------------------------------------------------
# No-AI paths (items 4, 5, 14, 15)
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("field", ["Computer Science", "  computer   SCIENCE ", "COMPUTER ENGINEERING"])
async def test_exact_normalized_match_is_deterministic_pass_with_zero_ai_calls(field: str) -> None:
    provider = MockAIProvider(return_relatedness=answer("NOT_RELATED", "HIGH"))
    results = await run(make_profile([edu(field_of_study=field)]), [make_job(**AMBIGUOUS)], provider)

    entry = field_entry(results["ambiguous"])
    assert (entry.status, entry.method, entry.reason_code) == (P, EvaluationMethod.DETERMINISTIC, ReasonCode.EXACT_FIELD_MATCH)
    assert results["ambiguous"].eligibility_state is E.ELIGIBLE
    assert provider.relatedness_call_count == 0


@pytest.mark.anyio
async def test_missing_candidate_field_is_unknown_with_zero_ai_calls() -> None:
    provider = MockAIProvider(return_relatedness=answer("RELATED", "HIGH"))
    results = await run(make_profile([edu(field_of_study=None)]), [make_job(**AMBIGUOUS)], provider)

    entry = field_entry(results["ambiguous"])
    assert (entry.status, entry.reason_code) == (U, ReasonCode.MISSING_CANDIDATE_VALUE)
    assert results["ambiguous"].eligibility_state is E.NEEDS_REVIEW
    assert provider.relatedness_call_count == 0


@pytest.mark.anyio
@pytest.mark.parametrize("allowed", [[], ["", "   "]])
async def test_empty_allowed_fields_is_omitted_with_zero_ai_calls(allowed: list[str]) -> None:
    """Ruling C-14: no field restriction — omitted, not UNKNOWN, never sent to AI."""
    provider = MockAIProvider(return_relatedness=answer("NOT_RELATED", "HIGH"))
    job = make_job(id="open", allowed_fields=allowed)
    results = await run(make_profile([edu(field_of_study=IT)]), [job], provider)

    assert results["open"].requirement_breakdown == []
    assert results["open"].eligibility_state is E.ELIGIBLE
    assert provider.relatedness_call_count == 0


@pytest.mark.anyio
async def test_requests_needing_no_ai_never_construct_a_provider() -> None:
    built: list[int] = []

    def builder() -> AIProvider:
        built.append(1)
        raise AIConfigurationError("would have been built")

    jobs = {
        "hard": make_job(id="hard", allowed_fields=CS_FIELDS, max_backlogs=0),
        "exact": make_job(id="exact", allowed_fields=[IT]),
        "open": make_job(id="open"),
    }
    service = AIService(builder=builder)
    response = await check_eligibility_with_ai(
        make_profile([edu(field_of_study=IT)], backlogs=2), list(jobs), jobs, service
    )
    assert [r.eligibility_state for r in response.results] == [E.NOT_ELIGIBLE, E.ELIGIBLE, E.ELIGIBLE]
    assert built == []

    missing = await check_eligibility_with_ai(
        make_profile([edu(field_of_study=None)]), ["amb"], {"amb": make_job(id="amb", allowed_fields=CS_FIELDS)}, service
    )
    assert missing.results[0].eligibility_state is E.UNKNOWN
    assert built == []


# ---------------------------------------------------------------------------------------
# AI ambiguity semantics (items 6–13)
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_related_field_is_ai_pass() -> None:
    provider = MockAIProvider(return_relatedness=answer("RELATED", "MEDIUM", "IT and CS overlap."))
    results = await run(make_profile([edu(field_of_study=IT)]), [make_job(**AMBIGUOUS)], provider)

    entry = field_entry(results["ambiguous"])
    assert (entry.status, entry.method, entry.reason_code) == (P, AI, ReasonCode.AI_FIELD_RELATED)
    assert entry.confidence is Confidence.MEDIUM
    assert "IT and CS overlap." in entry.note and "not a deterministic check" in entry.note
    assert provider.relatedness_call_count == 1


@pytest.mark.anyio
async def test_ai_pass_with_all_else_passing_is_likely_eligible_never_eligible() -> None:
    provider = MockAIProvider(return_relatedness=answer("RELATED", "HIGH"))
    job = make_job(**AMBIGUOUS, min_grad_year=2026, max_grad_year=2027, max_backlogs=0,
                   min_degree_level=DegreeLevel.BACHELORS)
    results = await run(make_profile([edu(field_of_study=IT)]), [job], provider)

    verdict = results["ambiguous"]
    assert verdict.eligibility_state is E.LIKELY_ELIGIBLE
    assert [e.status for e in verdict.requirement_breakdown] == [P, P, P, P, P]
    assert verdict.summary.startswith("Likely eligible")


@pytest.mark.anyio
async def test_ai_fail_is_requirement_fail_but_verdict_needs_review() -> None:
    provider = MockAIProvider(return_relatedness=answer("NOT_RELATED", "HIGH", "Different disciplines."))
    results = await run(make_profile([edu(field_of_study="Mechanical Engineering")]), [make_job(**AMBIGUOUS)], provider)

    entry = field_entry(results["ambiguous"])
    assert (entry.status, entry.method, entry.reason_code) == (F, AI, ReasonCode.AI_FIELD_NOT_RELATED)
    assert entry.confidence is Confidence.MEDIUM
    assert "cannot by itself make the candidate ineligible" in entry.note
    assert results["ambiguous"].eligibility_state is E.NEEDS_REVIEW


@pytest.mark.anyio
@pytest.mark.parametrize("confidence", ["HIGH", "MEDIUM"])
@pytest.mark.parametrize(
    "job_overrides",
    [
        {},  # the field requirement is the only one
        {"min_cgpa": 7.0, "min_cgpa_scale": "SCALE_10"},  # plus a deterministic PASS
        {"min_cgpa": 7.0},  # plus a deterministic UNKNOWN (no job scale)
    ],
)
async def test_ai_fail_can_never_produce_not_eligible(confidence: str, job_overrides: dict[str, Any]) -> None:
    provider = MockAIProvider(return_relatedness=answer("NOT_RELATED", confidence))
    job = make_job(id="j", allowed_fields=CS_FIELDS, **job_overrides)
    results = await run(make_profile([edu(field_of_study="Botany")]), [job], provider)

    assert results["j"].eligibility_state is E.NEEDS_REVIEW
    assert results["j"].eligibility_state is not E.NOT_ELIGIBLE
    assert provider.relatedness_call_count == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("assessment", "reason"),
    [
        (answer("UNCERTAIN", "HIGH"), ReasonCode.AI_ASSESSMENT_INCONCLUSIVE),
        (answer("UNCERTAIN", "LOW"), ReasonCode.AI_ASSESSMENT_INCONCLUSIVE),
        (answer("RELATED", "LOW"), ReasonCode.AI_ASSESSMENT_INCONCLUSIVE),  # low confidence
        (answer("NOT_RELATED", "LOW"), ReasonCode.AI_ASSESSMENT_INCONCLUSIVE),
    ],
)
async def test_uncertain_or_low_confidence_is_unknown(assessment: FieldRelatednessAssessment, reason: ReasonCode) -> None:
    provider = MockAIProvider(return_relatedness=assessment)
    results = await run(make_profile([edu(field_of_study=IT)]), [make_job(**AMBIGUOUS)], provider)

    entry = field_entry(results["ambiguous"])
    assert (entry.status, entry.reason_code, entry.confidence) == (U, reason, Confidence.LOW)
    assert results["ambiguous"].eligibility_state is E.NEEDS_REVIEW  # CGPA passed; field unknown


@pytest.mark.anyio
async def test_ai_unknown_on_the_only_requirement_is_unknown_verdict() -> None:
    results = await run(make_profile([edu(field_of_study=IT)]), [make_job(id="only", allowed_fields=CS_FIELDS)], MockAIProvider())
    assert results["only"].eligibility_state is E.UNKNOWN


@pytest.mark.anyio
@pytest.mark.parametrize(
    "provider",
    [
        MockAIProvider(fail_with=AIProviderUnavailableError("PROVIDER-ERROR-TEXT-MARKER")),
        MockAIProvider(raise_invalid_response=True),
    ],
    ids=["provider_error", "invalid_response"],
)
async def test_provider_failure_fails_closed_to_unknown(provider: MockAIProvider) -> None:
    results = await run(make_profile([edu(field_of_study=IT)]), [make_job(**AMBIGUOUS)], provider)

    entry = field_entry(results["ambiguous"])
    assert (entry.status, entry.method, entry.reason_code) == (U, EvaluationMethod.DETERMINISTIC, ReasonCode.AI_ASSESSMENT_UNAVAILABLE)
    assert entry.confidence is Confidence.LOW
    assert "PROVIDER-ERROR-TEXT-MARKER" not in entry.model_dump_json()
    assert results["ambiguous"].eligibility_state is E.NEEDS_REVIEW


@pytest.mark.anyio
async def test_provider_construction_failure_fails_closed_to_unknown() -> None:
    def builder() -> AIProvider:
        raise AIConfigurationError("CONFIG-DETAIL-MARKER missing key")

    service = AIService(builder=builder)
    job = make_job(**AMBIGUOUS)
    response = await check_eligibility_with_ai(make_profile([edu(field_of_study=IT)]), [job.id], {job.id: job}, service)

    entry = field_entry(response.results[0])
    assert entry.reason_code is ReasonCode.AI_ASSESSMENT_UNAVAILABLE
    assert "CONFIG-DETAIL-MARKER" not in response.model_dump_json()


@pytest.mark.anyio
async def test_high_confidence_is_capped_at_medium() -> None:
    assert MAX_AI_CONFIDENCE is Confidence.MEDIUM
    for result in ("RELATED", "NOT_RELATED"):
        provider = MockAIProvider(return_relatedness=answer(result, "HIGH"))
        results = await run(make_profile([edu(field_of_study=IT)]), [make_job(**AMBIGUOUS)], provider)
        assert field_entry(results["ambiguous"]).confidence is Confidence.MEDIUM


def test_apply_assessment_never_raises_confidence_or_invents_certainty() -> None:
    job = make_job(**AMBIGUOUS)
    (_, ambiguous) = evaluate_requirements(make_profile([edu(field_of_study=IT)]), job)
    for result in ("RELATED", "NOT_RELATED", "UNCERTAIN"):
        for confidence in ("HIGH", "MEDIUM", "LOW"):
            entry = apply_assessment(ambiguous, answer(result, confidence))
            assert entry.confidence is not Confidence.HIGH
            if confidence == "LOW" or result == "UNCERTAIN":
                assert entry.status is U
    assert apply_assessment(ambiguous, None).status is U


# ---------------------------------------------------------------------------------------
# De-duplication (item 16)
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_duplicate_ambiguity_inputs_cause_one_provider_call() -> None:
    jobs = [
        make_job(id="a", allowed_fields=["Computer Science", "Computer Engineering"]),
        make_job(id="b", allowed_fields=["computer engineering", "  COMPUTER SCIENCE "]),  # same set
        make_job(id="c", allowed_fields=["Computer Science", "Computer Engineering"], min_cgpa=7.0, min_cgpa_scale="SCALE_10"),
    ]
    spy = SpyProvider(answer("RELATED"))
    results = await run(make_profile([edu(field_of_study=IT)]), jobs, spy)

    assert len(spy.calls) == 1
    assert {r.eligibility_state for r in results.values()} == {E.LIKELY_ELIGIBLE}


@pytest.mark.anyio
async def test_distinct_ambiguity_inputs_are_each_asked_once() -> None:
    jobs = [
        make_job(id="a", allowed_fields=["Computer Science"]),
        make_job(id="b", allowed_fields=["Mathematics"]),
        make_job(id="c", allowed_fields=["computer science"]),
        make_job(id="d", allowed_fields=["Mathematics", "Statistics"]),
    ]
    spy = SpyProvider(answer("RELATED"))
    await run(make_profile([edu(field_of_study=IT)]), jobs, spy)
    assert sorted(allowed for _, allowed in spy.calls) == [["Computer Science"], ["Mathematics"], ["Mathematics", "Statistics"]]


@pytest.mark.anyio
async def test_a_failed_assessment_is_not_retried_within_the_request() -> None:
    jobs = [make_job(id=f"j{n}", allowed_fields=CS_FIELDS) for n in range(5)]
    spy = SpyProvider(fail=True)
    results = await run(make_profile([edu(field_of_study=IT)]), jobs, spy)
    assert len(spy.calls) == 1
    assert {field_entry(r).reason_code for r in results.values()} == {ReasonCode.AI_ASSESSMENT_UNAVAILABLE}


@pytest.mark.anyio
async def test_memo_is_request_scoped() -> None:
    spy = SpyProvider(answer("RELATED"))
    for _ in range(3):
        await run(make_profile([edu(field_of_study=IT)]), [make_job(id="a", allowed_fields=CS_FIELDS)], spy)
    assert len(spy.calls) == 3


# ---------------------------------------------------------------------------------------
# Privacy (items 22–28)
# ---------------------------------------------------------------------------------------

MARKERS = (CID, NAME, EMAIL, PHONE, RESUME, INSTITUTION, SKILL, str(CGPA), str(YEAR), "B.Tech", "BACHELORS")


@pytest.mark.anyio
async def test_provider_receives_only_field_and_allowed_fields() -> None:
    spy = SpyProvider(answer("RELATED"))
    job = make_job(id="a", allowed_fields=CS_FIELDS, description="JOB-DESCRIPTION-MARKER",
                   requirements={"notes": "JOB-NOTES-MARKER"}, company_name="JOB-COMPANY-MARKER")
    await run(private_profile(), [job], spy)

    assert spy.calls == [(IT, CS_FIELDS)]


@pytest.mark.anyio
async def test_actual_gemini_prompt_contains_no_candidate_or_unrelated_job_data() -> None:
    bodies: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content.decode("utf-8"))
        text = json.dumps({"result": "RELATED", "confidence": "HIGH", "reason": "Related."})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})

    provider = GeminiFlashProvider(
        api_key="test-key-not-real", model="gemini-2.0-flash",
        api_base="https://generativelanguage.example.invalid/v1beta", timeout_seconds=5,
        max_retries=0, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    job = make_job(id="JOB-ID-MARKER-77", allowed_fields=CS_FIELDS, description="JOB-DESCRIPTION-MARKER",
                   requirements={"notes": "JOB-NOTES-MARKER"}, company_name="JOB-COMPANY-MARKER",
                   role_title="JOB-ROLE-MARKER", min_cgpa=7.0, min_cgpa_scale="SCALE_10",
                   apply_link="https://careers.example.com/JOB-LINK-MARKER")
    results = await run(private_profile(), [job], provider)

    assert results["JOB-ID-MARKER-77"].eligibility_state is E.LIKELY_ELIGIBLE
    assert len(bodies) == 1
    sent = bodies[0]
    for marker in MARKERS + ("JOB-ID-MARKER-77", "JOB-DESCRIPTION-MARKER", "JOB-NOTES-MARKER",
                             "JOB-COMPANY-MARKER", "JOB-ROLE-MARKER", "JOB-LINK-MARKER", "7.0"):
        assert marker not in sent, f"leaked into AI request: {marker}"
    assert IT in sent and all(field in sent for field in CS_FIELDS)


@pytest.mark.anyio
async def test_ai_inputs_prompts_and_responses_are_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    reason = "AI-REASON-LOG-MARKER-2d"
    provider = MockAIProvider(return_relatedness=answer("RELATED", "HIGH", reason))
    caplog.set_level(logging.DEBUG)
    job = make_job(id="a", allowed_fields=["ALLOWED-FIELD-LOG-MARKER"])
    results = await run(private_profile(field_of_study="FIELD-LOG-MARKER-2d"), [job], provider)

    assert reason in field_entry(results["a"]).note  # returned to the caller...
    logged = caplog.text + "\n".join(str(r.args) for r in caplog.records)
    for secret in MARKERS + (reason, "FIELD-LOG-MARKER-2d", "ALLOWED-FIELD-LOG-MARKER", "RELATED"):
        assert secret not in logged, f"leaked into logs: {secret}"  # ...never logged
    assert "ai_assessments=1 ai_unavailable=0" in caplog.text


def _override(provider: AIProvider) -> None:
    app.dependency_overrides[get_lazy_ai_service] = lambda: AIService(provider)


def test_endpoint_ai_pass_is_likely_eligible(catalogue: Catalogue) -> None:  # noqa: F811
    provider = MockAIProvider(return_relatedness=answer("RELATED", "HIGH", "Closely related."))
    _override(provider)
    try:
        body = catalogue.client.post(
            CHECK_URL,
            json={"profile": {"education": [edu(field_of_study="Xylography Adjacent Studies",
                                                 grad_year=2027, cgpa=8.0)], "backlogs": 0},
                  "job_ids": [catalogue.ids["STRICT"], catalogue.ids["STRICT"]]},
        ).json()
    finally:
        app.dependency_overrides.pop(get_lazy_ai_service, None)

    (result,) = body["results"]
    assert result["eligibility_state"] == "LIKELY_ELIGIBLE"
    entry = result["requirement_breakdown"][-1]
    assert (entry["method"], entry["confidence"], entry["reason_code"]) == ("ai_reasoning", "MEDIUM", "AI_FIELD_RELATED")
    assert provider.relatedness_call_count == 1


def test_endpoint_provider_error_text_is_not_exposed(catalogue: Catalogue) -> None:  # noqa: F811
    _override(MockAIProvider(fail_with=AIProviderUnavailableError("UPSTREAM-DETAIL-MARKER-44")))
    try:
        response = catalogue.client.post(
            CHECK_URL,
            json={"profile": {"education": [edu(field_of_study="Some Other Field", grad_year=2027)], "backlogs": 0},
                  "job_ids": [catalogue.ids["STRICT"]]},
        )
    finally:
        app.dependency_overrides.pop(get_lazy_ai_service, None)

    assert response.status_code == 200
    assert "UPSTREAM-DETAIL-MARKER-44" not in response.text
    assert response.json()["results"][0]["eligibility_state"] == "NEEDS_REVIEW"


def test_endpoint_with_ai_persists_nothing(catalogue: Catalogue) -> None:  # noqa: F811
    from sqlalchemy import inspect as sa_inspect

    def dump() -> str:
        with catalogue.engine.connect() as connection:
            return "\n".join(connection.connection.iterdump())

    before = dump()
    _override(MockAIProvider(return_relatedness=answer("RELATED", "HIGH", "AI-REASON-DB-MARKER")))
    try:
        response = catalogue.client.post(
            CHECK_URL,
            json={"profile": {"candidate_id": CID, "name": NAME, "education": [edu(field_of_study="Adjacent Field", grad_year=2027)], "backlogs": 0},
                  "job_ids": list(catalogue.ids.values())},
        )
    finally:
        app.dependency_overrides.pop(get_lazy_ai_service, None)

    assert response.status_code == 200
    assert dump() == before
    assert "AI-REASON-DB-MARKER" not in dump()
    assert set(sa_inspect(catalogue.engine).get_table_names()) == ALLOWED_OPERATIONAL_TABLES
    assert set(Base.metadata.tables) == ALLOWED_OPERATIONAL_TABLES


def test_default_runtime_provider_never_fabricates_a_pass(catalogue: Catalogue) -> None:  # noqa: F811
    """No override: the configured default (mock) must leave ambiguity unresolved."""
    response = catalogue.client.post(
        CHECK_URL,
        json={"profile": {"education": [edu(field_of_study="Adjacent Field", grad_year=2027)], "backlogs": 0},
              "job_ids": [catalogue.ids["STRICT"]]},
    )
    result = response.json()["results"][0]
    assert result["eligibility_state"] == "NEEDS_REVIEW"
    assert result["requirement_breakdown"][-1]["reason_code"] == "AI_ASSESSMENT_INCONCLUSIVE"


def test_no_public_ai_endpoint_was_added() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    assert not [path for path in paths if "ai" in path.split("/") or "relatedness" in path]
