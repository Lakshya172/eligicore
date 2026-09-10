"""Resume parser tests: format detection, text extraction, temp-file lifecycle, truthfulness.

Exercises the service directly — no FastAPI, no server. That it can be tested this way is
itself the check on INV-7.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.ai.ai_service import AIService
from app.ai.errors import AIProviderUnavailableError, AIResponseInvalidError
from app.ai.providers.mock import MockAIProvider
from app.schemas.candidate import Confidence, GradeScale
from app.schemas.resume import (
    ExtractedEducation,
    ResumeExtraction,
    ResumeParseStatus,
    SourceFormat,
)
from app.services.resume_parser import (
    ResumeParsingError,
    build_profile,
    check_traceability,
    detect_format,
    extract_text,
    normalize_text,
    parse_resume,
)
from tests.fixtures_documents import (
    SAMPLE_RESUME_LINES,
    SAMPLE_RESUME_NO_SCALE_LINES,
    build_corrupt_docx,
    build_corrupt_pdf,
    build_docx,
    build_docx_with_table,
    build_empty_pdf,
    build_pdf,
)

# ---------------------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------------------


def test_detects_pdf_from_magic_bytes() -> None:
    assert detect_format("resume.pdf", build_pdf(SAMPLE_RESUME_LINES)) is SourceFormat.PDF


def test_detects_docx_from_magic_bytes() -> None:
    assert detect_format("resume.docx", build_docx(SAMPLE_RESUME_LINES)) is SourceFormat.DOCX


def test_format_comes_from_content_not_filename() -> None:
    """A file named .pdf is not a PDF because it says so."""
    docx = build_docx(SAMPLE_RESUME_LINES)
    assert detect_format("actually_a_docx.pdf", docx) is SourceFormat.DOCX


@pytest.mark.parametrize(
    "content",
    [b"plain text resume", b"\x89PNG\r\n\x1a\n", b"", b"<html><body>cv</body></html>"],
)
def test_unsupported_types_are_rejected(content: bytes) -> None:
    with pytest.raises(ResumeParsingError) as exc:
        detect_format("resume.txt", content)
    assert exc.value.code == "UNSUPPORTED_FILE_TYPE"


# ---------------------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------------------


def test_extracts_text_from_pdf() -> None:
    text = extract_text(build_pdf(SAMPLE_RESUME_LINES), SourceFormat.PDF)
    assert "Test Candidate" in text
    assert "CGPA 8.2/10" in text
    assert "Python" in text


def test_extracts_text_from_docx() -> None:
    text = extract_text(build_docx(SAMPLE_RESUME_LINES), SourceFormat.DOCX)
    assert "Test Candidate" in text
    assert "B.Tech Information Technology" in text


def test_extracts_docx_table_cells() -> None:
    """Reading paragraphs alone silently misses table-laid-out resumes entirely."""
    docx = build_docx_with_table([("Degree", "B.Tech"), ("CGPA", "8.2/10")])
    text = extract_text(docx, SourceFormat.DOCX)
    assert "B.Tech" in text
    assert "8.2/10" in text


def test_empty_pdf_is_rejected() -> None:
    with pytest.raises(ResumeParsingError) as exc:
        extract_text(build_empty_pdf(), SourceFormat.PDF)
    assert exc.value.code == "EMPTY_DOCUMENT"


def test_empty_docx_is_rejected() -> None:
    with pytest.raises(ResumeParsingError) as exc:
        extract_text(build_docx([]), SourceFormat.DOCX)
    assert exc.value.code == "EMPTY_DOCUMENT"


def test_corrupt_pdf_is_rejected() -> None:
    with pytest.raises(ResumeParsingError) as exc:
        extract_text(build_corrupt_pdf(), SourceFormat.PDF)
    assert exc.value.code == "CORRUPT_DOCUMENT"


def test_corrupt_docx_is_rejected() -> None:
    with pytest.raises(ResumeParsingError) as exc:
        extract_text(build_corrupt_docx(), SourceFormat.DOCX)
    assert exc.value.code == "CORRUPT_DOCUMENT"


def test_parse_errors_never_contain_document_content() -> None:
    """A pdfminer or docx error message can quote the document. It must not surface."""
    marker = b"SECRET-RESUME-MARKER-4f2a"
    corrupt = b"%PDF-1.4\n" + marker + b"\nnot a real pdf\n%%EOF"
    with pytest.raises(ResumeParsingError) as exc:
        extract_text(corrupt, SourceFormat.PDF)
    assert marker.decode() not in str(exc.value)
    assert marker.decode() not in exc.value.message


# ---------------------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------------------


def test_normalize_collapses_whitespace_and_preserves_lines() -> None:
    raw = "Test    Candidate  \n\n\n\n  B.Tech   IT  \n"
    assert normalize_text(raw) == "Test Candidate\n\nB.Tech IT"


def test_normalize_handles_empty_input() -> None:
    assert normalize_text("") == ""
    assert normalize_text("   \n\n  ") == ""


# ---------------------------------------------------------------------------------------
# Temporary-file lifecycle (INV-11)
# ---------------------------------------------------------------------------------------


def _temp_resume_files() -> set[Path]:
    """Temporary files this application would have created, by extension."""
    root = Path(tempfile.gettempdir())
    return {p for p in root.glob("*.pdf")} | {p for p in root.glob("*.docx")}


def test_temp_file_removed_on_success() -> None:
    before = _temp_resume_files()
    extract_text(build_pdf(SAMPLE_RESUME_LINES), SourceFormat.PDF)
    assert not (_temp_resume_files() - before), "a temporary file survived a successful parse"


def test_temp_file_removed_on_failure() -> None:
    """The failure path is the one that gets forgotten — hence its own test."""
    before = _temp_resume_files()
    with pytest.raises(ResumeParsingError):
        extract_text(build_corrupt_pdf(), SourceFormat.PDF)
    assert not (_temp_resume_files() - before), "a temporary file survived a failed parse"


def test_temp_file_removed_on_empty_document() -> None:
    before = _temp_resume_files()
    with pytest.raises(ResumeParsingError):
        extract_text(build_docx([]), SourceFormat.DOCX)
    assert not (_temp_resume_files() - before)


# ---------------------------------------------------------------------------------------
# Truthfulness — traceability
# ---------------------------------------------------------------------------------------


def test_traceable_skills_are_kept() -> None:
    extraction = ResumeExtraction(skills=["Python", "React"])
    kept, issues = check_traceability(extraction, "Skills: Python, React, SQL")
    assert kept == ["Python", "React"]
    assert issues == []


def test_untraceable_skill_is_removed() -> None:
    """A model will happily add a skill a candidate 'probably' has. Plausibility is not evidence."""
    extraction = ResumeExtraction(skills=["Python", "Kubernetes"])
    kept, issues = check_traceability(extraction, "Skills: Python, React")

    assert kept == ["Python"]
    assert len(issues) == 1
    assert issues[0].code == "UNTRACEABLE_SKILL"


def test_traceability_ignores_case_and_punctuation() -> None:
    extraction = ResumeExtraction(skills=["Node.js", "REACT"])
    kept, _ = check_traceability(extraction, "Worked with nodejs and react")
    assert kept == ["Node.js", "REACT"]


def test_untraceable_skill_message_does_not_contain_the_skill() -> None:
    extraction = ResumeExtraction(skills=["SECRETSKILLXYZ"])
    _, issues = check_traceability(extraction, "Skills: Python")
    assert "SECRETSKILLXYZ" not in issues[0].message


def test_fabricated_seniority_is_not_kept() -> None:
    """Section 12's example: 'React' must not become 'Senior React Engineer'."""
    extraction = ResumeExtraction(skills=["Senior React Engineer"])
    kept, issues = check_traceability(extraction, "Skills: React")
    assert kept == []
    assert issues[0].code == "UNTRACEABLE_SKILL"


