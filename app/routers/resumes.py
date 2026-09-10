"""Resume parsing endpoint — stateless.

Accepts a file, returns a parsed profile, keeps nothing. The uploaded file exists only for
the duration of processing and is deleted afterwards whether processing succeeded or failed
(dossier §11, INV-11). The client persists both the file and the extracted data locally
(ADR-001).

HTTP concerns only. Extraction, structuring and truthfulness checking live in
``app.services.resume_parser``; provider selection lives in ``app.ai.ai_service`` (INV-7).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.ai.ai_service import AIService, get_ai_service
from app.config import Settings, get_settings
from app.schemas.resume import ExtractionMetadata, ResumeParseResponse
from app.services import resume_parser
from app.services.resume_parser import ResumeParsingError

router = APIRouter(prefix="/resumes", tags=["resumes"])

# Maps a parsing failure to an HTTP status. Kept as data so the mapping is reviewable in
# one place rather than scattered through branches.
_STATUS_BY_CODE: dict[str, int] = {
    "UNSUPPORTED_FILE_TYPE": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    "FILE_TOO_LARGE": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    "EMPTY_DOCUMENT": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "CORRUPT_DOCUMENT": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "INSUFFICIENT_TEXT": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "AI_RESPONSE_INVALID": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "AI_UNAVAILABLE": status.HTTP_502_BAD_GATEWAY,
}


@router.post(
    "/parse",
    response_model=ResumeParseResponse,
    status_code=status.HTTP_200_OK,
    summary="Parse a resume into a structured candidate profile",
    description=(
        "Accepts a PDF or DOCX resume, extracts its text, structures it into a candidate "
        "profile, and returns the profile with per-field confidence.\n\n"
        "**Stateless.** The uploaded file exists only for the duration of processing and is "
        "deleted afterwards, whether processing succeeds or fails. Nothing is stored "
        "server-side — the client persists both the file and the result locally.\n\n"
        "**Nothing is fabricated.** Fields the resume does not state are left absent rather "
        "than guessed, a grade without a stated scale keeps `scale: UNKNOWN`, and an "
        "unstated backlog count stays `null` rather than becoming `0`. Extracted skills "
        "that cannot be traced back to the resume text are removed and reported.\n\n"
        "`field_confidence` describes how much the system trusts its own extraction. It "
        "says nothing about eligibility — high confidence does not mean a strong candidate, "
        "and low confidence does not mean a weak one."
    ),
    responses={
        413: {"description": "File exceeds the maximum accepted size."},
        415: {"description": "Unsupported file type. Only PDF and DOCX are accepted."},
        422: {"description": "Document is empty, corrupt, or could not be structured."},
        502: {"description": "The AI provider was unavailable."},
    },
)
async def parse_resume(
    file: Annotated[UploadFile, File(description="Resume file (PDF or DOCX).")],
    ai_service: Annotated[AIService, Depends(get_ai_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    candidate_id: Annotated[
        str | None,
        Form(description="Optional client-generated correlation id, echoed back."),
    ] = None,
) -> ResumeParseResponse:
    """Parse an uploaded resume into a structured profile."""
    import time

    started = time.perf_counter()

    content = await file.read()
    # Checked after reading because Starlette has already buffered the upload; the real
    # ceiling is the server's own body limit. Still enforced here so an oversized document
    # never reaches extraction or the AI provider.
    if len(content) > settings.max_resume_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Resume exceeds the maximum size of "
                f"{settings.max_resume_bytes // (1024 * 1024)} MB."
            ),
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded file is empty.",
        )

    try:
        parsed, source_format = await resume_parser.parse_resume(
            content=content,
            filename=file.filename,
            ai_service=ai_service,
            candidate_id=candidate_id,
            max_characters=settings.max_resume_characters,
            min_characters=settings.min_resume_characters,
        )
    except ResumeParsingError as exc:
        # exc.message is authored in the service and contains no candidate data.
        raise HTTPException(
            status_code=_STATUS_BY_CODE.get(
                exc.code, status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=exc.message,
        ) from exc

    return ResumeParseResponse(
        candidate_id=candidate_id,
        status=parsed.status,
        profile=parsed.profile,
        field_confidence=parsed.field_confidence,
        issues=parsed.issues,
        metadata=ExtractionMetadata(
            source_format=source_format,
            characters_extracted=parsed.characters_extracted,
            provider=ai_service.provider_name,
            model=ai_service.model,
            duration_ms=(time.perf_counter() - started) * 1000,
        ),
    )
