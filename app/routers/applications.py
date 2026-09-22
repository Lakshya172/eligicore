"""Applications endpoints — the tracker export (ADR-023) and package preparation (ADR-025).

HTTP concerns only (INV-7). Each handler validates its request, calls one service and shapes what
comes back. The workbook layout lives in :mod:`app.services.tracker_export`; generation,
truthfulness validation, package status and every failure rule live in
:mod:`app.services.application_prep`. **No business logic, no provider handling and no database
query happens in this module** — the session is a dependency that is handed straight to the
service, the way ``job_ingestion`` already takes one.

**Stateless** (ADR-002, ADR-011). Export reads nothing and stores nothing; preparation reads one
public catalogue row and stores nothing. There is deliberately no ``GET`` on either, and no
application-status endpoint: both would imply a server-side record of an application, and none
exists (dossier §11, ADR-011).

**The one binary response in the API** (ADR-023 §8, ruling C-23): a successful export returns the
``.xlsx`` file itself. Preparation is ordinary JSON. Every error on both is the standard JSON
envelope — a 404 for an unknown job id, a 422 for a malformed request, and a **200** for every AI
failure, because an unavailable provider is a fact about the package, not a server fault
(ADR-019 §5).

**Nothing here submits anything** (ADR-008, INV-10). The response is a draft for a human.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.ai.ai_service import AIService, get_lazy_ai_service
from app.database import get_db
from app.schemas.application import (
    MAX_ANSWER_WORDS,
    MAX_COVER_LETTER_WORDS,
    MAX_QUESTION_TEXT,
    MAX_QUESTIONS,
    ApplicationPrepareRequest,
    ApplicationPrepareResponse,
)
from app.schemas.tracker import MAX_TRACKER_ROWS, TrackerExportRequest
from app.services.application_prep import JobNotFoundError, prepare_application
from app.services.tracker_export import TRACKER_FILENAME, XLSX_MEDIA_TYPE, export_tracker

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post(
    "/export",
    response_class=Response,
    status_code=status.HTTP_200_OK,
    summary="Export tracker rows as an Excel workbook",
    description=(
        "Renders the application-tracking rows **supplied in the body** as an `.xlsx` file and "
        "returns the file. The server looks nothing up and recalculates nothing: each row is "
        "written exactly as sent, in the order sent. Typically the client copies job, verdict "
        "and score fields from `/recommendations` and adds its own `application_status` and "
        "`notes`.\n\n"
        "**Workbook.** Sheet `Tracker`, one row per record. Sheet `Requirements`, one row per "
        "requirement, only when some record carries a `requirement_breakdown`. A null "
        "`match_score` is an empty cell, never 0. `deadline` and `evaluated_at` are real Excel "
        "dates (`evaluated_at` in UTC). Links are plain text.\n\n"
        "**Safe to open.** Text beginning with `=`, `+`, `-`, `@`, tab or carriage return is "
        "prefixed with an apostrophe and stored as text, so no cell can run as a formula.\n\n"
        f"**Limits.** 1 to {MAX_TRACKER_ROWS} records; each `job_id` at most once.\n\n"
        "**Response.** On success the body is the file itself (not JSON), with a fixed filename "
        f"`{TRACKER_FILENAME}` and `Cache-Control: no-store`. Errors use the standard JSON "
        "error envelope.\n\n"
        "**Nothing is stored** — no row, file or copy is kept, and no row content is logged."
    ),
    responses={
        200: {
            "description": "The tracker workbook.",
            "content": {XLSX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
        },
        422: {"description": "Invalid request. Submitted values are not echoed."},
    },
)
def export(request: TrackerExportRequest) -> Response:
    """Render the supplied rows and return the workbook.

    A plain ``def``: building a workbook is CPU work, so FastAPI runs it in its thread pool
    rather than blocking the event loop.
    """
    return Response(
        content=export_tracker(request.records),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{TRACKER_FILENAME}"',
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "/prepare",
    response_model=ApplicationPrepareResponse,
    status_code=status.HTTP_200_OK,
    summary="Prepare a reviewable application package",
    description=(
        "Generates a **draft** cover letter and answers for one catalogue job, then removes every "
        "claim that cannot be traced to the profile supplied in the same request.\n\n"
        "**Nothing is ever submitted.** `review_required` is always `true`. This API does not "
        "apply for jobs, fill employer forms, drive a browser or handle a CAPTCHA or OTP, and it "
        "never will — the package is yours to read, edit and send yourself.\n\n"
        "**Truthfulness is enforced, not requested.** Generated text is checked claim by claim "
        "against the supplied profile. An untraceable claim is removed with the sentence or list "
        "item that carried it — never reworded, never shortened, never flagged-and-kept — and "
        "every removal is disclosed in `removed_claims` with its category and reason. There is no "
        "parameter that disables this.\n\n"
        "**The provider sees a narrow projection.** Skills, experience titles, durations and "
        "descriptions, project names and descriptions, certification names, and degree, level, "
        "field of study and graduation year. It is never sent your name, email, phone, location, "
        "institution, CGPA, grading scale, backlog count, languages, preferences, employer names "
        "or résumé text — so a claim about any of those could only be a guess, and is removed on "
        "sight.\n\n"
        f"**Limits.** One `job_id`; at most {MAX_QUESTIONS} questions with unique ids; question "
        f"text at most {MAX_QUESTION_TEXT} characters; cover letter at most "
        f"{MAX_COVER_LETTER_WORDS} words; each answer at most {MAX_ANSWER_WORDS} words. An "
        "over-length item is discarded whole and returned as `null`, never truncated. A request "
        "with no cover letter and no questions asks for nothing and is rejected.\n\n"
        "**Status vs outcome.** `generation_outcome` says what the provider did; `status` says "
        "what survived validation. Every AI failure — unavailable, unparseable, empty — is a "
        "**200** with `NOTHING_VERIFIABLE` and no content, never a 5xx. Content that was "
        "generated and then entirely removed is `GENERATED` with `NOTHING_VERIFIABLE`.\n\n"
        "**Generation is mock-provider only in this build.** Selecting a live provider returns a "
        "200 with `AI_GENERATION_UNAVAILABLE`. Letter quality is not claimed; the truthfulness "
        "guarantee is.\n\n"
        "**Nothing is stored** — no profile, draft, package or removal is persisted, cached or "
        "logged."
    ),
    responses={
        404: {"description": "No job with that id."},
        422: {"description": "Invalid request. Submitted values are not echoed."},
    },
)
async def prepare(
    request: ApplicationPrepareRequest,
    db: Annotated[Session, Depends(get_db)],
    ai_service: Annotated[AIService, Depends(get_lazy_ai_service)],
) -> ApplicationPrepareResponse:
    """Delegate to the preparation service and translate its one error into a 404.

    The service is lazily given its provider, so a request rejected by validation never builds
    one. Nothing else is decided here: package status, failure semantics and every removal rule
    belong to :mod:`app.services.application_prep`.
    """
    try:
        return await prepare_application(db, request, ai_service)
    except JobNotFoundError as exc:
        # exc.message is authored in the service and contains no request content.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=exc.message
        ) from exc
