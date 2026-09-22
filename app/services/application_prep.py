"""Application-package preparation — generate, validate, then respond (ADR-025).

The dossier gives Week 7 one deliverable: *"Reviewable application packages"* (§15), and §7 STEP 8
states the shape of it — *"Tailored cover letter + answers → truthfulness validated"*, *"Output:
ready to REVIEW, never auto-submitted"*. This module is that step.

**The pipeline is the contract, and its order is load-bearing:**

1. resolve the catalogue job — an unknown id ends here, as a 404 (D2);
2. project the profile into :class:`~app.schemas.application.ApplicationEvidence` and the job into
   :class:`~app.schemas.application.JobBrief`, **field by field** (D10);
3. call the AI service **exactly once**;
4. check the draft's *structure* — ids, shape, word limits (D9, §11);
5. run the Slice 7A validator over the cover letter and over **every** answer (D5);
6. assemble the response from the sanitized text, and from nothing else.

**There is no path from a raw draft to a response.** Generated prose reaches a caller only as the
return value of :func:`app.services.truthfulness_validator.validate`. A package whose content was
generated and then entirely removed reports ``GENERATED`` with ``NOTHING_VERIFIABLE``: two
different facts about two different stages, and collapsing them would hide one.

**No AI failure is a 5xx** (ADR-019 §5). An unavailable provider, an unparseable reply and an empty
reply are all honest 200s that say what happened and carry no content.

Stateless and side-effect free (D4, D13, INV-1): nothing is stored, cached, memoized or written to
disk; no eligibility, matching or recommendation code is invoked (D7); the catalogue is read and
never written. One counts-only log line — never the profile, the evidence, the job text, a
question, the draft or a removal (INV-4).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.ai.ai_service import AIService
from app.ai.errors import AIError, AIResponseInvalidError
from app.models.job import Job
from app.schemas.application import (
    MAX_JOB_DESCRIPTION_CHARS,
    AnswerOutcome,
    ApplicationDraft,
    ApplicationEvidence,
    ApplicationPrepareRequest,
    ApplicationPrepareResponse,
    ApplicationQuestion,
    ClaimCategory,
    EvidenceCertification,
    EvidenceEducation,
    EvidenceExperience,
    EvidenceProject,
    GenerationLimits,
    GenerationOutcome,
    JobBrief,
    PackageStatus,
    PreparedAnswer,
    RemovalScope,
    RemovedClaim,
)
from app.schemas.candidate import CandidateProfile, Confidence
from app.services.truthfulness_validator import VALIDATOR_VERSION, validate

logger = logging.getLogger("eligicore.application_prep")

#: Returned whenever the requested job id is not in the catalogue. A fixed literal, matching
#: ``GET /api/v1/jobs/{job_id}`` exactly: the message must not vary with the id, or it becomes a
#: channel for echoing request content back.
JOB_NOT_FOUND_MESSAGE = "Job not found."

#: Returned with every package, whatever its status. EligiCore prepares; a human decides and a
#: human sends (ADR-008, INV-10, dossier §13.5).
NO_SUBMIT_NOTICE = (
    "This is a draft for you to review, edit and send yourself. EligiCore never submits an "
    "application on your behalf. Every claim that could not be traced to the profile you supplied "
    "has been removed rather than reworded — check what remains before you use it."
)


class ApplicationPrepError(Exception):
    """A preparation failure the router turns into an HTTP error.

    Carries a message **authored here**, never one built from request content, so the router can
    pass it to the client without inspecting it (the ``ResumeParsingError`` precedent).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class JobNotFoundError(ApplicationPrepError):
    """The requested ``job_id`` is not in the catalogue. The router answers 404."""


# ---------------------------------------------------------------------------------------
# Projections — the privacy boundary (D10)
# ---------------------------------------------------------------------------------------


