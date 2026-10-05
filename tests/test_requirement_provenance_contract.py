"""The provenance and evidence contract on a breakdown entry (ADR-030 Step 6, PR A).

Three things are pinned here, and each has its own reason to exist.

**The enum is contract.** ``RequirementProvenance`` moved from :mod:`app.schemas.extraction`
to :mod:`app.schemas.eligibility` so that :class:`RequirementResult` can carry it without a
circular import. A move is only safe if the member names and the wire values survive it
exactly (ADR-010), so both are asserted literally rather than derived from the class.

**The cycle is a real failure mode, not a hypothetical.** ``app.schemas.extraction`` imports
``RequirementType`` from ``app.schemas.eligibility`` at module scope, and ``RequirementType``
is defined *after* the line where the reverse import would sit. A reverse import therefore
fails at interpreter level, which ``from __future__ import annotations`` does not prevent,
because Pydantic resolves the annotation when it builds the model. The import tests run in
**fresh subprocesses** on purpose: once pytest has imported both modules, every later import
is a cache hit and proves nothing.

**PR A changes no verdict.** Provenance is carried, not yet consulted. The precedence tests
below say so out loud, so that the amended D4 precedence has to change them rather than
inheriting an assertion that was already true.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import app
from app.schemas.candidate import CandidateProfile, Confidence, JobType
from app.schemas.eligibility import (
    EligibilityState,
    EvaluationMethod,
    ReasonCode,
    RequirementProvenance,
    RequirementResult,
    RequirementStatus,
    RequirementType,
)
from app.schemas.job import JobRead, JobStatusSchema
from app.services.eligibility_engine import compose_verdict, evaluate_requirements

REPO_ROOT = Path(app.__file__).resolve().parent.parent

#: The breakdown entry's full field set after this PR, in declaration order — which is the
#: order a client reading the OpenAPI schema sees.
EXPECTED_FIELDS = (
    "requirement_type",
    "requirement",
    "candidate_value",
    "status",
    "confidence",
    "method",
    "provenance",
    "reason_code",
    "note",
    "evidence",
)

#: A sentence from a job description. Job text, never candidate text (INV-4).
EVIDENCE = "Minimum CGPA of 7.0 on a 10 point scale is required."


def make_result(**overrides: Any) -> RequirementResult:
    """A valid entry stating only what every entry must state."""
    base: dict[str, Any] = {
        "requirement_type": RequirementType.MIN_CGPA,
        "requirement": "Minimum CGPA 7.0 (SCALE_10)",
        "status": RequirementStatus.PASS,
        "confidence": Confidence.HIGH,
        "method": EvaluationMethod.DETERMINISTIC,
        "reason_code": ReasonCode.MEETS_MINIMUM,
        "note": "The grade meets the stated minimum.",
    }
    base.update(overrides)
    return RequirementResult.model_validate(base)


def make_job(**overrides: Any) -> JobRead:
    """A catalogue job stating no requirements unless overridden."""
    base: dict[str, Any] = {
        "id": "job-0001",
        "company_name": "Example Analytics",
        "role_title": "Software Engineering Intern",
        "job_type": JobType.INTERNSHIP,
        "location": None,
        "description": "",
        "requirements": {},
        "min_cgpa": None,
        "min_cgpa_scale": None,
        "allowed_fields": [],
        "min_degree_level": None,
        "max_backlogs": None,
        "min_grad_year": None,
        "max_grad_year": None,
        "required_skills": [],
        "apply_link": None,
        "deadline": None,
        "source": "test",
        "source_job_id": None,
        "status": JobStatusSchema.ACTIVE,
        "is_active": True,
        "last_verified_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return JobRead.model_validate(base)


def make_profile() -> CandidateProfile:
    return CandidateProfile.model_validate(
        {
            "education": [
                {
                    "degree": "B.Tech",
                    "level": "BACHELORS",
                    "field_of_study": "Computer Science",
                    "grad_year": 2027,
                    "cgpa": 8.0,
                    "scale": "SCALE_10",
                }
            ],
            "backlogs": 0,
        }
    )


def run_python(code: str) -> subprocess.CompletedProcess[str]:
    """Execute code in a fresh interpreter rooted at the repository."""
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


# ---------------------------------------------------------------------------------------
# The enum: two members, and the move changed neither name nor value
# ---------------------------------------------------------------------------------------


def test_requirement_provenance_has_exactly_two_members() -> None:
    """Two classes, and only two (ADR-030 D1). A third would be a new authority tier."""
    assert [member.name for member in RequirementProvenance] == [
        "SOURCE_STATED",
        "PROSE_DERIVED",
    ]


def test_requirement_provenance_values_are_unchanged_by_the_move() -> None:
    """Literal values: the move is contract-neutral only if these survive it (ADR-010)."""
    assert RequirementProvenance.SOURCE_STATED.value == "SOURCE_STATED"
    assert RequirementProvenance.PROSE_DERIVED.value == "PROSE_DERIVED"


def test_requirement_provenance_is_a_string_enum() -> None:
    """Serializes as its value, like every other contract enum in the schema."""
    assert isinstance(RequirementProvenance.SOURCE_STATED, str)
    assert RequirementProvenance("PROSE_DERIVED") is RequirementProvenance.PROSE_DERIVED


def test_both_schema_modules_expose_the_same_enum_object() -> None:
    """``app.models.extracted_requirement`` still imports it from extraction (ADR-030 D18)."""
    from app.schemas import eligibility, extraction

    assert extraction.RequirementProvenance is eligibility.RequirementProvenance


def test_extraction_types_still_pin_their_provenance() -> None:
    """The move did not loosen the literal pinning of ADR-030 D6's output."""
    from app.schemas.extraction import ExtractionProposal, VerifiedDerivedRequirement

    assert (
        VerifiedDerivedRequirement.model_fields["provenance"].default
        is RequirementProvenance.PROSE_DERIVED
    )
    assert (
        ExtractionProposal.model_fields["provenance"].default
        is RequirementProvenance.PROSE_DERIVED
    )


