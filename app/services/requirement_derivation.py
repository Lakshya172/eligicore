"""Derivation orchestration: ingestion → extraction → verification → storage (ADR-030 D21).

The layer that connects four things that already exist and until now did not know about each
other. It originates nothing and decides nothing about a requirement: the deterministic
extractors propose (D11), the verifier decides (D6), and ``extracted_requirements`` records
what survived (D16-D19). This module is the sequence, the trigger rule and the row lifecycle,
and that is all it is.

**Database access is deliberate and the AI boundary is not crossed.** This is the
persistence/application-service boundary, so a :class:`~sqlalchemy.orm.Session` is a
parameter. There is no FastAPI import, no router dependency, no HTTP, no AI provider, no
configuration read and **no logging at all** — not a count here, and certainly not an evidence
string or a description (INV-4, ADR-030 D24). The caller holds the configuration flag, owns
the transaction and logs whatever counts it wants from the outcome returned to it.

**Nothing about a candidate reaches this module.** No function takes a profile, an
identifier, a resume or an evaluation, and none is constructed. Extraction runs at ingestion
time from job text alone, exactly as D21 and D24 require.

What this module is **not**
---------------------------

It does not supply derived requirements to the eligibility engine, apply R-COLLISION, touch
``RequirementResult`` or change any response. Those are D20's engine boundary and belong to
their own decision and their own change. A row written here is stored and inert.

Trigger rule (D21, D22)
-----------------------

Derivation is ingestion-time only, one job at a time. Two triggers, and the asymmetry between
them is D22's, not an implementation convenience:

* **The pinned text changed** — a new job, or a description that is materially different.
  Eligible at the next ingestion, automatically.
* **The extractor version changed** — re-derivation happens when this function is called for
  such a job, but *"ordinary ingestion never silently re-extracts the catalogue"* (D22), so
  nothing in the ingestion path calls it for a job whose description is unchanged.

A job whose current description already has rows at the current extractor version is
``SKIPPED`` without running an extractor at all.

A known consequence, stated rather than hidden: a job that legitimately yields **zero**
verified requirements stores no row, so nothing records that derivation ran. Were this
function called for it again it would re-extract. Distinguishing "derived, found nothing"
from "never derived" needs somewhere to record the attempt, which means a schema change, and
the ingestion trigger above avoids the cost in practice by only calling for a job whose text
actually changed.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.extracted_requirement import ExtractedRequirement, ExtractionStatus
from app.models.job import Job
from app.schemas.eligibility import RequirementType
from app.schemas.extraction import (
    DerivedValue,
    GradYearWindowValue,
    MaxBacklogsValue,
    MinCgpaValue,
    VerifiedDerivedRequirement,
)
from app.services.requirement_extractors import EXTRACTOR_VERSION, extract_requirements
from app.services.requirement_verifier import verify_proposals


def source_text_digest(description: str) -> str:
    """SHA-256 of a job's description **exactly as stored** — the staleness key (D19).

    Deliberately not ``compute_content_hash``. That function canonicalizes before hashing,
    lowercasing and stripping punctuation, so two descriptions differing only in punctuation
    or case produce the same content hash while storing differently. A derived row keyed on
    it could look current while the evidence it quotes no longer occurs in the text.

    The two coexist and answer different questions: ``content_hash`` is source churn,
    ``source_text_digest`` is "is this derivation still about the text we hold".
    """
    return hashlib.sha256(description.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DerivationStatus(str, Enum):
    """What happened when derivation was asked for.

    ``COMPLETED`` with ``verified == 0`` and ``UNAVAILABLE`` are **different outcomes** and
    are kept apart on purpose. The first means the extractors ran and the posting states no
    requirement this system can verify, which is ordinary and common. The second means the
    attempt failed and the system knows nothing — collapsing them would let a broken
    extractor look like a catalogue of criterion-free jobs.
    """

    #: Extraction and verification ran. Rows reflect the result, which may be no rows.
    COMPLETED = "COMPLETED"

    #: Already derived from this exact text at this extractor version. Nothing was run.
    SKIPPED = "SKIPPED"

    #: Extraction or verification raised. Nothing was written, and ingestion is unaffected.
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class DerivationOutcome:
    """Counts and status for one job's derivation. The caller's only output from this module.

    Returned rather than logged, so a caller that wants operational numbers logs them from
    values it already holds — and nothing here is ever tempted to log the text it read.
    """

    status: DerivationStatus
    source_text_digest: str
    proposals: int = 0
    verified: int = 0
    rows_created: int = 0
    rows_updated: int = 0
    rows_invalidated: int = 0


#: Every typed value column, so a replacement writes all of them and a stale column cannot
#: survive a change of value shape. The database's own CHECK would catch that; clearing them
#: explicitly means the CHECK stays a backstop rather than the thing being relied upon.
_EMPTY_VALUE_COLUMNS: dict[str, object | None] = {
    "min_cgpa": None,
    "min_cgpa_scale": None,
    "min_grad_year": None,
    "max_grad_year": None,
    "max_backlogs": None,
}


def _value_columns(value: DerivedValue) -> dict[str, object | None]:
    """Map one verified typed value onto the storage columns it populates."""
    columns = dict(_EMPTY_VALUE_COLUMNS)
    if isinstance(value, MinCgpaValue):
        columns["min_cgpa"] = value.min_cgpa
        columns["min_cgpa_scale"] = value.min_cgpa_scale
    elif isinstance(value, GradYearWindowValue):
        columns["min_grad_year"] = value.min_grad_year
        columns["max_grad_year"] = value.max_grad_year
    elif isinstance(value, MaxBacklogsValue):
        columns["max_backlogs"] = value.max_backlogs
    return columns


def _verified_requirements(
    job: Job,
) -> tuple[dict[RequirementType, VerifiedDerivedRequirement], int]:
    """Extract from the job's pinned text and keep only what the verifier promoted.

    ``job.description`` **is** the pinned normalized text: ``normalize_job`` stores it
    post-``collapse_whitespace``, which is exactly D9's definition. It is passed through
    unchanged rather than re-normalized, because the verifier locates evidence in the string
    the system actually holds and a second normalization here would be a second definition of
    what that string is.

    The verifier's collection rule (D8) already discards every type for which two different
    values were proposed, so at most one requirement survives per type — which is what makes
    the storage unique key sufficient rather than merely plausible.
    """
    proposals = extract_requirements(job.description)
    result = verify_proposals(proposals, job.description)
    return (
        {
            requirement.requirement_type: requirement
            for requirement in result.verified
        },
        len(proposals),
    )


def _new_row(
    job: Job, digest: str, requirement: VerifiedDerivedRequirement, at: datetime
) -> ExtractedRequirement:
    """Build one storage row from one verified requirement.

    ``provenance`` and ``strength`` are taken from the verified requirement rather than
    defaulted, and on that type both are :class:`typing.Literal` — so a row claiming
    ``SOURCE_STATED`` or a non-``REQUIRED`` strength is unconstructible here before the
    database's own CHECK constraints ever see it.
    """
    return ExtractedRequirement(
        id=str(uuid.uuid4()),
        job_id=job.id,
        source_text_digest=digest,
        # Correlation metadata only. This table is never an input to the hash (D17).
        content_hash=job.content_hash,
        requirement_type=requirement.requirement_type,
        provenance=requirement.provenance,
        strength=requirement.strength,
        evidence_text=requirement.evidence_text,
        extractor=requirement.extractor,
        extractor_version=requirement.extractor_version,
        provider=requirement.provider,
        model=requirement.model,
        extracted_at=at,
        status=ExtractionStatus.ACTIVE,
        invalidated_at=None,
        **_value_columns(requirement.value),
    )


def _refresh(
    row: ExtractedRequirement,
    job: Job,
    requirement: VerifiedDerivedRequirement,
    at: datetime,
) -> None:
    """Rewrite an **active** row in place for the same job, text and requirement type.

    This is the extractor-version path: the same sentence re-read by a newer extractor
    produces the same key, so the row is replaced rather than duplicated. ``invalidated_at``
    is cleared explicitly — an active row carrying an invalidation timestamp is incoherent,
    and leaving a stale one would misreport when the derivation stopped applying.

    **Only ever called for a row that is already ``ACTIVE``.** ``INVALIDATED`` is terminal
    (see :meth:`ExtractedRequirement.invalidate`), and nothing here moves a row back.
    """
    row.content_hash = job.content_hash
    row.evidence_text = requirement.evidence_text
    row.extractor = requirement.extractor
    row.extractor_version = requirement.extractor_version
    row.provider = requirement.provider
    row.model = requirement.model
    row.extracted_at = at
    row.status = ExtractionStatus.ACTIVE
    row.invalidated_at = None
    for column, value in _value_columns(requirement.value).items():
        setattr(row, column, value)


def _is_current(rows: list[ExtractedRequirement], digest: str) -> bool:
    """Whether this job's derivation at this exact text is already up to date.

    True when rows exist for the digest and no active one was written by an older extractor.
    An all-invalidated digest counts as current: those rows are terminal, re-running would
    write nothing, and re-extracting to discover that on every ingestion is pure cost.
    """
    at_digest = [row for row in rows if row.source_text_digest == digest]
    if not at_digest:
        return False
    return all(
        row.extractor_version == EXTRACTOR_VERSION for row in at_digest if row.is_active
    )


def derive_for_job(session: Session, job: Job) -> DerivationOutcome:
    """Derive, verify and store this job's prose requirements. One job, never a batch.

    **Does not commit.** The caller owns the transaction, which is what lets ingestion commit
    the job first and treat a derivation failure as a separate, discardable unit of work.

    Args:
        session: The caller's session. Rows are added and mutated, never committed here.
        job: A stored job. Its ``description`` is the pinned normalized text (D9).

    Returns:
        A :class:`DerivationOutcome` carrying the status and the counts. Never raises for an
        extraction or verification failure: that is reported as
        :attr:`DerivationStatus.UNAVAILABLE` with nothing written, because a posting the
        system could not read is not a posting without requirements (ADR-003) and must never
        be the reason an ingestion run fails (D26).
    """
    digest = source_text_digest(job.description)
    rows = list(
        session.execute(
            select(ExtractedRequirement).where(ExtractedRequirement.job_id == job.id)
        ).scalars()
    )

    if _is_current(rows, digest):
        return DerivationOutcome(status=DerivationStatus.SKIPPED, source_text_digest=digest)

    try:
        verified, proposal_count = _verified_requirements(job)
    except Exception:
        # Fail closed and stay silent. The exception text could quote the description, and a
        # posting is third-party input (D25); re-raising would take a valid ingestion down
        # with it. Nothing has been written at this point, so there is nothing to undo.
        return DerivationOutcome(
            status=DerivationStatus.UNAVAILABLE, source_text_digest=digest
        )

    at = _utcnow()
    at_digest = {
        row.requirement_type: row for row in rows if row.source_text_digest == digest
    }

    created = updated = 0
    for requirement_type, requirement in verified.items():
        row = at_digest.get(requirement_type)
        if row is None:
            session.add(_new_row(job, digest, requirement, at))
            created += 1
        elif row.is_active:
            _refresh(row, job, requirement, at)
            updated += 1
        # A row already invalidated for this exact text and type stays invalidated. The
        # description changed away and back, and resurrecting a verification performed
        # against text that was withdrawn is precisely what the terminal state forbids.

    # Anything still active that this derivation did not just confirm no longer describes the
    # job: either it belongs to a superseded description, or its requirement type is no
    # longer verified from the current one. Invalidated, never deleted — a withdrawn
    # requirement is as much a fact about the posting as a current one (ADR-006).
    invalidated = 0
    for row in rows:
        if not row.is_active:
            continue
        if row.source_text_digest != digest or row.requirement_type not in verified:
            row.invalidate(at)
            invalidated += 1

    return DerivationOutcome(
        status=DerivationStatus.COMPLETED,
        source_text_digest=digest,
        proposals=proposal_count,
        verified=len(verified),
        rows_created=created,
        rows_updated=updated,
        rows_invalidated=invalidated,
    )


__all__ = [
    "DerivationOutcome",
    "DerivationStatus",
    "derive_for_job",
    "source_text_digest",
]
