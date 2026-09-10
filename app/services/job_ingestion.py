"""Job ingestion: fetch, normalize, deduplicate, upsert, and record state.

Business logic. No FastAPI (INV-7). Takes a session and a list of adapters; the caller
decides where those come from.

Per run, per adapter:

    fetch -> normalize + hash -> match existing -> create | update | leave unchanged
          -> close jobs the authoritative source no longer lists
          -> write one ingestion_state row

**Matching order matters.** ``(source, source_job_id)`` is tried first because a source's
own stable identifier survives the posting being edited — a company fixing a typo in a
description should update the existing job, not create a second one. ``content_hash`` is the
fallback for sources without identifiers.

**Nothing here touches personal data.** Ingestion runs independently of any candidate
(dossier §7 step 4), so no function in this module takes a candidate, and `ingestion_state`
holds no user identifier (INV-1, ADR-012).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base_adapter import AdapterError, JobSourceAdapter
from app.models.ingestion_state import IngestionState, IngestionStatus
from app.models.job import Job, JobStatus
from app.schemas.job import IngestionOutcome, NormalizedJob
from app.services.job_normalizer import normalize_job

logger = logging.getLogger("eligicore.ingestion")

#: Fields copied from a normalized job onto an existing row during an update. Kept as data
#: so adding a column is one edit here rather than a forgotten assignment.
_UPDATABLE_FIELDS = (
    "company_name",
    "role_title",
    "job_type",
    "location",
    "description",
    "requirements",
    "min_cgpa",
    "min_cgpa_scale",
    "allowed_fields",
    "max_backlogs",
    "min_grad_year",
    "max_grad_year",
    "required_skills",
    "apply_link",
    "deadline",
    "content_hash",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def find_existing_job(session: Session, normalized: NormalizedJob) -> Job | None:
    """Locate the stored job a normalized record refers to, if any.

    Two strategies, in order:

    1. ``(source, source_job_id)`` — the source's own identifier. Survives edits to the
       posting, so an amended description updates rather than duplicates.
    2. ``content_hash`` — for sources with no stable identifier. Matches only within the
       same source, because the same posting syndicated to two portals is legitimately two
       rows with two apply links, and merging them would lose one.
    """
    if normalized.source_job_id:
        by_id = session.execute(
            select(Job).where(
                Job.source == normalized.source,
                Job.source_job_id == normalized.source_job_id,
            )
        ).scalar_one_or_none()
        if by_id is not None:
            return by_id

    return session.execute(
        select(Job).where(
            Job.source == normalized.source,
            Job.content_hash == normalized.content_hash,
        )
    ).scalar_one_or_none()


def _apply_updates(job: Job, normalized: NormalizedJob) -> bool:
    """Copy changed fields onto an existing job. Returns whether anything changed."""
    changed = False
    for field in _UPDATABLE_FIELDS:
        new_value = getattr(normalized, field)
        if getattr(job, field) != new_value:
            setattr(job, field, new_value)
            changed = True

    # A job present in this fetch is confirmed live, whatever it was before. A previously
    # closed posting reappearing in an authoritative source means it is open again.
    if job.status is not JobStatus.ACTIVE:
        job.status = JobStatus.ACTIVE
        changed = True

    return changed


def _create_job(normalized: NormalizedJob) -> Job:
    """Build a new job row from a normalized record."""
    now = _utcnow()
    return Job(
        id=str(uuid.uuid4()),
        source=normalized.source,
        source_job_id=normalized.source_job_id,
        status=JobStatus.ACTIVE,
        last_verified_at=now,
        created_at=now,
        updated_at=now,
        **{field: getattr(normalized, field) for field in _UPDATABLE_FIELDS},
    )


def ingest_source(session: Session, adapter: JobSourceAdapter) -> IngestionOutcome:
    """Run one adapter and reconcile its jobs into the catalogue.

    Raises:
        AdapterError: The adapter could not fetch. State is recorded as FAILED before the
            error propagates, so a failure is visible rather than silent.
    """
    source = adapter.source_name
    started = _utcnow()

    try:
        raw_jobs = _fetch_sync(adapter)
    except AdapterError as exc:
        _write_state(
            session,
            source=source,
            status=IngestionStatus.FAILED,
            run_at=started,
            # exc is authored by the adapter and already sanitized.
            error=str(exc),
            counts=IngestionOutcome(
                source=source, jobs_seen=0, jobs_created=0, jobs_updated=0,
                jobs_unchanged=0, jobs_deactivated=0,
            ),
        )
        session.commit()
        logger.warning("ingestion source=%s outcome=failed error_type=AdapterError", source)
        raise

    created = updated = unchanged = duplicates = 0
    seen_job_ids: set[str] = set()

    for raw in raw_jobs:
        normalized = normalize_job(raw, source)
        existing = find_existing_job(session, normalized)

        if existing is None:
            job = _create_job(normalized)
            session.add(job)
            # Flush so a later record in this same run matching the same posting finds it
            # and collapses, rather than creating a second row and tripping the constraint.
            session.flush()
            seen_job_ids.add(job.id)
            created += 1
            continue

        if existing.id in seen_job_ids:
            # Two records in one fetch resolved to the same stored job — the source listed
            # the same posting twice. Collapsed rather than counted as an update.
            duplicates += 1
            existing.last_verified_at = _utcnow()
            continue

        seen_job_ids.add(existing.id)
        existing.last_verified_at = _utcnow()
        if _apply_updates(existing, normalized):
            updated += 1
        else:
            unchanged += 1

    deactivated = _close_disappeared(session, adapter, seen_job_ids)

    outcome = IngestionOutcome(
        source=source,
        jobs_seen=len(raw_jobs),
        jobs_created=created,
        jobs_updated=updated,
        jobs_unchanged=unchanged,
        jobs_deactivated=deactivated,
        duplicates_collapsed=duplicates,
    )

    _write_state(
        session,
        source=source,
        status=IngestionStatus.SUCCESS,
        run_at=started,
        error=None,
        counts=outcome,
    )
    session.commit()

    # Counts only. Job postings are public, but keeping ingestion logging to numbers means
    # the habit holds when a future source carries something less public.
    logger.info(
        "ingestion source=%s outcome=success seen=%d created=%d updated=%d "
        "unchanged=%d deactivated=%d duplicates=%d",
        source, outcome.jobs_seen, created, updated, unchanged, deactivated, duplicates,
    )
    return outcome


def _fetch_sync(adapter: JobSourceAdapter) -> list:
    """Run an adapter's async fetch from synchronous code."""
    import asyncio

    return asyncio.run(adapter.fetch())


