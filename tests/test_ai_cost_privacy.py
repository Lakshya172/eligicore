"""Week 8 Slice 8A — the privacy boundary around cost logging (ADR-026 D8, D9).

Two obligations, both structural rather than behavioural, because a boundary that holds only
while nobody changes a default is not a boundary:

1. **Generation is excluded.** ``generate_application_content`` gets no token, length or cost
   logging, no usage sink, and no setting that could give it one. ADR-025 bars logging any
   length that could characterize one candidate's content; a token count is such a length,
   and ADR-026 D8 resolved that by scope exclusion rather than by amending ADR-025.
2. **Cost is not about a person.** No candidate field and no ``candidate_id`` reaches a cost
   log line, nothing is persisted, and a cost figure is never keyed to anyone.

The generation tests are written against the *source and the signatures*, not only against
behaviour: a behavioural test passes again the moment someone adds the field back with a flag
defaulted off.
"""

from __future__ import annotations

import ast
import inspect
import io
import json
import logging
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai import ai_service as ai_service_module
from app.ai.ai_service import AIService, get_lazy_ai_service
from app.ai.providers.base import AIProvider
from app.ai.providers.gemini import GeminiFlashProvider
from app.ai.providers.mock import MockAIProvider
from app.config import ModelCostRate, Settings
from app.database import Base, get_db
from app.main import app
from app.models.job import Job, JobStatus
from app.schemas.candidate import JobType

# Markers. Every one is a value that must never appear in an operational log line.
M_ID = "COST-CAND-ID-8a"
M_NAME = "Costmarker Person"
M_EMAIL = "costmarker@example.com"
M_PHONE = "+19995550188"
M_LOCATION = "Costmarkerville"
M_INSTITUTION = "Costmarker Institute"
M_CGPA = 7.91
M_BACKLOGS = 3
M_EMPLOYER = "Costmarker Industries"
M_LANGUAGE = "Costmarkerish"
M_RESUME = "COSTMARKER-RESUME-TEXT"
M_SKILL = "Python"
M_PROJECT = "Costmarker Ledger"
M_QUESTION = "Describe the Costmarker Ledger project and your CGPA."
M_COMPANY = "Costmarker Target Co"

GENERATION_SOURCE = Path(ai_service_module.__file__).read_text(encoding="utf-8")


def generation_method_source() -> str:
    """The body of ``AIService.generate_application_content``, as written."""
    tree = ast.parse(GENERATION_SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "generate_application_content":
            return ast.get_source_segment(GENERATION_SOURCE, node) or ""
    raise AssertionError("generate_application_content not found in AIService")


# ---------------------------------------------------------------------------------------
# 1. Generation is structurally excluded from cost accounting
# ---------------------------------------------------------------------------------------


def test_generation_has_no_usage_parameter_on_any_provider() -> None:
    """There is no parameter for a sink to arrive through — the exclusion is the signature."""
    for cls in (AIProvider, MockAIProvider, GeminiFlashProvider):
        params = inspect.signature(cls.generate_application_content).parameters
        assert "usage" not in params, cls
        assert set(params) == {"self", "evidence", "job", "questions", "limits"}, cls


def test_generation_service_method_never_builds_or_passes_a_sink() -> None:
    source = generation_method_source()
    for forbidden in ("UsageSink", "usage=", "_accounting", "cost_micros", "sink"):
        assert forbidden not in source, forbidden


def test_generation_log_line_emits_no_token_length_or_cost_field() -> None:
    source = generation_method_source()
    for forbidden in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost_micros",
        "input_chars",
    ):
        assert forbidden not in source, forbidden


