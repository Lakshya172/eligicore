"""Resume parsing: text extraction, AI structuring, and truthfulness checking.

Pure business logic — no FastAPI, no database (INV-7). The only I/O is reading the
temporary file it is handed.

Pipeline:

    bytes -> temp file -> text extraction -> normalization -> AI extraction
          -> traceability check -> CandidateProfile -> confidence

Three things this module is responsible for getting right:

* **The temporary file is always deleted** — success path and failure path alike (INV-11).
* **Nothing is logged that could carry candidate data** (INV-4). Not the text, not the
  extracted fields, not an exception message that might quote them.
* **Nothing is fabricated.** Extraction copies; it does not complete. Claims that cannot be
  traced back to the source text are demoted and reported, never quietly kept
  (dossier §6, ADR-007).
"""

from __future__ import annotations

import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from docx import Document

from app.ai.ai_service import AIService
from app.ai.errors import AIError, AIResponseInvalidError
from app.schemas.candidate import (
    CandidateProfile,
    Confidence,
    EducationEntry,
    ExperienceEntry,
    GradeScale,
    IssueSeverity,
    ValidationIssue,
)
from app.schemas.resume import (
    ResumeExtraction,
    ResumeParseStatus,
    SourceFormat,
)
from app.services.candidate_normalizer import normalize_skills

logger = logging.getLogger("eligicore.resume")