# ---------------------------------------------------------------------------------------
# Extraction -> profile
# ---------------------------------------------------------------------------------------


def test_build_profile_preserves_grade_and_scale() -> None:
    extraction = ResumeExtraction(
        education=[ExtractedEducation(degree="B.Tech", cgpa=8.2, scale=GradeScale.SCALE_10)]
    )
    profile, _, _ = build_profile(extraction, "B.Tech CGPA 8.2/10", None)

    assert profile.education[0].cgpa == 8.2
    assert profile.education[0].scale is GradeScale.SCALE_10


def test_missing_scale_survives_extraction_as_unknown() -> None:
    """The rule that matters most, checked at the parser layer too."""
    extraction = ResumeExtraction(
        education=[ExtractedEducation(degree="B.Tech", cgpa=8.2)],
        field_confidence={"education[0].cgpa": Confidence.HIGH},
    )
    profile, confidence, issues = build_profile(extraction, "B.Tech CGPA 8.2", None)

    assert profile.education[0].scale is GradeScale.UNKNOWN
    assert profile.education[0].cgpa == 8.2
    assert any(i.code == "MISSING_SCALE" for i in issues)


def test_deterministic_rule_overrides_model_confidence() -> None:
    """A model's confidence in itself is a claim, not a measurement (ADR-003 precedence)."""
    extraction = ResumeExtraction(
        education=[ExtractedEducation(degree="B.Tech", cgpa=8.2)],
        field_confidence={"education[0].cgpa": Confidence.HIGH},
    )
    _, confidence, _ = build_profile(extraction, "CGPA 8.2", None)

    assert confidence["education[0].cgpa"] is Confidence.LOW


