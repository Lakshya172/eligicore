"""Applications endpoints — the tracker export (ADR-023).

HTTP concerns only (INV-7): validate the request, call the export service, wrap its bytes. The
workbook layout, formula-injection defence and logging live in
:mod:`app.services.tracker_export`.

**Stateless** (ADR-002, ADR-011). The client's tracking rows arrive in the body and leave only as
the returned file. No database session is taken, because the export reads nothing from the
server. There is deliberately no ``GET`` and no application-status endpoint.

**The one binary response in the API** (ADR-023 §8, ruling C-23): a successful export returns the
``.xlsx`` file itself. The request is still a Pydantic model and every error is still the
standard JSON envelope.

``/api/v1/applications/prepare`` is Week 7 and is not implemented.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.schemas.tracker import MAX_TRACKER_ROWS, TrackerExportRequest
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