_WHITESPACE_RUN = re.compile(r"[ \t ]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

_EXTENSION_BY_FORMAT = {SourceFormat.PDF: ".pdf", SourceFormat.DOCX: ".docx"}


class ResumeParsingError(Exception):
    """A resume could not be processed.

    Carries a machine-readable ``code`` so the router can map it to a status without
    string-matching. **Never carries file content or candidate data** in its message.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ParsedResume:
    """Outcome of a parse. Returned to the router, which shapes the HTTP response."""

    status: ResumeParseStatus
    profile: CandidateProfile
    field_confidence: dict[str, Confidence]
    issues: list[ValidationIssue]
    characters_extracted: int


# ---------------------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------------------


def detect_format(filename: str | None, content: bytes) -> SourceFormat:
    """Determine the document format from its magic bytes.

    Content decides, not the filename. A file named ``resume.pdf`` is not a PDF just
    because it says so, and trusting the extension is how a parser gets handed something it
    cannot read (``standards/security_privacy.md`` §4).

    Raises:
        ResumeParsingError: The format is not one of the supported types.
    """
    if content.startswith(b"%PDF-"):
        return SourceFormat.PDF
    # DOCX is a ZIP container; "PK\x03\x04" is the local file header.
    if content.startswith(b"PK\x03\x04"):
        return SourceFormat.DOCX

    raise ResumeParsingError(
        code="UNSUPPORTED_FILE_TYPE",
        message="Unsupported file type. Only PDF and DOCX resumes are accepted.",
    )


# ---------------------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------------------


def extract_text(content: bytes, source_format: SourceFormat) -> str:
    """Extract plain text from resume bytes via a temporary file.

    The temporary file is deleted in a ``finally`` block, so it goes away on the failure
    path too (INV-11). ``delete=False`` plus an explicit unlink is required because Windows
    will not delete a file that is still open, and development here is on Windows while
    deployment is Linux (memory note E-3).

    Raises:
        ResumeParsingError: The document is corrupt, empty, or yields too little text.
    """
    suffix = _EXTENSION_BY_FORMAT[source_format]
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    temp_path = Path(handle.name)

    try:
        handle.write(content)
        handle.close()  # close before reading; Windows will not allow both.
        if source_format is SourceFormat.PDF:
            text = _extract_pdf_text(temp_path)
        else:
            text = _extract_docx_text(temp_path)
    finally:
        handle.close()
        _delete_quietly(temp_path)

    normalized = normalize_text(text)
    if not normalized.strip():
        raise ResumeParsingError(
            code="EMPTY_DOCUMENT",
            message="No text could be extracted. The document may be empty or image-only.",
        )
    return normalized


def _extract_pdf_text(path: Path) -> str:
    """Extract text from a PDF."""
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                raise ResumeParsingError(
                    code="EMPTY_DOCUMENT", message="The PDF contains no pages."
                )
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except ResumeParsingError:
        raise
    except Exception as exc:
        # Only the exception type is surfaced. A pdfminer error message can quote document
        # content, which is the resume (INV-4).
        raise ResumeParsingError(
            code="CORRUPT_DOCUMENT",
            message=f"The PDF could not be read ({type(exc).__name__}).",
        ) from exc


def _extract_docx_text(path: Path) -> str:
    """Extract text from a DOCX, including table cells."""
    try:
        document = Document(str(path))
    except Exception as exc:
        raise ResumeParsingError(
            code="CORRUPT_DOCUMENT",
            message=f"The DOCX could not be read ({type(exc).__name__}).",
        ) from exc

    parts = [p.text for p in document.paragraphs]
    # Resumes frequently lay out education and skills in tables; paragraphs alone miss them.
    for table in document.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


def _delete_quietly(path: Path) -> None:
    """Delete a temporary file, logging only the failure category if it will not go.

    A cleanup failure must not mask the original error, so it is swallowed — but it is
    logged, because a temp file surviving is a privacy concern, not a cosmetic one.
    """
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning(
            "temp_file_cleanup_failed error_type=%s", type(exc).__name__
        )


def normalize_text(text: str) -> str:
    """Collapse extraction noise without altering meaning.

    Runs of spaces become one, trailing whitespace goes, and runs of blank lines collapse
    to two. Line structure is preserved because resumes carry meaning in their layout —
    flattening it would lose the boundary between one education entry and the next.
    """
    if not text:
        return ""
    lines = [_WHITESPACE_RUN.sub(" ", line).strip() for line in text.splitlines()]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


# ---------------------------------------------------------------------------------------
# Truthfulness — traceability of extracted claims
# ---------------------------------------------------------------------------------------


def _traceable(value: str, haystack_normalized: str) -> bool:
    """True when ``value`` appears in the source text, ignoring case and punctuation."""
    needle = _NON_ALNUM.sub("", value.lower())
    return bool(needle) and needle in haystack_normalized


def check_traceability(
    extraction: ResumeExtraction, resume_text: str
) -> tuple[list[str], list[ValidationIssue]]:
    """Drop extracted skills that do not appear in the source text.

    The dossier is explicit that the system does not fabricate (§6), and a language model
    will happily add a skill a candidate "probably" has. Plausibility is not evidence: a
    fabricated skill on a real application is a misrepresentation of a real person.

    Scope is deliberate and limited. Skills are checked because they are discrete tokens
    that must appear verbatim, and they are the most likely fabrication target. Free-text
    fields — job descriptions, project summaries — are legitimately paraphrased during
    extraction and cannot be verified by substring matching, so they are **not** checked
    here. That is a known limitation, not an oversight.

    Returns:
        The surviving skills, and an issue for each one removed.
    """
    normalized_source = _NON_ALNUM.sub("", resume_text.lower())
    kept: list[str] = []
    issues: list[ValidationIssue] = []

    for skill in extraction.skills:
        if _traceable(skill, normalized_source):
            kept.append(skill)
        else:
            issues.append(
                ValidationIssue(
                    field="skills",
                    code="UNTRACEABLE_SKILL",
                    message=(
                        "A skill reported by extraction does not appear in the resume "
                        "text and was removed. Nothing is kept that cannot be traced to "
                        "the source."
                    ),
                    severity=IssueSeverity.WARNING,
                )
            )
    return kept, issues


# ---------------------------------------------------------------------------------------
# Extraction -> profile
# ---------------------------------------------------------------------------------------


def build_profile(
    extraction: ResumeExtraction,
    resume_text: str,
    candidate_id: str | None,
) -> tuple[CandidateProfile, dict[str, Confidence], list[ValidationIssue]]:
    """Convert a validated extraction into a canonical profile.

    Fields the extraction did not report stay absent. Nothing is defaulted into existence:
    a missing backlog count remains ``None`` rather than becoming ``0``, which would turn
    "not stated" into a passing value (INV-3).
    """
    issues: list[ValidationIssue] = []
    confidence = dict(extraction.field_confidence)

    skills, traceability_issues = check_traceability(extraction, resume_text)
    issues.extend(traceability_issues)
    if traceability_issues:
        # Extraction added something the source does not support; the whole skills list is
        # now less trustworthy, regardless of what the model claimed.
        confidence["skills"] = Confidence.LOW

    education = [
        EducationEntry(
            degree=entry.degree or "Unspecified",
            level=entry.level,
            field_of_study=entry.field_of_study or None,
            institution=entry.institution or None,
            grad_year=entry.grad_year,
            cgpa=entry.cgpa,
            scale=entry.scale,
        )
        for entry in extraction.education
        if _has_content(entry)
    ]

    experience = [
        ExperienceEntry(
            title=entry.title or "Unspecified",
            company=entry.company or None,
            duration=entry.duration or None,
            description=entry.description or None,
        )
        for entry in extraction.experience
        if entry.title or entry.company
    ]

    profile = CandidateProfile(
        candidate_id=candidate_id,
        name=extraction.name or None,
        email=extraction.email or None,
        phone=extraction.phone or None,
        location=extraction.location or None,
        education=education,
        experience=experience,
        skills=normalize_skills(skills),
        languages=extraction.languages,
        backlogs=extraction.backlogs,
        field_confidence=confidence,
    )

    issues.extend(_confidence_rules(profile, confidence))
    return profile, confidence, issues


def _has_content(entry: object) -> bool:
    """True when an extracted education entry carries anything worth keeping."""
    return any(
        getattr(entry, field, None) is not None
        for field in ("degree", "field_of_study", "institution", "grad_year", "cgpa")
    )


def _confidence_rules(
    profile: CandidateProfile, confidence: dict[str, Confidence]
) -> list[ValidationIssue]:
    """Apply deterministic confidence rules on top of the model's self-reported values.

    A model's confidence in itself is a claim, not a measurement. Where deterministic
    evidence contradicts it, the deterministic rule wins — the same precedence the
    eligibility engine will use in Week 4 (ADR-003).

    Mutates ``confidence`` in place and returns the issues raised.
    """
    issues: list[ValidationIssue] = []

    for index, entry in enumerate(profile.education):
        if entry.cgpa is not None and entry.scale is GradeScale.UNKNOWN:
            # No matter how sure the model claims to be, a grade with no scale cannot be
            # compared to anything (standards/eligibility.md §4).
            confidence[f"education[{index}].cgpa"] = Confidence.LOW
            issues.append(
                ValidationIssue(
                    field=f"education[{index}].scale",
                    code="MISSING_SCALE",
                    message=(
                        "A grade was extracted without its grading scale. The scale is not "
                        "inferred; please confirm it before this grade is used."
                    ),
                    severity=IssueSeverity.WARNING,
                )
            )

    if profile.backlogs is None:
        issues.append(
            ValidationIssue(
                field="backlogs",
                code="MISSING_BACKLOGS",
                message=(
                    "The resume did not state an active backlog count. This stays UNKNOWN "
                    "and is not assumed to be zero."
                ),
                severity=IssueSeverity.INFO,
            )
        )

    if not profile.education:
        issues.append(
            ValidationIssue(
                field="education",
                code="NO_EDUCATION_EXTRACTED",
                message=(
                    "No education record could be extracted. Eligibility evaluation "
                    "depends on it, so please add it manually."
                ),
                severity=IssueSeverity.WARNING,
            )
        )

    return issues


def _determine_status(
    profile: CandidateProfile,
    confidence: dict[str, Confidence],
    issues: list[ValidationIssue],
) -> ResumeParseStatus:
    """Classify the outcome for the client.

    Uncertainty is preserved rather than rounded away: a result that needs a human eye says
    so, instead of being presented as a clean parse.
    """
    if any(issue.severity is IssueSeverity.ERROR for issue in issues):
        return ResumeParseStatus.NEEDS_REVIEW
    if any(issue.code == "UNTRACEABLE_SKILL" for issue in issues):
        return ResumeParseStatus.NEEDS_REVIEW
    if not profile.education or not profile.name or not profile.email:
        return ResumeParseStatus.PARTIAL
    if any(level is Confidence.LOW for level in confidence.values()):
        return ResumeParseStatus.PARTIAL
    return ResumeParseStatus.PARSED


# ---------------------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------------------


async def parse_resume(
    content: bytes,
    filename: str | None,
    ai_service: AIService,
    *,
    candidate_id: str | None = None,
    max_characters: int = 100_000,
    min_characters: int = 50,
) -> tuple[ParsedResume, SourceFormat]:
    """Parse a resume end to end.

    Raises:
        ResumeParsingError: Unsupported type, corrupt document, empty document, or an AI
            failure that leaves nothing usable to return.
    """
    source_format = detect_format(filename, content)
    text = extract_text(content, source_format)

    if len(text) < min_characters:
        raise ResumeParsingError(
            code="INSUFFICIENT_TEXT",
            message=(
                "Too little text could be extracted to parse. The document may be a "
                "scanned image rather than a text document."
            ),
        )

    # Bound what reaches the model. A pathological document should not consume the AI
    # budget for one request (standards/ai.md §7).
    truncated = text[:max_characters]

    try:
        extraction = await ai_service.extract_resume(truncated)
    except AIResponseInvalidError as exc:
        # Malformed AI output is expected occasionally and is not a server fault. It
        # becomes NEEDS_REVIEW, never a silent pass (standards/ai.md §4).
        raise ResumeParsingError(
            code="AI_RESPONSE_INVALID",
            message=(
                "The extraction result could not be validated. Please enter the profile "
                "manually or try again."
            ),
        ) from exc
    except AIError as exc:
        raise ResumeParsingError(
            code="AI_UNAVAILABLE",
            message="Resume extraction is temporarily unavailable. Please try again.",
        ) from exc

    profile, confidence, issues = build_profile(extraction, truncated, candidate_id)

    if len(text) > max_characters:
        issues.append(
            ValidationIssue(
                field="resume_raw_text",
                code="TEXT_TRUNCATED",
                message=(
                    "The document was longer than the processing limit and was truncated "
                    "before extraction. Later sections may not be represented."
                ),
                severity=IssueSeverity.WARNING,
            )
        )

    return (
        ParsedResume(
            status=_determine_status(profile, confidence, issues),
            profile=profile,
            field_confidence=confidence,
            issues=issues,
            characters_extracted=len(text),
        ),
        source_format,
    )