def test_missing_backlogs_is_never_coerced_to_zero() -> None:
    extraction = ResumeExtraction(skills=["Python"])
    profile, _, issues = build_profile(extraction, "Python", None)

    assert profile.backlogs is None
    assert any(i.code == "MISSING_BACKLOGS" for i in issues)


def test_untraceable_skill_lowers_skills_confidence() -> None:
    extraction = ResumeExtraction(
        skills=["Python", "Kubernetes"],
        field_confidence={"skills": Confidence.HIGH},
    )
    _, confidence, _ = build_profile(extraction, "Skills: Python", None)
    assert confidence["skills"] is Confidence.LOW


def test_empty_extraction_yields_empty_profile_not_invented_data() -> None:
    profile, _, issues = build_profile(ResumeExtraction(), "some text", None)

    assert profile.name is None
    assert profile.email is None
    assert profile.education == []
    assert profile.skills == []
    assert profile.backlogs is None
    assert any(i.code == "NO_EDUCATION_EXTRACTED" for i in issues)


def test_candidate_id_is_echoed_not_generated() -> None:
    profile, _, _ = build_profile(ResumeExtraction(), "text", "client-id-1")
    assert profile.candidate_id == "client-id-1"
    profile_none, _, _ = build_profile(ResumeExtraction(), "text", None)
    assert profile_none.candidate_id is None


# ---------------------------------------------------------------------------------------
# End-to-end orchestration
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_parse_resume_end_to_end_pdf() -> None:
    service = AIService(MockAIProvider())
    parsed, source_format = await parse_resume(
        build_pdf(SAMPLE_RESUME_LINES), "resume.pdf", service
    )

    assert source_format is SourceFormat.PDF
    assert parsed.profile.email == "test.candidate@example.com"
    assert parsed.profile.education[0].scale is GradeScale.SCALE_10
    assert parsed.characters_extracted > 0


@pytest.mark.anyio
async def test_parse_resume_no_scale_stays_unknown() -> None:
    service = AIService(MockAIProvider())
    parsed, _ = await parse_resume(
        build_pdf(SAMPLE_RESUME_NO_SCALE_LINES), "resume.pdf", service
    )

    assert parsed.profile.education[0].cgpa == 8.2
    assert parsed.profile.education[0].scale is GradeScale.UNKNOWN
    assert any(i.code == "MISSING_SCALE" for i in parsed.issues)


@pytest.mark.anyio
async def test_parse_resume_reports_partial_when_fields_missing() -> None:
    service = AIService(MockAIProvider())
    parsed, _ = await parse_resume(
        build_pdf(SAMPLE_RESUME_NO_SCALE_LINES), "resume.pdf", service
    )
    assert parsed.status in (ResumeParseStatus.PARTIAL, ResumeParseStatus.NEEDS_REVIEW)


@pytest.mark.anyio
async def test_ai_unavailable_becomes_a_parsing_error() -> None:
    service = AIService(MockAIProvider(fail_with=AIProviderUnavailableError("down")))
    with pytest.raises(ResumeParsingError) as exc:
        await parse_resume(build_pdf(SAMPLE_RESUME_LINES), "r.pdf", service)
    assert exc.value.code == "AI_UNAVAILABLE"


@pytest.mark.anyio
async def test_invalid_ai_response_becomes_a_parsing_error() -> None:
    """Malformed AI output is expected occasionally — never a silent pass, never a crash."""
    service = AIService(MockAIProvider(raise_invalid_response=True))
    with pytest.raises(ResumeParsingError) as exc:
        await parse_resume(build_pdf(SAMPLE_RESUME_LINES), "r.pdf", service)
    assert exc.value.code == "AI_RESPONSE_INVALID"


@pytest.mark.anyio
async def test_insufficient_text_is_rejected() -> None:
    service = AIService(MockAIProvider())
    with pytest.raises(ResumeParsingError) as exc:
        await parse_resume(
            build_pdf(["hi"]), "r.pdf", service, min_characters=50
        )
    assert exc.value.code == "INSUFFICIENT_TEXT"


@pytest.mark.anyio
async def test_oversized_text_is_truncated_and_reported() -> None:
    service = AIService(MockAIProvider())
    long_resume = list(SAMPLE_RESUME_LINES) + [f"Line {i} of filler content" for i in range(400)]
    parsed, _ = await parse_resume(
        build_pdf(long_resume), "r.pdf", service, max_characters=500
    )

    assert any(i.code == "TEXT_TRUNCATED" for i in parsed.issues)
    assert service._provider.received_text_lengths[0] <= 500  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_parse_resume_does_not_persist_anything() -> None:
    """INV-1, at the service layer: parsing must not register or create a table."""
    from app.database import Base

    service = AIService(MockAIProvider())
    await parse_resume(build_pdf(SAMPLE_RESUME_LINES), "r.pdf", service)
    assert list(Base.metadata.tables) == []
