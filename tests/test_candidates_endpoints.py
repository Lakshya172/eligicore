"""Endpoint contract, statelessness and privacy tests.

The privacy tests here are not decoration. Local-first personal data is the project's
defining architectural property (ADR-001), and QG-005 requires it to be verified by
evidence rather than asserted in prose.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.database import Base, engine
from tests.conftest import ALLOWED_OPERATIONAL_TABLES, FORBIDDEN_TABLES

VALIDATE_URL = "/api/v1/candidates/validate"
NORMALIZE_URL = "/api/v1/candidates/normalize"



# ---------------------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------------------


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_document_generates(client: TestClient) -> None:
    """The generated OpenAPI document is the published contract, so it must build."""
    response = client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json()["paths"]
    assert VALIDATE_URL in paths
    assert NORMALIZE_URL in paths


def test_every_route_is_versioned(client: TestClient) -> None:
    """INV-12: all endpoints live under /api/v1/."""
    paths = client.get("/openapi.json").json()["paths"]
    unversioned = [p for p in paths if not p.startswith("/api/v1/")]
    assert unversioned == []


def test_no_candidate_get_or_patch_route_exists(client: TestClient) -> None:
    """ADR-002: a GET/PATCH on a candidate resource would imply a server-held record."""
    paths = client.get("/openapi.json").json()["paths"]
    for path, methods in paths.items():
        if "candidate" in path:
            assert set(methods) <= {"post"}, f"{path} exposes non-POST methods: {methods}"


# ---------------------------------------------------------------------------------------
# Validation endpoint
# ---------------------------------------------------------------------------------------


def test_validate_accepts_a_complete_profile(
    client: TestClient, complete_profile: dict[str, Any]
) -> None:
    response = client.post(VALIDATE_URL, json=complete_profile)
    assert response.status_code == 200

    body = response.json()
    assert body["is_valid"] is True
    assert body["candidate_id"] == "client-generated-test-id-0001"
    assert body["profile"]["education"][0]["scale"] == "SCALE_10"


def test_validate_response_shape(
    client: TestClient, minimal_profile: dict[str, Any]
) -> None:
    body = client.post(VALIDATE_URL, json=minimal_profile).json()
    assert set(body) == {"candidate_id", "is_valid", "issues", "profile"}

    for issue in body["issues"]:
        assert set(issue) == {"field", "code", "message", "severity"}
        assert issue["severity"] in {"ERROR", "WARNING", "INFO"}


def test_validate_reports_gaps_without_rejecting(client: TestClient) -> None:
    """A partial profile is reported on, not refused."""
    response = client.post(VALIDATE_URL, json={"education": [{"degree": "B.Tech"}]})
    assert response.status_code == 200

    body = response.json()
    codes = {issue["code"] for issue in body["issues"]}
    assert {"MISSING_GRAD_YEAR", "MISSING_FIELD_OF_STUDY", "MISSING_BACKLOGS"} <= codes
    assert body["is_valid"] is True, "warnings must not block"


def test_validate_flags_blocking_issue(client: TestClient) -> None:
    body = client.post(VALIDATE_URL, json={}).json()
    assert body["is_valid"] is False
    assert any(i["code"] == "NO_EDUCATION" and i["severity"] == "ERROR"
               for i in body["issues"])


def test_validate_flags_grade_exceeding_scale(client: TestClient) -> None:
    body = client.post(
        VALIDATE_URL,
        json={"education": [{"degree": "B.Tech", "cgpa": 8.2, "scale": "SCALE_4"}]},
    ).json()

    assert body["is_valid"] is False
    assert any(i["code"] == "GRADE_EXCEEDS_SCALE" for i in body["issues"])


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email"},
        {"backlogs": -5},
        {"education": [{"degree": "B.Tech", "cgpa": -3}]},
        {"unexpected_field": "x"},
        {"education": "not-a-list"},
    ],
)
def test_validate_rejects_structurally_invalid_payloads(
    client: TestClient, payload: dict[str, Any]
) -> None:
    response = client.post(VALIDATE_URL, json=payload)
    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"


def test_error_response_shape_is_consistent(client: TestClient) -> None:
    body = client.post(VALIDATE_URL, json={"backlogs": -1}).json()
    assert set(body) == {"error", "message", "request_id", "details"}
    for detail in body["details"]:
        assert set(detail) == {"field", "code", "message"}


def test_request_id_header_is_returned(client: TestClient) -> None:
    response = client.post(VALIDATE_URL, json={})
    assert response.headers.get("X-Request-ID")


def test_supplied_request_id_is_echoed(client: TestClient) -> None:
    response = client.post(
        VALIDATE_URL, json={}, headers={"X-Request-ID": "trace-abc-123"}
    )
    assert response.headers["X-Request-ID"] == "trace-abc-123"


# ---------------------------------------------------------------------------------------
# Normalization endpoint
# ---------------------------------------------------------------------------------------


def test_normalize_canonicalizes_skills(
    client: TestClient, complete_profile: dict[str, Any]
) -> None:
    body = client.post(NORMALIZE_URL, json=complete_profile).json()
    skills = body["profile"]["skills"]

    assert skills == ["Python", "React", "SQL", "Docker"]
    assert len(skills) == 4, "ReactJS and React.js must collapse into one entry"


def test_normalize_preserves_education(
    client: TestClient, complete_profile: dict[str, Any]
) -> None:
    body = client.post(NORMALIZE_URL, json=complete_profile).json()
    education = body["profile"]["education"]

    assert len(education) == 2
    assert education[0]["cgpa"] == 8.2
    assert education[0]["scale"] == "SCALE_10"
    assert education[1]["cgpa"] == 92.0
    assert education[1]["scale"] == "PERCENTAGE"


def test_normalize_returns_scale_independent_grades(
    client: TestClient, complete_profile: dict[str, Any]
) -> None:
    body = client.post(NORMALIZE_URL, json=complete_profile).json()
    grades = body["normalized_grades"]

    assert grades[0]["fraction"] == pytest.approx(0.82)
    assert grades[1]["fraction"] == pytest.approx(0.92)
    assert [g["education_index"] for g in grades] == [0, 1]


def test_normalize_leaves_unknown_scale_unnormalized(client: TestClient) -> None:
    """The requirement that matters most: unknown must stay unknown."""
    body = client.post(
        NORMALIZE_URL, json={"education": [{"degree": "B.Tech", "cgpa": 8.2}]}
    ).json()

    assert body["profile"]["education"][0]["scale"] == "UNKNOWN"
    assert body["profile"]["education"][0]["cgpa"] == 8.2
    assert body["normalized_grades"][0]["fraction"] is None


def test_normalize_response_shape(
    client: TestClient, minimal_profile: dict[str, Any]
) -> None:
    body = client.post(NORMALIZE_URL, json=minimal_profile).json()
    assert set(body) == {"candidate_id", "profile", "normalized_grades", "changes"}


def test_normalize_preserves_semantic_content(
    client: TestClient, complete_profile: dict[str, Any]
) -> None:
    """Cleaning representation must not drop or alter information."""
    body = client.post(NORMALIZE_URL, json=complete_profile).json()
    profile = body["profile"]

    assert profile["name"] == "Test Candidate"
    assert profile["backlogs"] == 0
    assert profile["preferences"]["work_mode"] == "HYBRID"
    assert profile["preferences"]["job_types"] == ["INTERNSHIP"]
    assert len(profile["experience"]) == 1
    assert profile["experience"][0]["company"] == "Example Corp"
    assert profile["languages"] == ["English"], "case-duplicate collapses"


def test_normalize_rejects_invalid_payload(client: TestClient) -> None:
    assert client.post(NORMALIZE_URL, json={"backlogs": -1}).status_code == 422


# ---------------------------------------------------------------------------------------
# Statelessness — the same request twice yields the same answer, and stores nothing
# ---------------------------------------------------------------------------------------


def test_endpoints_are_stateless(
    client: TestClient, complete_profile: dict[str, Any]
) -> None:
    """No server-side state accumulates between identical calls."""
    first = client.post(NORMALIZE_URL, json=complete_profile).json()
    second = client.post(NORMALIZE_URL, json=complete_profile).json()
    assert first == second

    validated_first = client.post(VALIDATE_URL, json=complete_profile).json()
    validated_second = client.post(VALIDATE_URL, json=complete_profile).json()
    assert validated_first == validated_second


def test_candidate_id_is_not_a_server_lookup_key(
    client: TestClient, minimal_profile: dict[str, Any]
) -> None:
    """Two different ids for identical data produce identical results but for the echo."""
    first = client.post(VALIDATE_URL, json={**minimal_profile, "candidate_id": "a"}).json()
    second = client.post(VALIDATE_URL, json={**minimal_profile, "candidate_id": "b"}).json()

    assert first["candidate_id"] == "a"
    assert second["candidate_id"] == "b"
    assert first["issues"] == second["issues"]


# ---------------------------------------------------------------------------------------
# Privacy — INV-1 and INV-4, verified by evidence (QG-005)
# ---------------------------------------------------------------------------------------


def test_no_candidate_tables_are_registered() -> None:
    """INV-1: no ORM model may represent a candidate, application or evaluation.

    Checked as an **allowlist** rather than a ban list. Weeks 1–2 asserted the set was
    empty, which held then only because no table existed at all; Week 3 introduced the job
    catalogue. Requiring every registered table to be one we named keeps the check strict —
    a personal-data table under an unanticipated name still fails.
    """
    registered = set(Base.metadata.tables)
    unexpected = registered - ALLOWED_OPERATIONAL_TABLES
    assert not unexpected, f"unexpected tables registered: {unexpected}"
    assert not (registered & FORBIDDEN_TABLES)


def test_no_candidate_tables_exist_in_the_database(
    client: TestClient, complete_profile: dict[str, Any]
) -> None:
    """After a full request cycle, the database must still hold no personal-data table."""
    client.post(VALIDATE_URL, json=complete_profile)
    client.post(NORMALIZE_URL, json=complete_profile)

    existing = set(inspect(engine).get_table_names())
    assert not (existing & FORBIDDEN_TABLES), f"forbidden tables present: {existing}"


def test_forbidden_model_modules_do_not_exist() -> None:
    """ADR-011: the dossier §8.2 listing showing these is stale. They must not exist.

    A structural guard, because the likeliest way this architecture breaks is someone
    reading §8.2 at face value and creating the files it lists.
    """
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent
    for forbidden in ("app/models/candidate.py", "app/models/application.py"):
        assert not (project_root / forbidden).exists(), (
            f"{forbidden} exists and must not — see ADR-011"
        )


def test_no_migration_creates_a_forbidden_table() -> None:
    """QG-006 item 2: no migration may create a personal-data table."""
    from pathlib import Path

    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    for migration in versions.glob("*.py"):
        text = migration.read_text(encoding="utf-8").lower()
        for forbidden in FORBIDDEN_TABLES:
            assert f'create_table("{forbidden}"' not in text
            assert f"create_table('{forbidden}'" not in text


def test_validation_errors_do_not_echo_submitted_values(client: TestClient) -> None:
    """INV-4: FastAPI's default 422 echoes the offending input. Ours must not.

    This is the single most likely PII leak in the application: a malformed email or name
    reflected straight back into the caller's logs and error tracker.
    """
    secret = "SENSITIVE-CANDIDATE-VALUE-9f3a2b"
    response = client.post(VALIDATE_URL, json={"email": secret})

    assert response.status_code == 422
    assert secret not in response.text

    body = response.json()
    assert any(d["field"] == "email" for d in body["details"])
    for detail in body["details"]:
        assert "input" not in detail
        assert "ctx" not in detail


def test_unknown_field_error_does_not_echo_its_value(client: TestClient) -> None:
    """`extra=forbid` rejections must name the field without repeating the value."""
    secret = "SECRET-SSN-000-00-0000"
    response = client.post(VALIDATE_URL, json={"national_id": secret})

    assert response.status_code == 422
    assert secret not in response.text


def test_nested_validation_error_does_not_echo_values(client: TestClient) -> None:
    secret = "SECRET-INSTITUTION-NAME-77x"
    response = client.post(
        VALIDATE_URL,
        json={"education": [{"degree": "B.Tech", "institution": secret, "cgpa": -1}]},
    )

    assert response.status_code == 422
    assert secret not in response.text


def test_request_logging_contains_no_candidate_data(
    client: TestClient,
    complete_profile: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """INV-4: logs carry request id, method, path, status, duration — nothing else."""
    with caplog.at_level("DEBUG", logger="eligicore"):
        client.post(NORMALIZE_URL, json=complete_profile)

    logged = "\n".join(record.getMessage() for record in caplog.records)
    for secret in (
        "Test Candidate",
        "test.candidate@example.com",
        "+10000000000",
        "Example Institute of Technology",
        "Example City",
    ):
        assert secret not in logged, f"{secret!r} leaked into logs"

    assert "path=/api/v1/candidates/normalize" in logged