def build_evidence(profile: CandidateProfile) -> ApplicationEvidence:
    """Project a profile into the evidence a provider may see, **field by field**.

    Written out longhand on purpose. ``model_dump()``, ``**kwargs`` and dictionary merging are all
    forbidden here (D10): each would forward whatever the profile happens to carry, so adding a
    field to :class:`~app.schemas.candidate.CandidateProfile` one day would silently widen what
    leaves the service. Naming every field means a new one arrives **excluded by default**, and
    including it is a visible edit to this function.

    Never projected: ``candidate_id``, ``name``, ``email``, ``phone``, ``location``, ``languages``,
    ``backlogs``, ``preferences``, ``field_confidence``, ``resume_raw_text``,
    ``experience[].company``, ``education[].institution``, ``education[].cgpa``,
    ``education[].scale``, ``certifications[].issuer`` and ``certifications[].year``.
    """
    return ApplicationEvidence(
        skills=list(profile.skills),
        experience=[
            EvidenceExperience(
                title=entry.title,
                duration=entry.duration,
                description=entry.description,
            )
            for entry in profile.experience
        ],
        projects=[
            EvidenceProject(name=project.name, description=project.description)
            for project in profile.projects
        ],
        certifications=[
            EvidenceCertification(name=certification.name)
            for certification in profile.certifications
        ],
        education=[
            EvidenceEducation(
                degree=entry.degree,
                level=entry.level,
                field_of_study=entry.field_of_study,
                grad_year=entry.grad_year,
            )
            for entry in profile.education
        ],
    )


def build_job_brief(job: Job) -> JobBrief:
    """Project a catalogue job into the brief a provider sees.

    ``company_name`` originates **here**, from the resolved row — the request has no field for a
    job object, so the target company is never client-supplied (D2). The description is truncated
    rather than rejected: a long posting is ordinary, and the tail rarely adds a requirement the
    opening paragraphs have not already stated.
    """
    return JobBrief(
        job_id=job.id,
        company_name=job.company_name,
        role_title=job.role_title,
        description=(job.description or "")[:MAX_JOB_DESCRIPTION_CHARS],
        required_skills=list(job.required_skills or []),
    )


# ---------------------------------------------------------------------------------------
# Generation and structural validation
# ---------------------------------------------------------------------------------------


def _word_count(text: str) -> int:
    """Words are whitespace-delimited tokens (D9). Deliberately the crudest possible rule."""
    return len(text.split())


async def _generate(
    ai_service: AIService,
    evidence: ApplicationEvidence,
    brief: JobBrief,
    questions: list[ApplicationQuestion],
    limits: GenerationLimits,
) -> tuple[GenerationOutcome, ApplicationDraft | None]:
    """Make the one provider call and decide whether its reply is usable **as a whole**.

    Structural failure is all-or-nothing by design (§11): a reply with an unknown question id, a
    duplicate id, or a shape that is not an :class:`ApplicationDraft` is a reply from something
    that did not understand the request, and picking the usable parts out of it would be guessing
    which parts to trust. Per-item problems — over-length, blank — are handled later, where the
    rest of the draft can still survive.
    """
    try:
        draft = await ai_service.generate_application_content(
            evidence, brief, questions, limits
        )
    except AIResponseInvalidError:
        return GenerationOutcome.AI_GENERATION_INVALID, None
    except AIError:
        # Unavailable, rejected, misconfigured, timed out: from the caller's side these are one
        # fact — no draft exists — and none of them is a 5xx.
        return GenerationOutcome.AI_GENERATION_UNAVAILABLE, None

    if not isinstance(draft, ApplicationDraft):
        return GenerationOutcome.AI_GENERATION_INVALID, None

    requested_ids = {question.id for question in questions}
    answered_ids = [answer.question_id for answer in draft.answers]
    if len(set(answered_ids)) != len(answered_ids):
        return GenerationOutcome.AI_GENERATION_INVALID, None
    if any(answer_id not in requested_ids for answer_id in answered_ids):
        return GenerationOutcome.AI_GENERATION_INVALID, None

    has_letter = bool((draft.cover_letter or "").strip())
    has_answer = any(answer.text.strip() for answer in draft.answers)
    if not has_letter and not has_answer:
        return GenerationOutcome.AI_GENERATION_EMPTY, None

    return GenerationOutcome.GENERATED, draft


