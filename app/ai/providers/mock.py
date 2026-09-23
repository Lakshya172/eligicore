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
from app.ai.usage import UsageSink
from app.schemas.application import (
    ApplicationDraft,
    ApplicationEvidence,
    ApplicationQuestion,
    DraftAnswer,
    GenerationLimits,
    JobBrief,
)
from app.schemas.candidate import Confidence, GradeScale
from app.schemas.eligibility import FieldRelatedness, FieldRelatednessAssessment
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

    **Field relatedness is conservative by default.** Unless a test pins an answer, the mock
    returns ``UNCERTAIN`` at LOW confidence — which the eligibility engine reports as
    ``UNKNOWN``. The mock is the runtime default provider, so a mock that said "related"
    would hand real users a fabricated ``LIKELY_ELIGIBLE`` from an unconfigured deployment
    (ADR-019).

    Args:
        fail_with: Raise this error from either method. Lets tests exercise provider failure
            handling without a live provider.
        return_extraction: Return this exact extraction, bypassing pattern matching. Lets a
            test pin the AI's output precisely.
        raise_invalid_response: Raise :class:`AIResponseInvalidError` from either method,
            simulating a reply that failed schema validation.
        return_relatedness: Return this exact field-relatedness assessment instead of the
            conservative default.
        return_draft: Return this exact application draft, bypassing composition. Lets a test
            pin provider output precisely — including output a real provider should never
            produce.
        fabricate: Append this sentence to the cover letter and to every answer. Exists so a
            test can prove the **validator** removes an invented claim; the mock never
            fabricates on its own.
        over_length: Compose items that exceed the requested word limits, to exercise the
            server-side limit enforcement that D9 requires regardless of what a provider does.
        empty: Compose whitespace-only content, to exercise the empty-output path.
    """

    name = "mock"

    def __init__(
        self,
        *,
        fail_with: AIError | None = None,
        return_extraction: ResumeExtraction | None = None,
        raise_invalid_response: bool = False,
        return_relatedness: FieldRelatednessAssessment | None = None,
        return_draft: ApplicationDraft | None = None,
        fabricate: str | None = None,
        over_length: bool = False,
        empty: bool = False,
    ) -> None:
        self._fail_with = fail_with
        self._return_extraction = return_extraction
        self._raise_invalid_response = raise_invalid_response
        self._return_relatedness = return_relatedness
        self._return_draft = return_draft
        self._fabricate = fabricate
        self._over_length = over_length
        self._empty = empty
        self.call_count = 0
        #: Lengths of the texts this provider was asked to process. Lengths only — never
        #: the text, so an assertion about calls can never itself leak resume content.
        self.received_text_lengths: list[int] = []
        #: Literal count of field-relatedness calls. Tests assert on it to prove the AI
        #: stage was, or was not, reached (INV-2).
        self.relatedness_call_count = 0
        #: Number of permitted fields per relatedness call — counts, never the strings.
        self.received_allowed_field_counts: list[int] = []
        #: Literal count of application-generation calls. The orchestration contract is exactly
        #: one call per request, and a test asserts it (ADR-025 § Orchestration).
        self.generation_call_count = 0
        #: Shape of each generation input: **counts and limits only**, never evidence, job text
        #: or question text. A counter that recorded content would leak candidate data into
        #: every test that inspects it (INV-4).
        self.received_generation_shapes: list[dict[str, int]] = []

    @property
    def model(self) -> str:
        return "mock-deterministic-v1"

    async def extract_resume(
        self, resume_text: str, *, usage: UsageSink | None = None
    ) -> ResumeExtraction:
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

    async def assess_field_relatedness(
        self,
        field_of_study: str,
        allowed_fields: list[str],
        *,
        usage: UsageSink | None = None,
    ) -> FieldRelatednessAssessment:
        """Return the pinned assessment, or the conservative ``UNCERTAIN`` default."""
        self.relatedness_call_count += 1
        self.received_allowed_field_counts.append(len(allowed_fields))

        if self._fail_with is not None:
            raise self._fail_with
        if self._raise_invalid_response:
            raise AIResponseInvalidError(
                "Mock provider returned a response that failed schema validation."
            )
        if self._return_relatedness is not None:
            return self._return_relatedness

        return FieldRelatednessAssessment(
            result=FieldRelatedness.UNCERTAIN,
            confidence=Confidence.LOW,
            reason="The mock provider makes no relatedness judgement unless one is configured.",
        )

    async def generate_application_content(
        self,
        evidence: ApplicationEvidence,
        job: JobBrief,
        questions: list[ApplicationQuestion],
        limits: GenerationLimits,
    ) -> ApplicationDraft:
        """Compose a draft from the supplied evidence, and from nothing else.

        **Conservative by construction.** Every claim-bearing sentence is assembled from a value
        that is literally present in ``evidence``: a listed skill, a recorded role title, a named
        project, a stated field of study. The mock has no vocabulary of its own for facts, so in
        normal mode it cannot fabricate one — which is the behaviour the default provider must
        have, because an unconfigured deployment runs on it.

        Deterministic, offline, and free of state: the same inputs give the same draft, no
        network call is made, no key is needed and nothing is written down. Failure and
        fabrication modes are injectable so the service's error paths can be exercised without a
        live provider.
        """
        self.generation_call_count += 1
        self.received_generation_shapes.append(
            {
                "skills": len(evidence.skills),
                "experience": len(evidence.experience),
                "projects": len(evidence.projects),
                "certifications": len(evidence.certifications),
                "education": len(evidence.education),
                "questions": len(questions),
                "job_description_chars": len(job.description),
                "cover_letter_max_words": limits.cover_letter_max_words,
                "answer_max_words": limits.answer_max_words,
            }
        )

        if self._fail_with is not None:
            raise self._fail_with
        if self._raise_invalid_response:
            raise AIResponseInvalidError(
                "Mock provider returned a response that failed schema validation."
            )
        if self._return_draft is not None:
            return self._return_draft
        if self._empty:
            return ApplicationDraft(
                cover_letter="   " if limits.include_cover_letter else None,
                answers=[DraftAnswer(question_id=q.id, text="  ") for q in questions],
            )

        cover_letter = (
            self._compose_cover_letter(evidence, job, limits.cover_letter_max_words)
            if limits.include_cover_letter
            else None
        )
        answers = [
            DraftAnswer(
                question_id=question.id,
                text=self._compose_answer(
                    evidence, question.max_words or limits.answer_max_words
                ),
            )
            for question in questions
        ]
        return ApplicationDraft(cover_letter=cover_letter, answers=answers)

    # -- composition --------------------------------------------------------------------

    def _compose_cover_letter(
        self, evidence: ApplicationEvidence, job: JobBrief, max_words: int
    ) -> str:
        """Assemble paragraphs in priority order, stopping before the word limit is passed.

        Respecting the limit here is not a substitute for the service enforcing it — D9 requires
        both — but a provider that habitually overshoots would make every package partial.

        Unaddressed and unsigned (D8): the salutation names nobody, the sign-off carries no name,
        and no contact detail exists in the evidence to write even by accident.
        """
        paragraphs = ["Dear Hiring Team,"]
        body = [
            self._sentence(
                f"I am writing to apply for the {job.role_title} role at {job.company_name}"
            ),
            *self._skill_sentences(evidence, job),
            *self._history_sentences(evidence),
            "I would welcome the chance to discuss this role with you.",
        ]
        if self._fabricate:
            body.append(self._fabricate)

        budget = max_words - self._words("Dear Hiring Team, Sincerely,")
        kept: list[str] = []
        for sentence in body:
            if self._over_length or self._words(" ".join(kept + [sentence])) <= budget:
                kept.append(sentence)
        paragraphs.append(" ".join(kept))
        paragraphs.append("Sincerely,")
        text = "\n\n".join(paragraphs)
        if self._over_length:
            text = f"{text}\n\n{self._padding(max_words)}"
        return text

    def _compose_answer(self, evidence: ApplicationEvidence, max_words: int) -> str:
        """Answer from evidence only. Shallow on purpose — a clever mock hides real bugs."""
        sentences = [
            *self._skill_sentences(evidence, None),
            *self._history_sentences(evidence),
        ] or ["I would be glad to discuss this further."]
        if self._fabricate:
            sentences.append(self._fabricate)

        kept: list[str] = []
        for sentence in sentences:
            if self._over_length or self._words(" ".join(kept + [sentence])) <= max_words:
                kept.append(sentence)
        text = " ".join(kept) or sentences[0]
        if self._over_length:
            text = f"{text} {self._padding(max_words)}"
        return text

    def _skill_sentences(
        self, evidence: ApplicationEvidence, job: JobBrief | None
    ) -> list[str]:
        """One sentence naming skills the evidence lists, preferring the ones the job asks for."""
        if not evidence.skills:
            return []
        wanted = {skill.casefold() for skill in (job.required_skills if job else [])}
        ordered = [s for s in evidence.skills if s.casefold() in wanted] or list(evidence.skills)
        chosen = ordered[:3]
        return [f"I have experience with {self._join(chosen)}."]

    def _history_sentences(self, evidence: ApplicationEvidence) -> list[str]:
        """Sentences about roles, projects and discipline — each naming a recorded value."""
        sentences: list[str] = []
        titles = [e.title for e in evidence.experience if e.title]
        if titles:
            sentences.append(f"I worked as a {titles[0]}.")
        projects = [p.name for p in evidence.projects if p.name]
        if projects:
            sentences.append(f"I built {projects[0]}.")
        fields = [e.field_of_study for e in evidence.education if e.field_of_study]
        if fields:
            sentences.append(f"My studies are in {fields[0]}.")
        return sentences

    @staticmethod
    def _sentence(text: str) -> str:
        """End a sentence with exactly one full stop, even when a value already carries one."""
        return f"{text.rstrip('.').rstrip()}."

    @staticmethod
    def _join(items: list[str]) -> str:
        """Join with a comma and a final 'and', so the sentence reads as English."""
        if len(items) == 1:
            return items[0]
        return f"{', '.join(items[:-1])} and {items[-1]}"

    @staticmethod
    def _words(text: str) -> int:
        return len(text.split())

    @staticmethod
    def _padding(max_words: int) -> str:
        """Filler that overshoots a limit while asserting nothing the validator could remove."""
        return " ".join(["padding"] * (max_words + 5))

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
