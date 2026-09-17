"""Deterministic eligibility engine.

Pure business logic. No FastAPI, no database, no AI import, no I/O (INV-7). Takes a
candidate profile and public job records; returns verdicts. Nothing is stored, and nothing
about the candidate is logged (INV-1, INV-4).

**Eligibility is not matching.** This module answers "does the candidate satisfy the job's
stated eligibility requirements?" — never "how well do they fit?". Skills, location and job
type belong to the Week 5 matching engine (C-11).

Evaluation order (dossier §12.1, ADR-003, ADR-017):

1. Select the qualification the per-qualification requirements apply to (ADR-018, A-1).
2. Evaluate **every** stated structured requirement deterministically, so a candidate who
   fails learns every verified reason rather than just the first (C-13).
3. If any verified deterministic requirement FAILED, ambiguous requirements are marked
   ``SKIPPED_AFTER_HARD_FAILURE`` and are never offered to AI. This is the INV-2 guard, and
   it lives in control flow — :func:`ambiguous_requirements` returns nothing for such a job.
4. Compose the final state from the breakdown (:func:`compose_verdict`).

The AI ambiguity stage is not part of this module yet (PR 4B). Until it exists, an
ambiguous requirement stays ``UNKNOWN``.

**Absence of evidence is not evidence of ineligibility.** No missing value is ever replaced
with a comparable one: a missing CGPA is not 0.0, missing backlogs are not 0, and a missing
graduation year is not this year (INV-3).
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from app.schemas.candidate import (
    CandidateProfile,
    Confidence,
    DegreeLevel,
    EducationEntry,
    GradeScale,
)
from app.schemas.eligibility import (
    EligibilityCheckResponse,
    EligibilityState,
    EvaluationMethod,
    JobEligibility,
    ReasonCode,
    RequirementResult,
    RequirementStatus,
    RequirementType,
)
from app.schemas.job import JobRead

logger = logging.getLogger("eligicore.eligibility")

#: Version of the rule set. Bump it whenever a rule, a reason code's meaning, or the verdict
#: precedence changes, so clients holding stored verdicts know to re-evaluate.
ENGINE_VERSION = "1"

#: Orderable qualification levels (ADR-018). ``OTHER`` and ``UNKNOWN`` are deliberately
#: absent: neither can be placed on this ladder, so neither can pass or fail a comparison.
_LEVEL_RANK: dict[DegreeLevel, int] = {
    DegreeLevel.HIGH_SCHOOL: 0,
    DegreeLevel.DIPLOMA: 1,
    DegreeLevel.BACHELORS: 2,
    DegreeLevel.MASTERS: 3,
    DegreeLevel.DOCTORATE: 4,
}

#: Human-readable requirement names used in summaries.
_REQUIREMENT_LABELS: dict[RequirementType, str] = {
    RequirementType.MIN_CGPA: "minimum CGPA",
    RequirementType.GRAD_YEAR_WINDOW: "graduation year",
    RequirementType.MAX_BACKLOGS: "backlog limit",
    RequirementType.MIN_DEGREE_LEVEL: "minimum qualification level",
    RequirementType.ALLOWED_FIELDS: "field of study",
}

_QUALIFICATION_NOTES: dict[ReasonCode, str] = {
    ReasonCode.NO_QUALIFICATION: (
        "The profile has no education record, so this requirement cannot be verified."
    ),
    ReasonCode.QUALIFICATION_NOT_DETERMINABLE: (
        "The profile has several education records and no single one is at the highest "
        "known level, so it is not clear which qualification this requirement applies to. "
        "Records are never combined."
    ),
}


# ---------------------------------------------------------------------------------------
# Result construction
# ---------------------------------------------------------------------------------------


def _result(
    requirement_type: RequirementType,
    requirement: str,
    status: RequirementStatus,
    reason_code: ReasonCode,
    note: str,
    candidate_value: str | None = None,
) -> RequirementResult:
    """Build a deterministic breakdown entry.

    Confidence follows from *how* the result was reached, never from whether it is good
    news: a verified comparison is HIGH whether it passed or failed; an unverifiable
    requirement is LOW (ADR-003, ``standards/eligibility.md`` §7).
    """
    confidence = Confidence.LOW if status is RequirementStatus.UNKNOWN else Confidence.HIGH
    return RequirementResult(
        requirement_type=requirement_type,
        requirement=requirement,
        candidate_value=candidate_value,
        status=status,
        confidence=confidence,
        method=EvaluationMethod.DETERMINISTIC,
        reason_code=reason_code,
        note=note,
    )


def _format_number(value: float) -> str:
    """Render a grade without inventing precision: 7.0 stays '7.0', 6.99 stays '6.99'."""
    return str(float(value))


def _normalize_text(value: str) -> str:
    """Trim, collapse whitespace and casefold — nothing more (ruling A-2).

    No stemming, no abbreviation expansion, no synonym table: any of those would be a field
    ontology, which this engine deliberately does not have.
    """
    return " ".join(value.split()).casefold()


# ---------------------------------------------------------------------------------------
# Qualification selection (ADR-018, ruling A-1)
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class QualificationSelection:
    """The education entry per-qualification requirements are evaluated against.

    Exactly one of ``entry`` and ``reason`` is set. When ``entry`` is ``None``, every
    per-qualification requirement resolves to ``UNKNOWN`` with ``reason``.
    """

    entry: EducationEntry | None
    reason: ReasonCode | None


def select_qualification(education: list[EducationEntry]) -> QualificationSelection:
    """Select the single qualification that CGPA, year, level and field are read from.

    1. No entries → none (``NO_QUALIFICATION``).
    2. Exactly one entry → that entry, whatever its level.
    3. Several entries → the single entry at the highest *known* level. A tie at that level,
       or no entry with an orderable level, → none (``QUALIFICATION_NOT_DETERMINABLE``).

    All four per-qualification requirements read from the *same* selected entry. Taking a
    CGPA from one record and a graduation year from another would evaluate a qualification
    the candidate does not hold.
    """
    if not education:
        return QualificationSelection(None, ReasonCode.NO_QUALIFICATION)
    if len(education) == 1:
        return QualificationSelection(education[0], None)

    ranked = [entry for entry in education if entry.level in _LEVEL_RANK]
    if not ranked:
        return QualificationSelection(None, ReasonCode.QUALIFICATION_NOT_DETERMINABLE)

    top = max(_LEVEL_RANK[entry.level] for entry in ranked)
    at_top = [entry for entry in ranked if _LEVEL_RANK[entry.level] == top]
    if len(at_top) != 1:
        return QualificationSelection(None, ReasonCode.QUALIFICATION_NOT_DETERMINABLE)
    return QualificationSelection(at_top[0], None)


def _unselected(
    requirement_type: RequirementType, requirement: str, selection: QualificationSelection
) -> RequirementResult:
    """The UNKNOWN result for a per-qualification requirement with no usable qualification."""
    reason = selection.reason or ReasonCode.QUALIFICATION_NOT_DETERMINABLE
    return _result(
        requirement_type,
        requirement,
        RequirementStatus.UNKNOWN,
        reason,
        _QUALIFICATION_NOTES[reason],
    )


# ---------------------------------------------------------------------------------------
# Requirement rules
# ---------------------------------------------------------------------------------------


def evaluate_min_cgpa(
    job: JobRead, selection: QualificationSelection
) -> RequirementResult | None:
    """Minimum CGPA. Same-scale comparison only (ruling C-12).

    There is no cross-scale conversion. Real conversions between 4-point, 10-point and
    percentage systems are institution-specific and non-linear, so a mismatched scale is
    ``UNKNOWN`` rather than an invented equivalence.

    Returns ``None`` when the job states no minimum.
    """
    if job.min_cgpa is None:
        return None

    stated_scale = (job.min_cgpa_scale or "").strip().upper()
    kind = RequirementType.MIN_CGPA
    requirement = (
        f"Minimum CGPA {_format_number(job.min_cgpa)} "
        f"({stated_scale if stated_scale else 'scale not stated'})"
    )

    # --- job side ------------------------------------------------------------------------
    if not stated_scale or stated_scale == GradeScale.UNKNOWN.value:
        return _result(
            kind, requirement, RequirementStatus.UNKNOWN, ReasonCode.JOB_SCALE_MISSING,
            "The job states a minimum grade without its grading scale, so no grade can be "
            "compared against it. The scale is never assumed.",
        )
    try:
        job_scale = GradeScale(stated_scale)
    except ValueError:
        return _result(
            kind, requirement, RequirementStatus.UNKNOWN, ReasonCode.JOB_SCALE_INVALID,
            "The job's grading scale is not a recognised scale, so the minimum cannot be "
            "interpreted.",
        )
    job_maximum = job_scale.maximum
    if job_maximum is None or job.min_cgpa > job_maximum:
        return _result(
            kind, requirement, RequirementStatus.UNKNOWN, ReasonCode.JOB_VALUE_EXCEEDS_SCALE,
            "The job's minimum exceeds the maximum of its own grading scale, so the "
            "requirement is invalid as stated.",
        )

    # --- candidate side ------------------------------------------------------------------
    if selection.entry is None:
        return _unselected(kind, requirement, selection)
    entry = selection.entry

    if entry.cgpa is None:
        return _result(
            kind, requirement, RequirementStatus.UNKNOWN, ReasonCode.MISSING_CANDIDATE_VALUE,
            "The selected qualification has no grade. A missing grade is not treated as "
            "zero, and it is not treated as passing.",
        )
    candidate_value = f"{_format_number(entry.cgpa)} ({entry.scale.value})"

    if entry.scale is GradeScale.UNKNOWN:
        return _result(
            kind, requirement, RequirementStatus.UNKNOWN, ReasonCode.CANDIDATE_SCALE_UNKNOWN,
            "The candidate's grade has no stated grading scale, so it cannot be compared. "
            "The scale is never assumed.",
            candidate_value,
        )
    if entry.scale is not job_scale:
        return _result(
            kind, requirement, RequirementStatus.UNKNOWN, ReasonCode.SCALE_MISMATCH,
            "The candidate's grade and the job's minimum use different grading scales. "
            "No conversion between scales is assumed.",
            candidate_value,
        )
    candidate_maximum = entry.scale.maximum
    if candidate_maximum is None or entry.cgpa > candidate_maximum:
        return _result(
            kind, requirement, RequirementStatus.UNKNOWN,
            ReasonCode.CANDIDATE_VALUE_EXCEEDS_SCALE,
            "The candidate's grade exceeds the maximum of its stated scale, so one of the "
            "two is wrong and the grade cannot be trusted.",
            candidate_value,
        )

    # --- comparison ----------------------------------------------------------------------
    if entry.cgpa >= job.min_cgpa:
        return _result(
            kind, requirement, RequirementStatus.PASS, ReasonCode.MEETS_MINIMUM,
            "The grade meets or exceeds the minimum on the same scale.",
            candidate_value,
        )
    return _result(
        kind, requirement, RequirementStatus.FAIL, ReasonCode.BELOW_MINIMUM,
        "The grade is below the minimum on the same scale.",
        candidate_value,
    )


def evaluate_grad_year_window(
    job: JobRead, selection: QualificationSelection
) -> RequirementResult | None:
    """Graduation year within every stated bound, inclusive.

    Either bound may be stated alone. Returns ``None`` when the job states neither.
    """
    low, high = job.min_grad_year, job.max_grad_year
    if low is None and high is None:
        return None

    kind = RequirementType.GRAD_YEAR_WINDOW
    if low is not None and high is not None:
        requirement = f"Graduation year {low}-{high}"
    elif low is not None:
        requirement = f"Graduation year {low} or later"
    else:
        requirement = f"Graduation year {high} or earlier"

    if low is not None and high is not None and low > high:
        return _result(
            kind, requirement, RequirementStatus.UNKNOWN, ReasonCode.INVALID_JOB_REQUIREMENT,
            "The job's earliest permitted graduation year is after its latest, so the "
            "window is invalid as stated.",
        )

    if selection.entry is None:
        return _unselected(kind, requirement, selection)
    year = selection.entry.grad_year
    if year is None:
        return _result(
            kind, requirement, RequirementStatus.UNKNOWN, ReasonCode.MISSING_CANDIDATE_VALUE,
            "The selected qualification has no graduation year. It is not assumed.",
        )

    candidate_value = str(year)
    if low is not None and year < low:
        return _result(
            kind, requirement, RequirementStatus.FAIL, ReasonCode.BEFORE_WINDOW,
            "The graduation year is earlier than the earliest year the job permits.",
            candidate_value,
        )
    if high is not None and year > high:
        return _result(
            kind, requirement, RequirementStatus.FAIL, ReasonCode.AFTER_WINDOW,
            "The graduation year is later than the latest year the job permits.",
            candidate_value,
        )
    return _result(
        kind, requirement, RequirementStatus.PASS, ReasonCode.WITHIN_WINDOW,
        "The graduation year is within the permitted range, bounds inclusive.",
        candidate_value,
    )


def evaluate_max_backlogs(
    job: JobRead, profile: CandidateProfile
) -> RequirementResult | None:
    """Active backlogs at or below the job's limit.

    Profile-level, not per-qualification. Returns ``None`` when the job states no limit.
    """
    if job.max_backlogs is None:
        return None

    kind = RequirementType.MAX_BACKLOGS
    requirement = f"Maximum {job.max_backlogs} active backlog(s)"

    if profile.backlogs is None:
        return _result(
            kind, requirement, RequirementStatus.UNKNOWN, ReasonCode.MISSING_CANDIDATE_VALUE,
            "The profile does not state an active backlog count. An unstated count is not "
            "assumed to be zero.",
        )

    candidate_value = str(profile.backlogs)
    if profile.backlogs <= job.max_backlogs:
        return _result(
            kind, requirement, RequirementStatus.PASS, ReasonCode.WITHIN_LIMIT,
            "The active backlog count is within the job's limit.",
            candidate_value,
        )
    return _result(
        kind, requirement, RequirementStatus.FAIL, ReasonCode.EXCEEDS_LIMIT,
        "The active backlog count exceeds the job's limit.",
        candidate_value,
    )


def evaluate_min_degree_level(
    job: JobRead, selection: QualificationSelection
) -> RequirementResult | None:
    """Selected qualification level at or above the job's minimum.

    Ordering: HIGH_SCHOOL < DIPLOMA < BACHELORS < MASTERS < DOCTORATE. ``OTHER`` and
    ``UNKNOWN`` are unorderable on either side. Returns ``None`` when the job states no level.
    """
    required = job.min_degree_level
    if required is None:
        return None

    kind = RequirementType.MIN_DEGREE_LEVEL
    requirement = f"Minimum qualification level {required.value}"

    if required not in _LEVEL_RANK:
        return _result(
            kind, requirement, RequirementStatus.UNKNOWN, ReasonCode.INVALID_JOB_REQUIREMENT,
            "The job's required level is not an orderable qualification level, so nothing "
            "can be compared against it.",
        )

    if selection.entry is None:
        return _unselected(kind, requirement, selection)
    level = selection.entry.level
    if level not in _LEVEL_RANK:
        return _result(
            kind, requirement, RequirementStatus.UNKNOWN, ReasonCode.CANDIDATE_LEVEL_UNKNOWN,
            "The selected qualification's level is not known or not orderable, so it cannot "
            "be compared. It is not guessed from the degree name.",
            None if level is DegreeLevel.UNKNOWN else level.value,
        )

    if _LEVEL_RANK[level] >= _LEVEL_RANK[required]:
        return _result(
            kind, requirement, RequirementStatus.PASS, ReasonCode.MEETS_LEVEL,
            "The qualification level meets or exceeds the required level.",
            level.value,
        )
    return _result(
        kind, requirement, RequirementStatus.FAIL, ReasonCode.BELOW_LEVEL,
        "The qualification level is below the required level.",
        level.value,
    )


def evaluate_allowed_fields(
    job: JobRead, selection: QualificationSelection
) -> RequirementResult | None:
    """Field of study against the job's permitted fields — exact normalized match only.

    **This rule never produces FAIL** (ruling A-2). There is no field ontology, so code
    cannot tell "Computer Science and Engineering" from an unrelated field; a non-exact
    match is ambiguous, not a mismatch. Returns ``None`` when the job permits any field.
    """
    allowed = [field for field in job.allowed_fields if field.strip()]
    if not allowed:
        return None

    kind = RequirementType.ALLOWED_FIELDS
    requirement = "Field of study: " + ", ".join(" ".join(f.split()) for f in allowed)

    if selection.entry is None:
        return _unselected(kind, requirement, selection)
    field = selection.entry.field_of_study
    if field is None or not field.strip():
        return _result(
            kind, requirement, RequirementStatus.UNKNOWN, ReasonCode.MISSING_CANDIDATE_VALUE,
            "The selected qualification has no field of study, so this requirement cannot "
            "be verified.",
        )

    candidate_value = " ".join(field.split())
    if _normalize_text(field) in {_normalize_text(option) for option in allowed}:
        return _result(
            kind, requirement, RequirementStatus.PASS, ReasonCode.EXACT_FIELD_MATCH,
            "The field of study exactly matches a permitted field.",
            candidate_value,
        )
    return _result(
        kind, requirement, RequirementStatus.UNKNOWN, ReasonCode.FIELD_NOT_EXACT_MATCH,
        "The field of study does not exactly match a permitted field. Whether it is a "
        "related field cannot be decided deterministically, so it is not treated as a "
        "mismatch.",
        candidate_value,
    )


# ---------------------------------------------------------------------------------------
# The hard-failure guard (INV-2, ruling C-13)
# ---------------------------------------------------------------------------------------


def has_verified_hard_failure(results: Iterable[RequirementResult]) -> bool:
    """True when any deterministic requirement FAILED on present, valid data.

    An AI-reasoned FAIL never counts. Only this is a *verified* hard failure (ADR-003).
    """
    return any(
        result.status is RequirementStatus.FAIL
        and result.method is EvaluationMethod.DETERMINISTIC
        for result in results
    )


def ambiguous_requirements(results: list[RequirementResult]) -> list[int]:
    """Indices of breakdown entries the AI stage is permitted to assess.

    **The structural INV-2 guard.** Returns an empty list whenever a verified hard failure
    exists, so no later stage can reach, re-evaluate or soften that job. Only exact-match
    misses on field of study qualify (ruling A-3); missing data never does, because AI must
    not supply facts the profile does not contain.
    """
    if has_verified_hard_failure(results):
        return []
    return [
        index
        for index, result in enumerate(results)
        if result.reason_code is ReasonCode.FIELD_NOT_EXACT_MATCH
    ]


def _skip_ambiguity_after_hard_failure(
    results: list[RequirementResult],
) -> list[RequirementResult]:
    """Mark ambiguous entries as skipped when a hard failure makes assessing them moot."""
    if not has_verified_hard_failure(results):
        return results
    return [
        result.model_copy(
            update={
                "reason_code": ReasonCode.SKIPPED_AFTER_HARD_FAILURE,
                "note": (
                    "Not assessed further: another requirement already failed a verified "
                    "check, so this ambiguous requirement cannot change the verdict."
                ),
            }
        )
        if result.reason_code is ReasonCode.FIELD_NOT_EXACT_MATCH
        else result
        for result in results
    ]


# ---------------------------------------------------------------------------------------
# Verdict composition (ADR-017)
# ---------------------------------------------------------------------------------------


def compose_verdict(results: list[RequirementResult]) -> EligibilityState:
    """Compose the final state. Precedence is exact and ordered (ADR-017):

    1. Zero structured requirements → ``ELIGIBLE``
    2. Any deterministic FAIL → ``NOT_ELIGIBLE``
    3. Every requirement UNKNOWN → ``UNKNOWN``
    4. Any UNKNOWN, or any AI FAIL → ``NEEDS_REVIEW``
    5. All PASS, at least one by AI → ``LIKELY_ELIGIBLE``
    6. All PASS deterministically → ``ELIGIBLE``

    An AI result alone can never produce ``NOT_ELIGIBLE`` (ruling R-2).
    """
    if not results:
        return EligibilityState.ELIGIBLE
    if has_verified_hard_failure(results):
        return EligibilityState.NOT_ELIGIBLE
    if all(result.status is RequirementStatus.UNKNOWN for result in results):
        return EligibilityState.UNKNOWN
    if any(result.status is not RequirementStatus.PASS for result in results):
        # What remains here is UNKNOWN or an AI-reasoned FAIL.
        return EligibilityState.NEEDS_REVIEW
    if any(result.method is EvaluationMethod.AI_REASONING for result in results):
        return EligibilityState.LIKELY_ELIGIBLE
    return EligibilityState.ELIGIBLE


def _labels(results: Iterable[RequirementResult]) -> str:
    return ", ".join(_REQUIREMENT_LABELS[result.requirement_type] for result in results)


def _has_unevaluated_notes(job: JobRead) -> bool:
    """True when the job carries free-text requirement content the engine does not read."""
    return any(
        value not in (None, "", [], {})
        and not (isinstance(value, str) and not value.strip())
        for value in job.requirements.values()
    )


def build_summary(
    state: EligibilityState, results: list[RequirementResult], job: JobRead
) -> str:
    """A human-readable reason for the verdict.

    Names requirements, never candidate values — a client logging summaries must not be
    logging grades (INV-4). Values live only in ``candidate_value``.
    """
    total = len(results)

    if not results:
        summary = "Eligible: this job states no structured eligibility requirements."
    elif state is EligibilityState.NOT_ELIGIBLE:
        failed = [
            r for r in results
            if r.status is RequirementStatus.FAIL
            and r.method is EvaluationMethod.DETERMINISTIC
        ]
        unverified = [r for r in results if r.status is RequirementStatus.UNKNOWN]
        summary = (
            f"Not eligible: {len(failed)} of {total} stated requirement(s) failed a verified "
            f"check ({_labels(failed)})."
        )
        if unverified:
            summary += (
                f" {len(unverified)} other requirement(s) could not be verified "
                f"({_labels(unverified)})."
            )
    elif state is EligibilityState.UNKNOWN:
        summary = (
            f"Unknown: none of the {total} stated requirement(s) could be verified from the "
            f"supplied profile ({_labels(results)})."
        )
    elif state is EligibilityState.NEEDS_REVIEW:
        unresolved = [r for r in results if r.status is not RequirementStatus.PASS]
        passed = total - len(unresolved)
        summary = (
            f"Needs review: {passed} of {total} stated requirement(s) met; "
            f"{_labels(unresolved)} could not be confirmed."
        )
    elif state is EligibilityState.LIKELY_ELIGIBLE:
        by_ai = sum(1 for r in results if r.method is EvaluationMethod.AI_REASONING)
        summary = (
            f"Likely eligible: meets all {total} stated requirement(s), {by_ai} of them by "
            "AI reasoning rather than a deterministic check."
        )
    else:
        summary = f"Eligible: meets all {total} stated eligibility requirement(s)."

    if _has_unevaluated_notes(job):
        summary += (
            " The job also lists free-text requirement notes, which were not evaluated."
        )
    return summary


# ---------------------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------------------


def evaluate_requirements(
    profile: CandidateProfile, job: JobRead
) -> list[RequirementResult]:
    """Evaluate every structured requirement the job states, deterministically.

    One qualification is selected once and shared by every per-qualification rule, so no
    two requirements can read from different education records. Requirements the job does
    not state are omitted, not reported as passing.
    """
    selection = select_qualification(profile.education)
    evaluated = [
        evaluate_min_cgpa(job, selection),
        evaluate_grad_year_window(job, selection),
        evaluate_max_backlogs(job, profile),
        evaluate_min_degree_level(job, selection),
        evaluate_allowed_fields(job, selection),
    ]
    results = [result for result in evaluated if result is not None]
    return _skip_ambiguity_after_hard_failure(results)


def evaluate_job(profile: CandidateProfile, job: JobRead) -> JobEligibility:
    """Produce the full, explained verdict for one candidate-job pair."""
    results = evaluate_requirements(profile, job)
    state = compose_verdict(results)
    return JobEligibility(
        job_id=job.id,
        company_name=job.company_name,
        role_title=job.role_title,
        job_status=job.status,
        apply_link=job.apply_link,
        deadline=job.deadline,
        eligibility_state=state,
        requirement_breakdown=results,
        summary=build_summary(state, results, job),
    )


def check_eligibility(
    profile: CandidateProfile,
    job_ids: list[str],
    jobs_by_id: Mapping[str, JobRead],
) -> EligibilityCheckResponse:
    """Evaluate a profile against the requested jobs.

    ``jobs_by_id`` holds the catalogue records the caller found; ids absent from it are
    reported in ``not_found_job_ids``. Results follow request order.

    Logs one line of counts and timing. **Never** the profile, any candidate value, or
    ``candidate_id`` — a stable client identifier in server logs would link one person's
    requests over time (INV-4).
    """
    started = time.perf_counter()

    results: list[JobEligibility] = []
    not_found: list[str] = []
    for job_id in job_ids:
        job = jobs_by_id.get(job_id)
        if job is None:
            not_found.append(job_id)
        else:
            results.append(evaluate_job(profile, job))

    counts = Counter(result.eligibility_state for result in results)
    logger.info(
        "eligibility_check jobs_requested=%d jobs_found=%d not_found=%d eligible=%d "
        "likely_eligible=%d needs_review=%d unknown=%d not_eligible=%d duration_ms=%.1f",
        len(job_ids),
        len(results),
        len(not_found),
        counts[EligibilityState.ELIGIBLE],
        counts[EligibilityState.LIKELY_ELIGIBLE],
        counts[EligibilityState.NEEDS_REVIEW],
        counts[EligibilityState.UNKNOWN],
        counts[EligibilityState.NOT_ELIGIBLE],
        (time.perf_counter() - started) * 1000,
    )

    return EligibilityCheckResponse(
        candidate_id=profile.candidate_id,
        engine_version=ENGINE_VERSION,
        evaluated_at=datetime.now(timezone.utc),
        results=results,
        not_found_job_ids=not_found,
    )
