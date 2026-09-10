"""Deterministic mock AI provider.

**Mandatory, not a convenience** (ADR-004, ``standards/ai.md`` §2). The dossier makes
"AI provider swappable via configuration, verified by running the test suite against a mock
provider" a success criterion (§17), and the suite must run with no network, no API key and
no paid call.

It is also the default provider (``ELIGICORE_AI_PROVIDER=mock``), so an unconfigured
checkout cannot make a billable request by accident.

**This is not a resume parser.** It performs shallow, deterministic pattern matching so
tests have something stable to assert against. It deliberately does not try to be clever:
a mock that guesses well would hide extraction bugs behind plausible output.

Failure modes are injectable so error paths are testable without a live provider.
"""

from __future__ import annotations

import re

from app.ai.errors import (
    AIError,
    AIProviderUnavailableError,
    AIResponseInvalidError,
)
from app.ai.providers.base import AIProvider
from app.schemas.candidate import Confidence, GradeScale
from app.schemas.resume import (
    ExtractedEducation,
    ResumeExtraction,
)

# Deliberately simple, anchored patterns. Anything more elaborate would make the mock's
# behaviour hard to predict, which defeats its purpose.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:(?<=\s)|^)(\+?\d[\d\s-]{7,}\d)(?:(?=\s)|$)")
_CGPA_WITH_SCALE = re.compile(
    r"(?:cgpa|gpa)\D{0,10}?(\d{1,2}(?:\.\d{1,2})?)\s*(?:/|out of)\s*(\d{1,3})",
    re.IGNORECASE,
)
_CGPA_BARE = re.compile(r"(?:cgpa|gpa)\D{0,10}?(\d{1,2}(?:\.\d{1,2})?)", re.IGNORECASE)
_GRAD_YEAR = re.compile(r"\b(19[5-9]\d|20\d{2})\b")

_KNOWN_SKILLS = (
    "Python", "Java", "JavaScript", "TypeScript", "React", "Node.js", "FastAPI",
    "Django", "Flask", "SQL", "PostgreSQL", "MySQL", "MongoDB", "Docker",
    "Kubernetes", "AWS", "Git", "Linux", "C++", "C#", "Go", "Rust", "HTML", "CSS",
)

_SCALE_BY_MAXIMUM = {
    4: GradeScale.SCALE_4,
    5: GradeScale.SCALE_5,
    10: GradeScale.SCALE_10,
    100: GradeScale.PERCENTAGE,
}