# ---------------------------------------------------------------------------------------
# Circular-import safety — fresh interpreters, both orders
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "first,second",
    [
        ("app.schemas.eligibility", "app.schemas.extraction"),
        ("app.schemas.extraction", "app.schemas.eligibility"),
    ],
)
def test_schema_modules_import_in_either_order(first: str, second: str) -> None:
    """Neither module may require the other to have been imported first."""
    result = run_python(f"import {first}; import {second}")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "module",
    [
        "app.schemas.eligibility",
        "app.schemas.extraction",
        "app.models.extracted_requirement",
        "app.services.eligibility_engine",
    ],
)
def test_each_module_imports_standalone(module: str) -> None:
    """Each is importable on its own, with nothing else primed in ``sys.modules``."""
    result = run_python(f"import {module}")
    assert result.returncode == 0, result.stderr


def test_provenance_resolves_identically_whichever_module_is_imported_first() -> None:
    """A duplicated enum would compare unequal across import orders and nothing else."""
    code = (
        "import app.schemas.extraction as x\n"
        "import app.schemas.eligibility as e\n"
        "assert x.RequirementProvenance is e.RequirementProvenance\n"
        "assert x.RequirementProvenance.SOURCE_STATED.value == 'SOURCE_STATED'\n"
        "print('ok')\n"
    )
    result = run_python(code)
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


# ---------------------------------------------------------------------------------------
# RequirementResult shape
# ---------------------------------------------------------------------------------------


def test_requirement_result_declares_exactly_the_expected_fields() -> None:
    assert tuple(RequirementResult.model_fields) == EXPECTED_FIELDS


def test_existing_fields_keep_their_requiredness() -> None:
    """The pre-existing fields are untouched by this PR."""
    fields = RequirementResult.model_fields
    for name in (
        "requirement_type",
        "requirement",
        "status",
        "confidence",
        "method",
        "reason_code",
        "note",
    ):
        assert fields[name].is_required(), name
    assert not fields["candidate_value"].is_required()


def test_a_pre_existing_construction_still_validates() -> None:
    """Callers that predate this PR supply neither new field and must keep working."""
    entry = make_result()
    assert entry.status is RequirementStatus.PASS
    assert entry.method is EvaluationMethod.DETERMINISTIC


def test_unknown_fields_are_still_forbidden() -> None:
    """``extra='forbid'`` survives the addition (ADR-010)."""
    with pytest.raises(ValidationError):
        make_result(provenance_hint="SOURCE_STATED")


# ---------------------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------------------


def test_provenance_defaults_to_source_stated() -> None:
    """Every requirement in the catalogue today came from a structured column."""
    assert make_result().provenance is RequirementProvenance.SOURCE_STATED


def test_provenance_accepts_prose_derived() -> None:
    entry = make_result(provenance=RequirementProvenance.PROSE_DERIVED, evidence=EVIDENCE)
    assert entry.provenance is RequirementProvenance.PROSE_DERIVED


def test_provenance_rejects_an_unknown_class() -> None:
    """A third provenance is a new ADR, not a new string."""
    with pytest.raises(ValidationError):
        make_result(provenance="INFERRED")