def test_the_only_measurement_generation_takes_is_the_question_count() -> None:
    """ADR-025 permits counts and bars lengths that characterize content.

    ``len(questions)`` is how many questions were asked — a count of the request's shape.
    ``len(draft)`` or ``len(evidence)`` would describe one candidate's content. This pins
    that every measurement in the method is the former.
    """
    measured = [
        ast.unparse(node.args[0])
        for node in ast.walk(ast.parse(generation_method_source()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "len"
    ]
    assert measured and set(measured) == {"questions"}, measured


def test_generation_log_line_still_carries_exactly_its_week_7_fields() -> None:
    """Unchanged, not merely free of new fields."""
    source = generation_method_source()
    for expected in (
        "operation=generate_application_content",
        "questions=%d",
        "duration_ms=%.1f",
        "outcome=success",
        "outcome=error",
    ):
        assert expected in source, expected


def test_no_setting_could_enable_generation_cost_logging() -> None:
    """A disabled flag is a latent violation. There must be no flag at all."""
    names = set(Settings.model_fields)
    for suspicious in (
        "log_generation_cost",
        "generation_cost_logging",
        "ai_log_generation_usage",
        "generation_usage",
    ):
        assert suspicious not in names, suspicious
    for name in names:
        assert not ("generation" in name and ("cost" in name or "usage" in name or "token" in name))


@pytest.mark.anyio
async def test_a_live_generation_call_logs_no_token_or_cost_field(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.schemas.application import ApplicationEvidence, GenerationLimits, JobBrief

    service = AIService(
        MockAIProvider(),
        settings=Settings(
            ai_cost_rates={
                "mock:mock-deterministic-v1": ModelCostRate(
                    prompt_micros_per_1k=100, completion_micros_per_1k=400
                )
            }
        ),
    )
    with caplog.at_level(logging.DEBUG, logger="eligicore.ai"):
        await service.generate_application_content(
            ApplicationEvidence(skills=[M_SKILL]),
            JobBrief(job_id="job-1", company_name=M_COMPANY, role_title="Engineer"),
            [],
            GenerationLimits(cover_letter_max_words=200),
        )

    lines = [r.getMessage() for r in caplog.records]
    assert any("generate_application_content" in line for line in lines)
    for line in lines:
        for forbidden in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_micros"):
            assert forbidden not in line, line


# ---------------------------------------------------------------------------------------
# 2. Cost logging carries no candidate data
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_cost_logging_carries_no_resume_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    resume = f"{M_NAME} {M_EMAIL} {M_PHONE} {M_RESUME} CGPA {M_CGPA}/10 {M_INSTITUTION}"
    service = AIService(
        MockAIProvider(),
        settings=Settings(
            ai_cost_rates={
                "mock:mock-deterministic-v1": ModelCostRate(
                    prompt_micros_per_1k=100, completion_micros_per_1k=400
                )
            }
        ),
    )
    with caplog.at_level(logging.DEBUG, logger="eligicore.ai"):
        await service.extract_resume(resume)

    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert "prompt_tokens=" in logs, "the cost fields must actually be there to be tested"
    for marker in (M_NAME, M_EMAIL, M_PHONE, M_RESUME, M_INSTITUTION, str(M_CGPA)):
        assert marker not in logs, marker


@pytest.mark.anyio
async def test_cost_logging_carries_no_field_of_study_or_permitted_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = AIService(MockAIProvider(), settings=Settings())
    with caplog.at_level(logging.DEBUG, logger="eligicore.ai"):
        await service.assess_field_relatedness("MARKER-FIELD-8a", ["MARKER-ALLOWED-8a"])

    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert "total_tokens=" in logs
    assert "MARKER-FIELD-8a" not in logs
    assert "MARKER-ALLOWED-8a" not in logs


def test_no_cost_field_is_keyed_by_a_candidate() -> None:
    """A per-candidate cost ledger is candidate persistence wearing an accounting hat."""
    for module in ("app/ai/ai_service.py", "app/ai/usage.py"):
        source = Path(module).read_text(encoding="utf-8")
        tree = ast.parse(source)
        executable = [
            node
            for node in ast.walk(tree)
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str))
        ]
        names = {
            node.id
            for node in executable
            if isinstance(node, ast.Name)
        } | {
            node.attr
            for node in executable
            if isinstance(node, ast.Attribute)
        }
        assert not [n for n in names if "candidate" in n.lower()], module


def test_usage_module_has_no_parameter_that_could_carry_content() -> None:
    from app.ai import usage as usage_module

    for name, obj in vars(usage_module).items():
        if name.startswith("_") or not callable(obj):
            continue
        try:
            params = inspect.signature(obj).parameters
        except (TypeError, ValueError):
            continue
        for param in params:
            assert "text" not in param and "profile" not in param and "id" != param, (name, param)


def test_nothing_in_slice_8a_writes_to_a_store() -> None:
    for module in ("app/ai/usage.py", "app/ai/ai_service.py"):
        source = Path(module).read_text(encoding="utf-8")
        for forbidden in ("session.add", "commit(", "open(", "Path(", "lru_cache"):
            assert forbidden not in source, (module, forbidden)


# ---------------------------------------------------------------------------------------
# 3. End to end: a real request, a real log stream, a real database
# ---------------------------------------------------------------------------------------


def _client() -> tuple[TestClient, Any]:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(
            Job(
                id="job-1",
                company_name=M_COMPANY,
                role_title="Backend Engineer",
                job_type=JobType.INTERNSHIP,
                description="Python",
                requirements={},
                allowed_fields=[],
                required_skills=[M_SKILL],
                source="curated",
                source_job_id="A",
                content_hash="0" * 64,
                status=JobStatus.ACTIVE,
            )
        )
        session.commit()

    def db() -> Any:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_lazy_ai_service] = lambda: AIService(
        MockAIProvider(),
        settings=Settings(
            ai_cost_rates={
                "mock:mock-deterministic-v1": ModelCostRate(
                    prompt_micros_per_1k=100, completion_micros_per_1k=400
                )
            }
        ),
    )
    return TestClient(app), engine