class MockAIProvider(AIProvider):
    """A deterministic provider for tests and for unconfigured local runs.

    Args:
        fail_with: Raise this error instead of extracting. Lets tests exercise provider
            failure handling without a live provider.
        return_extraction: Return this exact extraction, bypassing pattern matching. Lets a
            test pin the AI's output precisely.
        raise_invalid_response: Raise :class:`AIResponseInvalidError`, simulating a reply
            that failed schema validation.
    """

    name = "mock"

    def __init__(
        self,
        *,
        fail_with: AIError | None = None,
        return_extraction: ResumeExtraction | None = None,
        raise_invalid_response: bool = False,
    ) -> None:
        self._fail_with = fail_with
        self._return_extraction = return_extraction
        self._raise_invalid_response = raise_invalid_response
        self.call_count = 0
        #: Lengths of the texts this provider was asked to process. Lengths only — never
        #: the text, so an assertion about calls can never itself leak resume content.
        self.received_text_lengths: list[int] = []

    @property
    def model(self) -> str:
        return "mock-deterministic-v1"

    async def extract_resume(self, resume_text: str) -> ResumeExtraction:
        """Extract a structured profile using deterministic pattern matching."""
        self.call_count += 1
        self.received_text_lengths.append(len(resume_text))

        if self._fail_with is not None:
            raise self._fail_with
        if self._raise_invalid_response:
            raise AIResponseInvalidError(
                "Mock provider returned a response that failed schema validation."
            )
        if not resume_text.strip():
            raise AIProviderUnavailableError("Mock provider received empty text.")
        if self._return_extraction is not None:
            return self._return_extraction

        return self._extract(resume_text)

    # -- internals ----------------------------------------------------------------------

    def _extract(self, text: str) -> ResumeExtraction:
        """Build an extraction from simple patterns."""
        confidence: dict[str, Confidence] = {}

        email_match = _EMAIL.search(text)
        email = email_match.group(0) if email_match else None
        if email:
            # A literal match in the source text is strong evidence.
            confidence["email"] = Confidence.HIGH

        phone_match = _PHONE.search(text)
        phone = phone_match.group(1).strip() if phone_match else None
        if phone:
            confidence["phone"] = Confidence.MEDIUM

        name = self._first_plausible_name(text)
        if name:
            # A name taken from document position is a guess, and is labelled as one.
            confidence["name"] = Confidence.LOW

        skills = [s for s in _KNOWN_SKILLS if self._mentions(text, s)]
        if skills:
            confidence["skills"] = Confidence.MEDIUM

        education = self._extract_education(text, confidence)

        return ResumeExtraction(
            name=name,
            email=email,
            phone=phone,
            education=education,
            skills=skills,
            # backlogs stays None: the mock never invents one, and None means UNKNOWN
            # rather than zero (INV-3).
            field_confidence=confidence,
        )

    def _extract_education(
        self, text: str, confidence: dict[str, Confidence]
    ) -> list[ExtractedEducation]:
        """Extract a single education record, if a grade or year is present."""
        cgpa: float | None = None
        scale = GradeScale.UNKNOWN

        scaled = _CGPA_WITH_SCALE.search(text)
        if scaled:
            cgpa = float(scaled.group(1))
            scale = _SCALE_BY_MAXIMUM.get(int(scaled.group(2)), GradeScale.UNKNOWN)
            confidence["education[0].cgpa"] = Confidence.HIGH
        else:
            bare = _CGPA_BARE.search(text)
            if bare:
                cgpa = float(bare.group(1))
                # A grade with no stated scale stays UNKNOWN. It is never assumed to be
                # out of 10, however common that is (standards/eligibility.md §4).
                scale = GradeScale.UNKNOWN
                confidence["education[0].cgpa"] = Confidence.LOW

        year_match = _GRAD_YEAR.search(text)
        grad_year = int(year_match.group(1)) if year_match else None

        if cgpa is None and grad_year is None:
            return []

        if grad_year is not None:
            confidence["education[0].grad_year"] = Confidence.LOW

        return [
            ExtractedEducation(
                degree=self._find_degree(text),
                grad_year=grad_year,
                cgpa=cgpa,
                scale=scale,
            )
        ]

    @staticmethod
    def _mentions(text: str, skill: str) -> bool:
        """Whole-token match, so 'C' does not match every word containing the letter."""
        return re.search(rf"(?<![\w+#]){re.escape(skill)}(?![\w+#])", text, re.IGNORECASE) is not None

    @staticmethod
    def _find_degree(text: str) -> str | None:
        for degree in ("B.Tech", "B.E.", "BSc", "B.Sc", "MSc", "M.Tech", "MBA", "PhD"):
            if re.search(rf"(?<!\w){re.escape(degree)}(?!\w)", text, re.IGNORECASE):
                return degree
        return None

    @staticmethod
    def _first_plausible_name(text: str) -> str | None:
        """Take the first short line that looks like a name.

        Crude on purpose. Resumes conventionally open with the candidate's name, and the
        resulting guess is reported at LOW confidence rather than presented as fact.
        """
        for raw_line in text.splitlines()[:5]:
            line = raw_line.strip()
            if not (0 < len(line) <= 60):
                continue
            if _EMAIL.search(line) or any(ch.isdigit() for ch in line):
                continue
            words = line.split()
            if 1 < len(words) <= 4 and all(w[:1].isupper() for w in words if w):
                return line
        return None
