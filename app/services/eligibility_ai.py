"""AI ambiguity resolution for eligibility — the second stage (ADR-019).

The deterministic engine (:mod:`app.services.eligibility_engine`) runs first and has final
authority. This module may act **only** on what
:func:`~app.services.eligibility_engine.ambiguous_requirements` releases: an
``ALLOWED_FIELDS`` requirement whose field of study was present but not an exact match, on a
job with no verified hard failure. For any other job — a hard failure, an exact match, a
missing field, no field restriction — nothing is sent anywhere and no provider is built.

What the AI stage can and cannot do:

* It answers one question: is this field of study related to these permitted fields?
* An AI "related" becomes ``PASS`` (``ai_reasoning``, at most MEDIUM confidence), which can
  make a verdict ``LIKELY_ELIGIBLE`` — never ``ELIGIBLE``.
* An AI "not related" becomes ``FAIL`` in the breakdown, but only a *deterministic* FAIL
  counts toward ``NOT_ELIGIBLE``, so the verdict is at worst ``NEEDS_REVIEW`` (ruling R-2).
* An uncertain or LOW-confidence answer, a provider error, an invalid reply, or a provider
  that cannot be built all fail closed to ``UNKNOWN``.

Assessments are memoized per request, in memory, keyed on the normalized inputs. Nothing is
persisted, cached across requests, or logged beyond counts.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator, Mapping

from app.ai.ai_service import AIService
from app.ai.errors import AIError
from app.schemas.candidate import CandidateProfile, Confidence
from app.schemas.eligibility import (
    EligibilityCheckResponse,
    EvaluationMethod,
    FieldRelatedness,
    FieldRelatednessAssessment,
    JobEligibility,
    ReasonCode,
    RequirementResult,
    RequirementStatus,
    RequirementType,
)
from app.schemas.job import JobRead
from app.services.eligibility_engine import (
    ambiguous_requirements,
    assemble_job_eligibility,
    build_check_response,
    evaluate_requirements,
    normalize_field_name,
)

#: Upper bound on concurrent provider calls within one request. A 50-job request with many
#: distinct permitted-field lists must not fan out 50 simultaneous paid calls.
MAX_CONCURRENT_AI_CALLS = 4

#: The strongest confidence an AI-reasoned result may carry. An interpretation of whether two
#: disciplines are related is never as trustworthy as a comparison (ADR-003, ADR-019).
MAX_AI_CONFIDENCE = Confidence.MEDIUM

AssessmentKey = tuple[str, tuple[str, ...]]


def assessment_key(field_of_study: str, allowed_fields: list[str]) -> AssessmentKey:
    """The request-scoped memo key: normalized field plus normalized, sorted permitted fields.

    Two jobs listing the same permitted fields in a different order or casing ask the same
    question, and get one provider call between them.
    """
    return (
        normalize_field_name(field_of_study),
        tuple(sorted({normalize_field_name(option) for option in allowed_fields})),
    )


def ai_inputs(
    job: JobRead, results: list[RequirementResult]
) -> Iterator[tuple[int, str, list[str]]]:
    """Yield ``(index, field_of_study, allowed_fields)`` for each entry the AI may assess.

    The index list comes from :func:`ambiguous_requirements` and nowhere else, so a job with
    a verified hard failure yields nothing (INV-2). The remaining checks are belt and braces:
    only a field-of-study entry with a present value and a non-empty permitted list can ever
    produce AI input — missing data is never sent (ADR-019).
    """
    allowed = [" ".join(option.split()) for option in job.allowed_fields if option.strip()]
    if not allowed:
        return
    for index in ambiguous_requirements(results):
        entry = results[index]
        if entry.requirement_type is not RequirementType.ALLOWED_FIELDS:
            continue
        if not entry.candidate_value or not entry.candidate_value.strip():
            continue
        yield index, entry.candidate_value, allowed


def cap_confidence(confidence: Confidence) -> Confidence:
    """Lower HIGH to :data:`MAX_AI_CONFIDENCE`; never raise a confidence."""
    return MAX_AI_CONFIDENCE if confidence is Confidence.HIGH else confidence


def apply_assessment(
    entry: RequirementResult, assessment: FieldRelatednessAssessment | None
) -> RequirementResult:
    """Turn an ambiguous breakdown entry into its AI-resolved form.

    ``assessment`` is ``None`` when none could be obtained — the provider failed, replied
    invalidly, or could not be built. That is reported as a deterministic ``UNKNOWN``: no AI
    judgement exists to attribute the entry to.
    """
    if assessment is None:
        return entry.model_copy(
            update={
                "status": RequirementStatus.UNKNOWN,
                "confidence": Confidence.LOW,
                "method": EvaluationMethod.DETERMINISTIC,
                "reason_code": ReasonCode.AI_ASSESSMENT_UNAVAILABLE,
                "note": (
                    "The field of study is not an exact match for a permitted field, and an "
                    "AI assessment of whether it is related was not available. The "
                    "requirement could not be verified."
                ),
            }
        )

    if assessment.result is FieldRelatedness.UNCERTAIN or assessment.confidence is Confidence.LOW:
        return entry.model_copy(
            update={
                "status": RequirementStatus.UNKNOWN,
                "confidence": Confidence.LOW,
                "method": EvaluationMethod.AI_REASONING,
                "reason_code": ReasonCode.AI_ASSESSMENT_INCONCLUSIVE,
                "note": (
                    "The field of study is not an exact match, and AI reasoning could not "
                    f"say with enough confidence whether it is related: {assessment.reason}"
                ),
            }
        )

    confidence = cap_confidence(assessment.confidence)
    if assessment.result is FieldRelatedness.RELATED:
        return entry.model_copy(
            update={
                "status": RequirementStatus.PASS,
                "confidence": confidence,
                "method": EvaluationMethod.AI_REASONING,
                "reason_code": ReasonCode.AI_FIELD_RELATED,
                "note": (
                    "Not an exact match. AI reasoning, not a deterministic check, judged the "
                    f"field of study related to a permitted field: {assessment.reason}"
                ),
            }
        )
    return entry.model_copy(
        update={
            "status": RequirementStatus.FAIL,
            "confidence": confidence,
            "method": EvaluationMethod.AI_REASONING,
            "reason_code": ReasonCode.AI_FIELD_NOT_RELATED,
            "note": (
                "Not an exact match. AI reasoning judged the field of study not related to a "
                "permitted field. This is not a verified failure and cannot by itself make "
                f"the candidate ineligible: {assessment.reason}"
            ),
        }
    )


async def _assess_all(
    ai_service: AIService, pending: Mapping[AssessmentKey, tuple[str, list[str]]]
) -> dict[AssessmentKey, FieldRelatednessAssessment | None]:
    """Obtain one assessment per distinct question, concurrently and boundedly.

    With nothing pending this returns before touching ``ai_service``, so a lazy service never
    builds its provider. Every AI failure — including a provider that cannot be built —
    becomes ``None`` and fails closed.
    """
    if not pending:
        return {}

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_AI_CALLS)

    async def assess(
        key: AssessmentKey, field_of_study: str, allowed_fields: list[str]
    ) -> tuple[AssessmentKey, FieldRelatednessAssessment | None]:
        async with semaphore:
            try:
                return key, await ai_service.assess_field_relatedness(
                    field_of_study, allowed_fields
                )
            except AIError:
                # The exception text is not surfaced: the caller sees a stable reason code.
                return key, None

    pairs = await asyncio.gather(
        *(assess(key, field, allowed) for key, (field, allowed) in pending.items())
    )
    return dict(pairs)


async def check_eligibility_with_ai(
    profile: CandidateProfile,
    job_ids: list[str],
    jobs_by_id: Mapping[str, JobRead],
    ai_service: AIService,
) -> EligibilityCheckResponse:
    """Evaluate a profile against the requested jobs, resolving field ambiguity with AI.

    1. Every found job is evaluated deterministically — all checks run (ADR-017).
    2. AI input is collected only from :func:`ai_inputs`, de-duplicated across jobs.
    3. Each distinct question is asked once; failures fail closed.
    4. Assessments are applied, and every verdict is composed by the engine's unchanged
       precedence.
    """
    started = time.perf_counter()

    evaluated: list[tuple[JobRead, list[RequirementResult]]] = []
    not_found: list[str] = []
    for job_id in job_ids:
        job = jobs_by_id.get(job_id)
        if job is None:
            not_found.append(job_id)
        else:
            evaluated.append((job, evaluate_requirements(profile, job)))

    pending: dict[AssessmentKey, tuple[str, list[str]]] = {}
    for job, breakdown in evaluated:
        for _, field_of_study, allowed_fields in ai_inputs(job, breakdown):
            pending.setdefault(
                assessment_key(field_of_study, allowed_fields), (field_of_study, allowed_fields)
            )

    assessments = await _assess_all(ai_service, pending)

    results: list[JobEligibility] = []
    for job, breakdown in evaluated:
        resolved = list(breakdown)
        for index, field_of_study, allowed_fields in ai_inputs(job, breakdown):
            key = assessment_key(field_of_study, allowed_fields)
            resolved[index] = apply_assessment(breakdown[index], assessments.get(key))
        results.append(assemble_job_eligibility(job, resolved))

    return build_check_response(
        profile,
        job_ids,
        results,
        not_found,
        started,
        ai_assessments=len(assessments),
        ai_unavailable=sum(1 for value in assessments.values() if value is None),
    )