PROFILE: dict[str, Any] = {
    "candidate_id": M_ID,
    "name": M_NAME,
    "email": M_EMAIL,
    "phone": M_PHONE,
    "location": M_LOCATION,
    "skills": [M_SKILL],
    "projects": [{"name": M_PROJECT}],
    "experience": [{"title": "Intern", "company": M_EMPLOYER}],
    "education": [
        {
            "degree": "B.Tech",
            "institution": M_INSTITUTION,
            "cgpa": M_CGPA,
            "scale": "SCALE_10",
            "field_of_study": "Information Technology",
        }
    ],
    "languages": [M_LANGUAGE],
    "backlogs": M_BACKLOGS,
    "resume_raw_text": M_RESUME,
}

ALL_MARKERS = {
    "candidate_id": M_ID,
    "name": M_NAME,
    "email": M_EMAIL,
    "phone": M_PHONE,
    "location": M_LOCATION,
    "institution": M_INSTITUTION,
    "cgpa": str(M_CGPA),
    "backlogs": f'"backlogs": {M_BACKLOGS}',
    "employer": M_EMPLOYER,
    "language": M_LANGUAGE,
    "resume text": M_RESUME,
    "question text": M_QUESTION,
    "project name": M_PROJECT,
    "target company": M_COMPANY,
}


def test_a_prepare_request_leaks_nothing_and_writes_nothing() -> None:
    """The generation path, end to end, with cost logging switched on everywhere else."""
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    root = logging.getLogger()
    root.addHandler(handler)
    previous = root.level
    root.setLevel(logging.DEBUG)

    client, engine = _client()
    try:
        before = "\n".join(engine.connect().connection.iterdump())
        response = client.post(
            "/api/v1/applications/prepare",
            json={
                "profile": PROFILE,
                "job_id": "job-1",
                "questions": [{"id": "q1", "text": M_QUESTION}],
            },
        )
        after = "\n".join(engine.connect().connection.iterdump())
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)
        app.dependency_overrides.clear()

    assert response.status_code == 200
    logs = buffer.getvalue()

    for label, marker in ALL_MARKERS.items():
        assert marker not in logs, label

    for forbidden in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_micros"):
        assert forbidden not in logs, f"{forbidden} reached the generation path"

    assert before == after, "a prepare request must write nothing"
    assert M_RESUME not in response.text


def test_an_eligibility_request_logs_cost_without_candidate_data() -> None:
    """The instrumented path: cost fields present, candidate data absent, nothing written."""
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    root = logging.getLogger()
    root.addHandler(handler)
    previous = root.level
    root.setLevel(logging.DEBUG)

    client, engine = _client()
    try:
        before = "\n".join(engine.connect().connection.iterdump())
        response = client.post(
            "/api/v1/eligibility/check",
            json={"profile": PROFILE, "job_ids": ["job-1"]},
        )
        after = "\n".join(engine.connect().connection.iterdump())
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)
        app.dependency_overrides.clear()

    assert response.status_code == 200
    logs = buffer.getvalue()

    for label, marker in ALL_MARKERS.items():
        assert marker not in logs, label

    for line in logs.splitlines():
        if "cost_micros=" in line:
            assert M_ID not in line
            assert re.search(r"\bcost_micros=(\d+|unknown)\b", line), line

    assert before == after, "an eligibility request must write nothing"


def test_the_response_body_of_an_instrumented_endpoint_is_unchanged() -> None:
    """Cost accounting is operational. It must be invisible at the contract."""
    client, _ = _client()
    try:
        first = client.post(
            "/api/v1/eligibility/check", json={"profile": PROFILE, "job_ids": ["job-1"]}
        )
    finally:
        app.dependency_overrides.clear()

    body = first.json()
    assert first.status_code == 200
    flat = json.dumps(body)
    for forbidden in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_micros", "usage"):
        assert forbidden not in flat, forbidden