def _prepare_cover_letter(
    draft: ApplicationDraft, profile: CandidateProfile, max_words: int
) -> tuple[str | None, list[RemovedClaim]]:
    """Validate the letter, or discard it whole when it is missing or over-length.

    An over-length letter is **not truncated** (D9): cutting prose mid-argument changes what it
    says, and a validator-adjacent step that edits meaning is the thing this whole slice exists to
    prevent. It becomes ``null``, and the package reports itself as partial.
    """
    raw = draft.cover_letter
    if raw is None or not raw.strip():
        return None, []
    if _word_count(raw) > max_words:
        return None, []
    sanitized, removed = validate(raw, profile, RemovalScope.COVER_LETTER)
    return (sanitized if sanitized.strip() else None), removed


def _prepare_answer(
    question: ApplicationQuestion,
    draft: ApplicationDraft,
    profile: CandidateProfile,
    default_max_words: int,
) -> PreparedAnswer:
    """Validate one answer and name its outcome.

    ``REQUIRES_EXCLUDED_DATA`` is **derived, never predicted** (owner ruling, Week 7B design
    clarification). Nothing classifies a question before the provider call: no keyword list, no
    pre-scan, no heuristic about what a question is "really" asking. The outcome is recorded only
    when the validator actually removed a knowledge-boundary claim *and* nothing survived — which
    is the honest reading of "this could only have been answered with data the model was never
    given".
    """
    by_id = {answer.question_id: answer for answer in draft.answers}
    entry = by_id.get(question.id)
    max_words = question.max_words or default_max_words

    if entry is None or not entry.text.strip():
        return PreparedAnswer(
            question_id=question.id, answer=None, outcome=AnswerOutcome.EMPTY
        )
    if _word_count(entry.text) > max_words:
        return PreparedAnswer(
            question_id=question.id, answer=None, outcome=AnswerOutcome.INVALID
        )

    sanitized, removed = validate(
        entry.text, profile, RemovalScope.ANSWER, question_id=question.id
    )
    if sanitized.strip():
        return PreparedAnswer(
            question_id=question.id,
            answer=sanitized,
            outcome=AnswerOutcome.GENERATED,
            removed_claims=removed,
        )

    excluded = any(claim.category is ClaimCategory.EXCLUDED_DATA for claim in removed)
    return PreparedAnswer(
        question_id=question.id,
        answer=None,
        outcome=(
            AnswerOutcome.REQUIRES_EXCLUDED_DATA if excluded else AnswerOutcome.REMOVED_ENTIRELY
        ),
        removed_claims=removed,
    )


def _failed_answers(
    questions: list[ApplicationQuestion], outcome: GenerationOutcome
) -> list[PreparedAnswer]:
    """One entry per question when no draft exists, saying which stage failed."""
    mapping = {
        GenerationOutcome.AI_GENERATION_UNAVAILABLE: AnswerOutcome.UNAVAILABLE,
        GenerationOutcome.AI_GENERATION_INVALID: AnswerOutcome.INVALID,
        GenerationOutcome.AI_GENERATION_EMPTY: AnswerOutcome.EMPTY,
    }
    answer_outcome = mapping[outcome]
    return [
        PreparedAnswer(question_id=question.id, answer=None, outcome=answer_outcome)
        for question in questions
    ]


def _package_status(
    generation_outcome: GenerationOutcome,
    requested: int,
    delivered: int,
    removed: list[RemovedClaim],
) -> PackageStatus:
    """What survived validation — never what the provider did (ADR-025 § Failure semantics)."""
    if generation_outcome is not GenerationOutcome.GENERATED or delivered == 0:
        return PackageStatus.NOTHING_VERIFIABLE
    if removed or delivered < requested:
        return PackageStatus.PARTIAL
    return PackageStatus.COMPLETE


