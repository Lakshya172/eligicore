"""Resume endpoint contract, error handling and privacy tests.

The privacy tests are the point of this file. Local-first personal data is the project's
defining property (ADR-001), and the resume endpoint handles the most sensitive payload the
system ever sees, so its guarantees are verified by evidence rather than asserted (QG-005).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.ai.ai_service import AIService, get_ai_service
from app.ai.errors import AIProviderUnavailableError
from app.ai.providers.mock import MockAIProvider
from app.database import Base, engine
from app.main import app
from tests.conftest import ALLOWED_OPERATIONAL_TABLES, FORBIDDEN_TABLES
from app.schemas.resume import ResumeExtraction
from tests.fixtures_documents import (
    SAMPLE_RESUME_LINES,
    SAMPLE_RESUME_NO_SCALE_LINES,
    build_corrupt_pdf,
    build_docx,
    build_empty_pdf,
    build_pdf,
)

PARSE_URL = "/api/v1/resumes/parse"


@pytest.fixture
def resume_client() -> Iterator[TestClient]:
    """Client with the AI dependency overridden to a deterministic mock."""
    app.dependency_overrides[get_ai_service] = lambda: AIService(MockAIProvider())
    yield TestClient(app)
    app.dependency_overrides.clear()


def _client_with(provider: MockAIProvider) -> TestClient:
    app.dependency_overrides[get_ai_service] = lambda: AIService(provider)
    return TestClient(app)


def _pdf_upload(lines: tuple[str, ...] = SAMPLE_RESUME_LINES) -> dict:
    return {"file": ("resume.pdf", build_pdf(lines), "application/pdf")}


# ---------------------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------------------


def test_parses_a_pdf_resume(resume_client: TestClient) -> None:
    response = resume_client.post(PARSE_URL, files=_pdf_upload())
    assert response.status_code == 200

    body = response.json()
    assert body["profile"]["email"] == "test.candidate@example.com"
    assert body["metadata"]["source_format"] == "PDF"
    assert body["metadata"]["provider"] == "mock"


def test_parses_a_docx_resume(resume_client: TestClient) -> None:
    files = {
        "file": (
            "resume.docx",
            build_docx(SAMPLE_RESUME_LINES),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    response = resume_client.post(PARSE_URL, files=files)

    assert response.status_code == 200
    assert response.json()["metadata"]["source_format"] == "DOCX"


def test_response_shape(resume_client: TestClient) -> None:
    body = resume_client.post(PARSE_URL, files=_pdf_upload()).json()

    assert set(body) == {
        "candidate_id", "status", "profile", "field_confidence", "issues", "metadata",
    }
    assert body["status"] in {"PARSED", "PARTIAL", "NEEDS_REVIEW"}
    assert set(body["metadata"]) == {
        "source_format", "characters_extracted", "provider", "model", "duration_ms",
    }


def test_candidate_id_is_echoed(resume_client: TestClient) -> None:
    response = resume_client.post(
        PARSE_URL, files=_pdf_upload(), data={"candidate_id": "client-generated-9"}
    )
    body = response.json()
    assert body["candidate_id"] == "client-generated-9"
    assert body["profile"]["candidate_id"] == "client-generated-9"


def test_route_is_versioned_and_post_only(resume_client: TestClient) -> None:
    paths = resume_client.get("/openapi.json").json()["paths"]
    assert PARSE_URL in paths
    assert set(paths[PARSE_URL]) == {"post"}
    assert all(p.startswith("/api/v1/") for p in paths)


def test_metadata_reports_a_character_count_not_the_text(resume_client: TestClient) -> None:
    metadata = resume_client.post(PARSE_URL, files=_pdf_upload()).json()["metadata"]
    assert isinstance(metadata["characters_extracted"], int)
    assert metadata["characters_extracted"] > 0


# ---------------------------------------------------------------------------------------
# Confidence and uncertainty
# ---------------------------------------------------------------------------------------


def test_unstated_scale_stays_unknown_through_the_api(resume_client: TestClient) -> None:
    """The behaviour that matters most, verified at the outermost layer."""
    body = resume_client.post(
        PARSE_URL, files=_pdf_upload(SAMPLE_RESUME_NO_SCALE_LINES)
    ).json()

    education = body["profile"]["education"][0]
    assert education["cgpa"] == 8.2
    assert education["scale"] == "UNKNOWN"
    assert any(i["code"] == "MISSING_SCALE" for i in body["issues"])


def test_unstated_backlogs_stays_null(resume_client: TestClient) -> None:
    body = resume_client.post(PARSE_URL, files=_pdf_upload()).json()
    assert body["profile"]["backlogs"] is None


def test_confidence_is_reported_per_field(resume_client: TestClient) -> None:
    body = resume_client.post(PARSE_URL, files=_pdf_upload()).json()
    assert body["field_confidence"]
    assert all(v in {"HIGH", "MEDIUM", "LOW"} for v in body["field_confidence"].values())


def test_confidence_is_not_eligibility(resume_client: TestClient) -> None:
    """Confidence describes the extraction. It says nothing about the candidate."""
    body = resume_client.post(PARSE_URL, files=_pdf_upload()).json()

    assert "eligible" not in body
    assert "eligibility" not in body
    assert "eligibility_state" not in body["profile"]
    assert "match_score" not in body["profile"]


def test_untraceable_skills_are_removed_and_flagged() -> None:
    """A fabricated skill must not survive into the profile."""
    pinned = ResumeExtraction(skills=["Python", "Kubernetes"])
    client = _client_with(MockAIProvider(return_extraction=pinned))
    try:
        body = client.post(PARSE_URL, files=_pdf_upload()).json()
    finally:
        app.dependency_overrides.clear()

    assert "Kubernetes" not in body["profile"]["skills"]
    assert any(i["code"] == "UNTRACEABLE_SKILL" for i in body["issues"])
    assert body["status"] == "NEEDS_REVIEW"


# ---------------------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------------------


def test_unsupported_file_type_returns_415(resume_client: TestClient) -> None:
    files = {"file": ("resume.txt", b"just plain text", "text/plain")}
    assert resume_client.post(PARSE_URL, files=files).status_code == 415


def test_empty_upload_returns_422(resume_client: TestClient) -> None:
    files = {"file": ("resume.pdf", b"", "application/pdf")}
    assert resume_client.post(PARSE_URL, files=files).status_code == 422


def test_corrupt_pdf_returns_422(resume_client: TestClient) -> None:
    files = {"file": ("resume.pdf", build_corrupt_pdf(), "application/pdf")}
    assert resume_client.post(PARSE_URL, files=files).status_code == 422


def test_image_only_pdf_returns_422(resume_client: TestClient) -> None:
    """A scanned resume yields no text — a real case, not a hypothetical."""
    files = {"file": ("scan.pdf", build_empty_pdf(), "application/pdf")}
    response = resume_client.post(PARSE_URL, files=files)

    assert response.status_code == 422
    assert "image" in response.json()["message"].lower()


def test_oversized_file_returns_413(resume_client: TestClient) -> None:
    oversized = b"%PDF-" + b"x" * (6 * 1024 * 1024)
    files = {"file": ("big.pdf", oversized, "application/pdf")}
    assert resume_client.post(PARSE_URL, files=files).status_code == 413


def test_ai_unavailable_returns_502() -> None:
    provider = MockAIProvider(fail_with=AIProviderUnavailableError("provider down"))
    client = _client_with(provider)
    try:
        response = client.post(PARSE_URL, files=_pdf_upload())
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 502


def test_invalid_ai_response_returns_422() -> None:
    client = _client_with(MockAIProvider(raise_invalid_response=True))
    try:
        response = client.post(PARSE_URL, files=_pdf_upload())
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


def test_missing_file_returns_422(resume_client: TestClient) -> None:
    assert resume_client.post(PARSE_URL).status_code == 422


def test_errors_use_the_standard_envelope(resume_client: TestClient) -> None:
    files = {"file": ("resume.txt", b"plain text", "text/plain")}
    body = resume_client.post(PARSE_URL, files=files).json()
    assert set(body) == {"error", "message", "request_id", "details"}


# ---------------------------------------------------------------------------------------
# Privacy — INV-1, INV-4, INV-11 (QG-005)
# ---------------------------------------------------------------------------------------


def test_parsing_creates_no_personal_data_table(resume_client: TestClient) -> None:
    resume_client.post(PARSE_URL, files=_pdf_upload())

    assert not (set(Base.metadata.tables) - ALLOWED_OPERATIONAL_TABLES)
    assert not (set(inspect(engine).get_table_names()) & FORBIDDEN_TABLES)


def test_repeated_parses_accumulate_no_server_state(resume_client: TestClient) -> None:
    first = resume_client.post(PARSE_URL, files=_pdf_upload()).json()
    second = resume_client.post(PARSE_URL, files=_pdf_upload()).json()

    first["metadata"].pop("duration_ms")
    second["metadata"].pop("duration_ms")
    assert first == second


def test_no_temporary_resume_files_survive(resume_client: TestClient) -> None:
    """INV-11, verified through the full HTTP path rather than only the service."""
    temp_root = Path(tempfile.gettempdir())
    before = set(temp_root.glob("*.pdf")) | set(temp_root.glob("*.docx"))

    resume_client.post(PARSE_URL, files=_pdf_upload())
    resume_client.post(PARSE_URL, files={"file": ("r.pdf", build_corrupt_pdf(), "application/pdf")})

    after = set(temp_root.glob("*.pdf")) | set(temp_root.glob("*.docx"))
    assert not (after - before), "a temporary resume file survived request handling"


def test_resume_content_never_reaches_logs(
    resume_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """INV-4: the most sensitive payload the system handles must not be logged."""
    with caplog.at_level("DEBUG"):
        resume_client.post(PARSE_URL, files=_pdf_upload())

    logged = "\n".join(r.getMessage() for r in caplog.records)
    for secret in (
        "Test Candidate",
        "test.candidate@example.com",
        "+10000000000",
        "Example Institute of Technology",
        "CGPA 8.2",
        "Example Corp",
    ):
        assert secret not in logged, f"{secret!r} leaked into logs"

    assert "path=/api/v1/resumes/parse" in logged


def test_pdf_library_cannot_log_document_content(resume_client: TestClient) -> None:
    """Regression: pdfminer logs the literal resume text at DEBUG level.

    Found by the test above. Anyone raising the root log level to DEBUG - in production, or
    while chasing an unrelated bug - would dump candidate data into the logs without having
    written a single log statement. The parser pins these library loggers at WARNING and
    stops them propagating, which is a privacy control rather than noise reduction.
    """
    import logging

    for name in ("pdfminer", "pdfplumber"):
        library_logger = logging.getLogger(name)
        assert library_logger.level >= logging.WARNING, f"{name} may emit document content"
        assert library_logger.propagate is False, f"{name} records may escape to root"

    # Attach a handler directly to the library loggers. If they were ever re-enabled,
    # this is precisely where the resume text would appear.
    captured: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    collector = _Collector(level=logging.DEBUG)
    targets = [logging.getLogger(name) for name in ("pdfminer", "pdfplumber")]
    for target in targets:
        target.addHandler(collector)
    try:
        resume_client.post(PARSE_URL, files=_pdf_upload())
    finally:
        for target in targets:
            target.removeHandler(collector)

    logged = "\n".join(record.getMessage() for record in captured)
    assert "Test Candidate" not in logged
    assert "test.candidate@example.com" not in logged


def test_error_responses_do_not_echo_submitted_content(resume_client: TestClient) -> None:
    marker = "SENSITIVE-RESUME-MARKER-7c1d"
    files = {"file": (f"{marker}.txt", marker.encode(), "text/plain")}
    response = resume_client.post(PARSE_URL, files=files)

    assert response.status_code == 415
    assert marker not in response.text


def test_corrupt_document_error_does_not_echo_content(resume_client: TestClient) -> None:
    marker = "SENSITIVE-INSIDE-PDF-3b9f"
    corrupt = b"%PDF-1.4\n" + marker.encode() + b"\nbroken\n%%EOF"
    response = resume_client.post(
        PARSE_URL, files={"file": ("r.pdf", corrupt, "application/pdf")}
    )

    assert response.status_code == 422
    assert marker not in response.text


def test_provider_failure_does_not_leak_provider_detail() -> None:
    provider = MockAIProvider(
        fail_with=AIProviderUnavailableError("upstream said SENSITIVE-PROVIDER-DETAIL-x2")
    )
    client = _client_with(provider)
    try:
        response = client.post(PARSE_URL, files=_pdf_upload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert "SENSITIVE-PROVIDER-DETAIL-x2" not in response.text


def test_issue_messages_carry_no_candidate_values(resume_client: TestClient) -> None:
    body = resume_client.post(PARSE_URL, files=_pdf_upload(SAMPLE_RESUME_NO_SCALE_LINES)).json()
    joined = " ".join(i["message"] for i in body["issues"])

    for secret in ("Test Candidate", "test.candidate@example.com", "8.2"):
        assert secret not in joined
