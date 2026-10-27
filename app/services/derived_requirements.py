"""Derived requirements for evaluation — the one loading step both eligibility endpoints share.

ADR-030 D20b (owner ruling OD-14): ``POST /api/v1/eligibility/check`` and
``POST /api/v1/recommendations`` evaluate a job with **the same effective derived
requirements**, so ADR-022 §5's identical-verdict guarantee holds. Both routers call
:func:`load_derived_requirements` and nothing else to obtain them, and the shared eligibility
path (:func:`app.services.eligibility_ai.check_eligibility_with_ai`) requires the result as an
argument, so neither endpoint can evaluate without them.

This module holds the two things the persistence layer deliberately does not
(:mod:`app.services.requirement_derivation` reads no configuration and logs nothing):

* **The read gate** (owner ruling Q1). Derived requirements are consulted only while
  ``extraction_enabled`` is true. With it false nothing is queried and every verdict is what it
  was before ADR-030 (D27); stored rows are left exactly as they are (D22).
* **The skip count** (owner ruling Q2). A stored row that cannot be read back as a verified
  requirement is skipped and counted, and only the count is logged — never evidence text, a
  description, a job's content or anything about a candidate (INV-4, ADR-030 D24).

A database error is not handled here (owner ruling Q3). It propagates, and the request fails
through the application's sanitized 500.

Nothing is written and nothing is extracted: a request reads what ingestion stored (D21).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.job import Job
from app.schemas.extraction import VerifiedDerivedRequirement
from app.services.requirement_derivation import effective_derived_requirements_by_job

logger = logging.getLogger("eligicore.eligibility")

DerivedByJob = Mapping[str, tuple[VerifiedDerivedRequirement, ...]]


def load_derived_requirements(
    session: Session, jobs: Iterable[Job], *, settings: Settings | None = None
) -> DerivedByJob:
    """The verified derived requirements in force for each job, or none while extraction is off.

    Args:
        session: The request's session. Read only.
        jobs: The stored jobs about to be evaluated.
        settings: Overrides the process settings; tests use it.

    Returns:
        Verified requirements by job id. A job with none is absent. Empty when
        ``extraction_enabled`` is false.
    """
    if not (settings or get_settings()).extraction_enabled:
        return {}
    load = effective_derived_requirements_by_job(session, jobs)
    if load.unusable:
        logger.warning("derived_requirements unusable_rows=%d", load.unusable)
    return load.by_job