def test_provenance_is_independent_of_method() -> None:
    """``AI_REASONING`` about a column-stated requirement is still ``SOURCE_STATED``.

    This is the pairing D4a exists to keep apart: method names the stage that computed the
    result, provenance names the authority of the requirement behind it (ADR-030 D3).
    """
    entry = make_result(
        requirement_type=RequirementType.ALLOWED_FIELDS,
        requirement="Permitted fields of study: Computer Science",
        method=EvaluationMethod.AI_REASONING,
        confidence=Confidence.MEDIUM,
        reason_code=ReasonCode.AI_FIELD_RELATED,
    )
    assert entry.method is EvaluationMethod.AI_REASONING
    assert entry.provenance is RequirementProvenance.SOURCE_STATED


# ---------------------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------------------


def test_evidence_defaults_to_none() -> None:
    """A source-stated requirement rests on no sentence: it came from a field."""
    assert make_result().evidence is None


def test_evidence_carries_the_supporting_sentence() -> None:
    assert make_result(evidence=EVIDENCE).evidence == EVIDENCE


def test_evidence_rejects_an_empty_string() -> None:
    """Present-but-empty evidence would claim support that does not exist (ADR-006)."""
    with pytest.raises(ValidationError):
        make_result(evidence="")


def test_the_schema_does_not_yet_couple_evidence_to_provenance() -> None:
    """Deliberate: the first code able to produce a derived entry is the engine-boundary
    PR, and the coupling belongs with it rather than ahead of it."""
    assert make_result(provenance=RequirementProvenance.PROSE_DERIVED).evidence is None


# ---------------------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------------------


def test_both_fields_serialize_by_value() -> None:
    dumped = make_result(
        provenance=RequirementProvenance.PROSE_DERIVED, evidence=EVIDENCE
    ).model_dump(mode="json")
    assert dumped["provenance"] == "PROSE_DERIVED"
    assert dumped["evidence"] == EVIDENCE


def test_a_default_entry_serializes_with_both_new_keys_present() -> None:
    """Clients see the keys even when nothing was derived — absent is not null."""
    dumped = make_result().model_dump(mode="json")
    assert dumped["provenance"] == "SOURCE_STATED"
    assert dumped["evidence"] is None


@pytest.mark.parametrize("provenance", list(RequirementProvenance))
def test_round_trips_through_json(provenance: RequirementProvenance) -> None:
    original = make_result(provenance=provenance, evidence=EVIDENCE)
    restored = RequirementResult.model_validate_json(original.model_dump_json())
    assert restored == original
    assert restored.provenance is provenance
    assert restored.evidence == EVIDENCE


def test_the_published_schema_documents_both_fields() -> None:
    """ADR-006: the breakdown is the explanation, so the contract must describe it."""
    properties = RequirementResult.model_json_schema()["properties"]
    assert properties["provenance"]["description"]
    assert properties["evidence"]["description"]


# ---------------------------------------------------------------------------------------
# Existing engine behaviour is unchanged
# ---------------------------------------------------------------------------------------


def test_every_engine_result_is_source_stated_with_no_evidence() -> None:
    """The engine reads ``JobRead`` columns only, so everything it emits is source-stated."""
    job = make_job(
        min_cgpa=7.0,
        min_cgpa_scale="SCALE_10",
        min_grad_year=2026,
        max_grad_year=2028,
        max_backlogs=0,
        min_degree_level="BACHELORS",
        allowed_fields=["Computer Science"],
    )
    results = evaluate_requirements(make_profile(), job)
    assert len(results) == 5
    assert all(r.provenance is RequirementProvenance.SOURCE_STATED for r in results)
    assert all(r.evidence is None for r in results)


def test_provenance_does_not_yet_affect_the_verdict() -> None:
    """PR A carries provenance; it does not consult it.

    The amended D4 precedence is a separate PR. Until it lands a prose-derived FAIL still
    composes ``NOT_ELIGIBLE``, and asserting that here means the precedence PR must change
    this test rather than inherit it already passing.
    """
    failed_source = make_result(
        status=RequirementStatus.FAIL, reason_code=ReasonCode.BELOW_MINIMUM
    )
    failed_derived = failed_source.model_copy(
        update={"provenance": RequirementProvenance.PROSE_DERIVED, "evidence": EVIDENCE}
    )
    assert compose_verdict([failed_source]) is EligibilityState.NOT_ELIGIBLE
    assert compose_verdict([failed_derived]) is EligibilityState.NOT_ELIGIBLE


def test_evidence_does_not_affect_the_verdict() -> None:
    passed = make_result()
    assert compose_verdict([passed]) is compose_verdict(
        [passed.model_copy(update={"evidence": EVIDENCE})]
    )
