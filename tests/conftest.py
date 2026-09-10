"""Shared test fixtures.

**Every fixture here is obviously synthetic.** No real names, emails, phone numbers or
institutions appear anywhere in this repository's tests
(``standards/testing.md`` §5, QG-005 item 19).

Profiles are built as dictionaries and passed in request bodies, exactly as a client would
send them. Nothing is ever seeded into a database — there is no table to seed (ADR-002,
ADR-011).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app

#: Tables the server is permitted to have. An **allowlist**, deliberately: naming only the
#: forbidden tables would let a fourth personal-data table through under a name nobody
#: thought to ban. Anything registered outside this set fails the privacy tests, which is
#: the behaviour we want when someone adds a model without thinking about INV-1.
#:
#: Weeks 1–2 asserted this set was empty, which was true then but was never the invariant.
#: Week 3 adds the first operational tables; the rule — operational data only, no personal
#: data — is unchanged.
ALLOWED_OPERATIONAL_TABLES = {"jobs", "ingestion_state"}

#: Names that must never appear, checked in addition to the allowlist so the intent stays
#: legible at each call site.
FORBIDDEN_TABLES = {
    "candidates",
    "candidate",
    "applications",
    "application",
    "evaluations",
    "evaluation",
    "profiles",
    "resumes",
}


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on asyncio only.

    anyio would otherwise parameterize every async test across asyncio and trio, doubling
    the suite to exercise a backend this project does not use.
    """
    return "asyncio"


@pytest.fixture
def client() -> TestClient:
    """A test client for the FastAPI application."""
    return TestClient(app)


@pytest.fixture
def minimal_profile() -> dict[str, Any]:
    """The smallest profile that carries an education record."""
    return {
        "education": [
            {
                "degree": "B.Tech",
                "level": "BACHELORS",
                "field_of_study": "Information Technology",
                "institution": "Example Institute of Technology",
                "grad_year": 2027,
                "cgpa": 8.2,
                "scale": "SCALE_10",
            }
        ]
    }


@pytest.fixture
def complete_profile() -> dict[str, Any]:
    """A fully populated, entirely fictional candidate profile."""
    return {
        "candidate_id": "client-generated-test-id-0001",
        "name": "Test Candidate",
        "email": "test.candidate@example.com",
        "phone": "+10000000000",
        "location": "Example City",
        "education": [
            {
                "degree": "B.Tech",
                "level": "BACHELORS",
                "field_of_study": "Information Technology",
                "institution": "Example Institute of Technology",
                "grad_year": 2027,
                "cgpa": 8.2,
                "scale": "SCALE_10",
            },
            {
                "degree": "High School",
                "level": "HIGH_SCHOOL",
                "institution": "Example Public School",
                "grad_year": 2023,
                "cgpa": 92.0,
                "scale": "PERCENTAGE",
            },
        ],
        "experience": [
            {
                "title": "Software Engineering Intern",
                "company": "Example Corp",
                "duration": "Jun 2026 - Aug 2026",
                "description": "Built internal tooling.",
            }
        ],
        "skills": ["Python", "ReactJS", "React.js", "  SQL  ", "docker"],
        "projects": [{"name": "Example Project", "description": "A sample project."}],
        "certifications": [{"name": "Example Certification", "issuer": "Example Body"}],
        "languages": ["English", "english"],
        "backlogs": 0,
        "preferences": {
            "locations": ["Example City", "Remote"],
            "job_types": ["INTERNSHIP"],
            "work_mode": "HYBRID",
        },
        "field_confidence": {"name": "HIGH", "email": "MEDIUM"},
    }
