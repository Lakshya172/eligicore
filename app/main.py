"""FastAPI application entrypoint.

Wires configuration, logging, middleware, exception handlers and routers.

**Privacy is enforced here, not merely documented.** Two mechanisms in this module are
load-bearing for INV-4:

1. :func:`validation_exception_handler` overrides FastAPI's default 422 response, which
   would otherwise echo the offending candidate values straight back to the client and into
   any error tracker or access log that captures response bodies.
2. :func:`request_context_middleware` logs request id, method, path, status and duration —
   and nothing else. No bodies, no headers, no query values.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.config import get_settings
from app.routers import candidates

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("eligicore")


# ---------------------------------------------------------------------------------------
# Error contract
# ---------------------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    """One problem with a request.

    Carries the field location and why it was rejected — but **never the value that was
    rejected**. Echoing the value back is how a candidate's email address ends up in a
    client-side error log (INV-4).
    """

    model_config = ConfigDict(extra="forbid")

    field: str = Field(description="Dotted path to the offending field.")
    code: str = Field(description="Machine-readable error type.")
    message: str = Field(description="Explanation. Contains no submitted value.")


class ErrorResponse(BaseModel):
    """The single error shape used by every endpoint."""

    model_config = ConfigDict(extra="forbid")

    error: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable summary.")
    request_id: str = Field(description="Correlation id, also returned as X-Request-ID.")
    details: list[ErrorDetail] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Liveness response."""

    model_config = ConfigDict(extra="forbid")

    status: str
    version: str
    environment: str


# ---------------------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------------------

app = FastAPI(
    title="EligiCore",
    version=__version__,
    summary="An eligibility-first job application intelligence API.",
    description=(
        "Determines which jobs and internships a candidate is genuinely eligible for — and "
        "explains exactly why.\n\n"
        "### Local-first\n"
        "Personal data lives on the user's device. This API is a **processing service**, "
        "not a personal-data store. Every endpoint handling personal data is stateless: the "
        "client sends what an operation needs, the backend computes and returns a result, "
        "and the client persists it locally.\n\n"
        "There is no `candidates` table, no `applications` table and no `evaluations` "
        "table. `candidate_id` is a client-generated correlation identifier, not a "
        "server-side key.\n\n"
        "### Current status\n"
        "Week 1 of a 10-week build. Only the candidate profile endpoints exist. Resume "
        "parsing, job ingestion, eligibility evaluation and matching are not yet "
        "implemented."
    ),
    openapi_tags=[
        {
            "name": "candidates",
            "description": "Stateless candidate profile operations. Nothing is stored.",
        },
        {"name": "system", "description": "Operational endpoints."},
    ],
)


def _request_id(request: Request) -> str:
    """Return this request's correlation id, generating one if absent."""
    existing = getattr(request.state, "request_id", None)
    if isinstance(existing, str):
        return existing
    return str(uuid.uuid4())


@app.middleware("http")
async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Any]],
) -> Any:
    """Attach a request id and log safe operational metadata only.

    Logged: request id, method, path, status, duration. Deliberately not logged: request
    body, query values, headers, or anything else that could carry candidate data (INV-4,
    ``standards/security_privacy.md`` §2).
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000

    logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return a sanitized 422 that does not echo submitted values.

    FastAPI's default handler includes an ``input`` key holding the exact value that failed
    validation. For this API that value is candidate data — a name, an email address, a
    grade — and it would be reflected back to the caller and into any log or error tracker
    that records response bodies.

    This handler keeps the field location and the reason, and drops ``input`` and ``ctx``
    entirely. ``ctx`` is dropped too because Pydantic embeds offending values in it for
    several error types.
    """
    details = [
        ErrorDetail(
            field=".".join(str(part) for part in error.get("loc", ()) if part != "body")
            or "body",
            code=str(error.get("type", "invalid")),
            message=str(error.get("msg", "Invalid value.")),
        )
        for error in exc.errors()
    ]

    request_id = _request_id(request)
    logger.info(
        "request_id=%s validation_failed path=%s error_count=%d",
        request_id,
        request.url.path,
        len(details),
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error="VALIDATION_ERROR",
            message="The request payload failed validation.",
            request_id=request_id,
            details=details,
        ).model_dump(),
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Return HTTP errors in the same envelope every other endpoint uses."""
    request_id = _request_id(request)
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error="HTTP_ERROR",
            message=str(exc.detail),
            request_id=request_id,
        ).model_dump(),
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a generic 500 without leaking internals.

    The traceback is not returned to the client and the exception message is not included,
    because an exception raised while handling a profile can easily carry candidate data in
    its message (INV-4, memory pitfall P-5). Only the type name is logged.
    """
    request_id = _request_id(request)
    logger.error(
        "request_id=%s unhandled_exception path=%s type=%s",
        request_id,
        request.url.path,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="INTERNAL_ERROR",
            message="An internal error occurred.",
            request_id=request_id,
        ).model_dump(),
        headers={"X-Request-ID": request_id},
    )


@app.get(
    f"{settings.api_v1_prefix}/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Liveness check",
)
async def health() -> HealthResponse:
    """Report that the application is running.

    Under ``/api/v1`` rather than a bare ``/health`` because INV-12 places every endpoint
    behind the version prefix without exception.
    """
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=settings.environment.value,
    )


app.include_router(candidates.router, prefix=settings.api_v1_prefix)