def _provider_identity(ai_service: AIService) -> tuple[str, str]:
    """Name the provider and model, tolerating one that could not be constructed.

    A provider that failed to build has no name to report, and a request must still answer with a
    complete package (200, nothing verifiable) rather than a 500. ``"unknown"`` says exactly that,
    and reads no configuration to guess a better answer.
    """
    try:
        return ai_service.provider_name, ai_service.model
    except AIError:
        return "unknown", "unknown"


# ---------------------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------------------


async def prepare_application(
    session: Session,
    request: ApplicationPrepareRequest,
    ai_service: AIService,
) -> ApplicationPrepareResponse:
    """Prepare one reviewable application package.

    Args:
        session: Read-only access to the job catalogue — public operational data. Nothing is
            written, flushed or committed here (D13).
        request: The validated request. Its profile is used and discarded (D1).
        ai_service: Called exactly once, whatever the request contains.

    Returns:
        A package built only from validated content.

    Raises:
        JobNotFoundError: No catalogue job has that id. The router answers 404.
    """
    started = time.perf_counter()

    job = session.get(Job, request.job_id)
    if job is None:
        raise JobNotFoundError(JOB_NOT_FOUND_MESSAGE)

    evidence = build_evidence(request.profile)
    brief = build_job_brief(job)
    limits = GenerationLimits(
        include_cover_letter=request.include_cover_letter,
        cover_letter_max_words=request.cover_letter_max_words,
        answer_max_words=request.answer_max_words,
    )

    generation_outcome, draft = await _generate(
        ai_service, evidence, brief, list(request.questions), limits
    )

    if draft is None:
        cover_letter: str | None = None
        cover_removals: list[RemovedClaim] = []
        answers = _failed_answers(list(request.questions), generation_outcome)
    else:
        cover_letter, cover_removals = (
            _prepare_cover_letter(draft, request.profile, request.cover_letter_max_words)
            if request.include_cover_letter
            else (None, [])
        )
        answers = [
            _prepare_answer(question, draft, request.profile, request.answer_max_words)
            for question in request.questions
        ]

    # The aggregate is the authoritative list: cover-letter removals, then every answer's, in
    # request order. Per-answer lists are local copies of the same claims (ADR-025 § Removal).
    removed_claims = [*cover_removals]
    for answer in answers:
        removed_claims.extend(answer.removed_claims)

    requested = (1 if request.include_cover_letter else 0) + len(request.questions)
    delivered = (1 if cover_letter is not None else 0) + sum(
        1 for answer in answers if answer.answer is not None
    )
    status = _package_status(generation_outcome, requested, delivered, removed_claims)
    provider_name, model = _provider_identity(ai_service)

    logger.info(
        "application_prepared provider=%s model=%s outcome=%s status=%s questions=%d "
        "answers_delivered=%d removals=%d cover_letter=%s duration_ms=%.1f",
        provider_name,
        model,
        generation_outcome.value,
        status.value,
        len(request.questions),
        delivered,
        len(removed_claims),
        cover_letter is not None,
        (time.perf_counter() - started) * 1000,
    )

    return ApplicationPrepareResponse(
        candidate_id=request.profile.candidate_id,
        job_id=job.id,
        company_name=job.company_name,
        role_title=job.role_title,
        status=status,
        generation_outcome=generation_outcome,
        cover_letter=cover_letter,
        answers=answers,
        removed_claims=removed_claims,
        notice=NO_SUBMIT_NOTICE,
        provider=provider_name,
        model=model,
        confidence=(
            Confidence.LOW
            if removed_claims or status is PackageStatus.NOTHING_VERIFIABLE
            else Confidence.MEDIUM
        ),
        validator_version=VALIDATOR_VERSION,
        generated_at=datetime.now(timezone.utc),
    )