def _close_disappeared(
    session: Session, adapter: JobSourceAdapter, seen_job_ids: set[str]
) -> int:
    """Close active jobs an authoritative source no longer lists.

    **Only for authoritative sources.** A partial source — a paginated API, a filtered
    query, a rate-limited window — returns an incomplete view, and treating absence as
    closure there would empty the catalogue on the first page of results. That is the
    data-loss bug ``is_authoritative`` exists to prevent, and defaulting it to False means
    a new adapter gets the safe behaviour without its author having to know.

    Jobs are closed, never deleted: a closed posting stays retrievable with its reason,
    consistent with ADR-006.
    """
    if not adapter.is_authoritative:
        return 0

    stale = session.execute(
        select(Job).where(
            Job.source == adapter.source_name,
            Job.status == JobStatus.ACTIVE,
        )
    ).scalars().all()

    closed = 0
    for job in stale:
        if job.id not in seen_job_ids:
            job.status = JobStatus.CLOSED
            job.updated_at = _utcnow()
            closed += 1
    return closed


def _write_state(
    session: Session,
    *,
    source: str,
    status: IngestionStatus,
    run_at: datetime,
    error: str | None,
    counts: IngestionOutcome,
) -> IngestionState:
    """Upsert this source's single ingestion_state row (ADR-015)."""
    state = session.get(IngestionState, source)
    if state is None:
        state = IngestionState(source=source)
        session.add(state)

    state.last_run_at = run_at
    state.last_status = status
    state.last_error = error
    state.jobs_seen = counts.jobs_seen
    state.jobs_created = counts.jobs_created
    state.jobs_updated = counts.jobs_updated
    state.jobs_unchanged = counts.jobs_unchanged
    state.jobs_deactivated = counts.jobs_deactivated
    if status is IngestionStatus.SUCCESS:
        state.last_success_at = run_at
    return state


def ingest_all(
    session: Session, adapters: list[JobSourceAdapter]
) -> list[IngestionOutcome]:
    """Run every adapter, isolating failures.

    One source failing must not prevent the others from ingesting — that is the point of
    sources being independently enable-able (ADR-005). A failed source's state is recorded
    as FAILED and the run continues.
    """
    outcomes: list[IngestionOutcome] = []
    for adapter in adapters:
        try:
            outcomes.append(ingest_source(session, adapter))
        except AdapterError:
            # Already recorded as FAILED with a sanitized message by ingest_source.
            continue
    return outcomes
