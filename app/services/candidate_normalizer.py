"""Candidate profile validation and normalization.

Pure business logic. No FastAPI, no database, no I/O — this module is importable and
testable without a server (INV-7).

Two operations, matching the two stateless endpoints (dossier §11):

* :func:`validate_profile`  — report gaps and inconsistencies without altering the profile
* :func:`normalize_profile` — canonicalize skills, handle grade scales, clean up fields

Neither stores anything. Neither logs anything (INV-4) — the caller decides what to record,
and the caller is required not to record payloads.

**This module contains no eligibility logic.** It does not decide whether a candidate meets
any requirement; it only puts the profile into a shape a later stage can reason about. The
eligibility engine arrives in Week 4.
"""

from __future__ import annotations

import re

from app.schemas.candidate import (
    CandidateProfile,
    EducationEntry,
    GradeScale,
    IssueSeverity,
    NormalizedGrade,
    ValidationIssue,
)

# ---------------------------------------------------------------------------------------
# Skill canonicalization
# ---------------------------------------------------------------------------------------

# Variants that mean the same skill map to one canonical form, so that matching in Week 5
# measures real overlap rather than naming noise: "ReactJS", "React.js" and "React" must
# not read as three different skills (dossier §12.2 step 1).
#
# Keys are lookup-normalized (see _skill_lookup_key): lowercased, with separators removed.
# This map is deliberately a seed, not an ontology. Extend it as real resumes reveal real
# variants; do not attempt to enumerate every technology up front.
_SKILL_ALIASES: dict[str, str] = {
    # JavaScript ecosystem
    "react": "React",
    "reactjs": "React",
    "nodejs": "Node.js",
    "node": "Node.js",
    "nextjs": "Next.js",
    "vuejs": "Vue.js",
    "vue": "Vue.js",
    "angularjs": "Angular",
    "angular": "Angular",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "expressjs": "Express.js",
    "express": "Express.js",
    # Python ecosystem
    "python": "Python",
    "python3": "Python",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "pandas": "pandas",
    "numpy": "NumPy",
    "scikitlearn": "scikit-learn",
    "sklearn": "scikit-learn",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    # Languages
    "c": "C",
    "cpp": "C++",
    "cplusplus": "C++",
    "csharp": "C#",
    "java": "Java",
    "golang": "Go",
    "go": "Go",
    "rust": "Rust",
    "kotlin": "Kotlin",
    "swift": "Swift",
    "php": "PHP",
    "ruby": "Ruby",
    "r": "R",
    # Data
    "sql": "SQL",
    "mysql": "MySQL",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mongodb": "MongoDB",
    "sqlite": "SQLite",
    "redis": "Redis",
    # Infrastructure
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "aws": "AWS",
    "gcp": "Google Cloud",
    "azure": "Azure",
    "git": "Git",
    "linux": "Linux",
    # Web
    "html": "HTML",
    "html5": "HTML",
    "css": "CSS",
    "css3": "CSS",
    "tailwindcss": "Tailwind CSS",
    "restapi": "REST APIs",
    "rest": "REST APIs",
    "graphql": "GraphQL",
    # Practice
    "ml": "Machine Learning",
    "machinelearning": "Machine Learning",
    "dl": "Deep Learning",
    "deeplearning": "Deep Learning",
    "nlp": "NLP",
    "datastructures": "Data Structures",
    "dsa": "Data Structures and Algorithms",
    "oop": "Object-Oriented Programming",
}

_WHITESPACE = re.compile(r"\s+")
_SKILL_LOOKUP_STRIP = re.compile(r"[^a-z0-9+#]")


def _collapse_whitespace(value: str) -> str:
    """Trim and collapse internal whitespace runs to single spaces."""
    return _WHITESPACE.sub(" ", value).strip()


def _skill_lookup_key(skill: str) -> str:
    """Build the alias-map lookup key for a raw skill string.

    Lowercases and removes separators so that ``React.js``, ``react js`` and ``ReactJS``
    all collapse to ``reactjs``. ``+`` and ``#`` survive, because ``C++`` and ``C#`` are
    genuinely different skills from ``C``.
    """
    return _SKILL_LOOKUP_STRIP.sub("", skill.lower())


def normalize_skill(skill: str) -> str:
    """Return the canonical form of a single skill.

    Known variants map through :data:`_SKILL_ALIASES`. Unknown skills keep their original
    casing — inventing a capitalization convention for an unrecognized technology would
    mangle names like ``pandas`` or ``iOS`` more often than it would help.
    """
    cleaned = _collapse_whitespace(skill).strip(" .,;:/|")
    if not cleaned:
        return ""
    return _SKILL_ALIASES.get(_skill_lookup_key(cleaned), cleaned)


def normalize_skills(skills: list[str]) -> list[str]:
    """Canonicalize a skill list, removing duplicates and preserving order.

    Deduplication is case-insensitive and happens *after* canonicalization, so ``React``,
    ``ReactJS`` and ``react.js`` collapse to one entry. First occurrence wins, because the
    order a candidate lists skills in carries a weak signal of emphasis.
    """
    seen: set[str] = set()
    result: list[str] = []
    for raw in skills:
        canonical = normalize_skill(raw)
        if not canonical:
            continue
        key = canonical.casefold()
        if key not in seen:
            seen.add(key)
            result.append(canonical)
    return result


# ---------------------------------------------------------------------------------------
# Grade scale handling
# ---------------------------------------------------------------------------------------


def normalize_grade(entry: EducationEntry, index: int) -> NormalizedGrade:
    """Express one education entry's grade as a scale-independent fraction.

    Returns ``fraction=None`` whenever the grade or its scale is unknown. This is the
    single most important behaviour in this module: an unknown scale must stay unknown
    rather than being silently treated as a 10-point scale
    (``standards/eligibility.md`` §4, memory pitfall P-2).
    """
    fraction: float | None = None
    maximum = entry.scale.maximum
    if entry.cgpa is not None and maximum is not None and maximum > 0:
        # Clamp rather than raise: an out-of-range grade is already reported as an ERROR
        # issue by validate_profile, and normalize must not crash on it.
        fraction = min(entry.cgpa / maximum, 1.0)

    return NormalizedGrade(
        education_index=index,
        cgpa=entry.cgpa,
        scale=entry.scale,
        fraction=fraction,
    )


# ---------------------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------------------


def validate_profile(profile: CandidateProfile) -> list[ValidationIssue]:
    """Report gaps and inconsistencies in a profile.

    Structural problems — wrong types, negative grades, malformed email — are already
    rejected by Pydantic before this runs. What remains are *domain* findings: data that
    is well-formed but missing, or internally inconsistent.

    **No issue message contains a candidate value** (INV-4). Messages describe the problem,
    not the data.

    Returns issues in document order; the caller decides how to present them.
    """
    issues: list[ValidationIssue] = []

    if not profile.name:
        issues.append(
            ValidationIssue(
                field="name",
                code="MISSING_NAME",
                message="No name provided.",
                severity=IssueSeverity.WARNING,
            )
        )

    if not profile.email:
        issues.append(
            ValidationIssue(
                field="email",
                code="MISSING_EMAIL",
                message="No email address provided.",
                severity=IssueSeverity.WARNING,
            )
        )

    if not profile.education:
        issues.append(
            ValidationIssue(
                field="education",
                code="NO_EDUCATION",
                message=(
                    "No education records provided. Eligibility evaluation depends on "
                    "degree, field, graduation year and grade."
                ),
                severity=IssueSeverity.ERROR,
            )
        )

    for index, entry in enumerate(profile.education):
        issues.extend(_validate_education_entry(entry, index))

    if not profile.skills:
        issues.append(
            ValidationIssue(
                field="skills",
                code="NO_SKILLS",
                message="No skills provided. Match scoring will have nothing to compare.",
                severity=IssueSeverity.WARNING,
            )
        )

    if profile.backlogs is None:
        # Not an error, and emphatically not a zero. A job with a backlog limit will
        # evaluate to UNKNOWN for this candidate rather than passing them (INV-3).
        issues.append(
            ValidationIssue(
                field="backlogs",
                code="MISSING_BACKLOGS",
                message=(
                    "Active backlog count not provided. This stays UNKNOWN and is not "
                    "assumed to be zero; requirements with a backlog limit will be "
                    "reported as needing review."
                ),
                severity=IssueSeverity.WARNING,
            )
        )

    return issues


def _validate_education_entry(entry: EducationEntry, index: int) -> list[ValidationIssue]:
    """Validate one education entry. Helper for :func:`validate_profile`."""
    prefix = f"education[{index}]"
    issues: list[ValidationIssue] = []

    if entry.cgpa is not None and entry.scale is GradeScale.UNKNOWN:
        issues.append(
            ValidationIssue(
                field=f"{prefix}.scale",
                code="MISSING_SCALE",
                message=(
                    "A grade was provided without its grading scale. The scale is not "
                    "inferred; this grade cannot be compared until the scale is supplied."
                ),
                severity=IssueSeverity.WARNING,
            )
        )

    maximum = entry.scale.maximum
    if entry.cgpa is not None and maximum is not None and entry.cgpa > maximum:
        issues.append(
            ValidationIssue(
                field=f"{prefix}.cgpa",
                code="GRADE_EXCEEDS_SCALE",
                message=(
                    f"Grade exceeds the maximum of {maximum:g} for the stated scale. "
                    "One of the two is wrong."
                ),
                severity=IssueSeverity.ERROR,
            )
        )

    if entry.grad_year is None:
        issues.append(
            ValidationIssue(
                field=f"{prefix}.grad_year",
                code="MISSING_GRAD_YEAR",
                message=(
                    "No graduation year. Jobs with a graduation-year window cannot be "
                    "evaluated for this qualification."
                ),
                severity=IssueSeverity.WARNING,
            )
        )

    if entry.field_of_study is None:
        issues.append(
            ValidationIssue(
                field=f"{prefix}.field_of_study",
                code="MISSING_FIELD_OF_STUDY",
                message=(
                    "No field of study. Branch and degree-field requirements cannot be "
                    "evaluated for this qualification."
                ),
                severity=IssueSeverity.WARNING,
            )
        )

    return issues


def has_blocking_issues(issues: list[ValidationIssue]) -> bool:
    """True when any issue is ERROR severity. Warnings never block."""
    return any(issue.severity is IssueSeverity.ERROR for issue in issues)


# ---------------------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------------------


def normalize_profile(
    profile: CandidateProfile,
) -> tuple[CandidateProfile, list[NormalizedGrade], list[str]]:
    """Canonicalize a profile for downstream use.

    Returns the normalized profile, the scale-normalized grade view, and a list of
    human-readable change descriptions.

    Semantic meaning is preserved throughout. Normalization cleans representation — it
    never invents, drops or reinterprets information:

    * skills are canonicalized and deduplicated
    * text fields are whitespace-collapsed; emptied strings become ``None``
    * email is lowercased
    * **education is preserved entry-for-entry, including an UNKNOWN scale**

    The ``changes`` list names field paths only — never values (INV-4).
    """
    changes: list[str] = []
    data = profile.model_dump()

    # --- skills -------------------------------------------------------------------------
    normalized_skills = normalize_skills(profile.skills)
    if normalized_skills != profile.skills:
        changes.append(
            f"skills: canonicalized and deduplicated "
            f"({len(profile.skills)} -> {len(normalized_skills)} entries)"
        )
    data["skills"] = normalized_skills

    # --- languages ----------------------------------------------------------------------
    normalized_languages = _clean_string_list(profile.languages)
    if normalized_languages != profile.languages:
        changes.append("languages: whitespace cleaned and deduplicated")
    data["languages"] = normalized_languages

    # --- simple text fields -------------------------------------------------------------
    for field_name in ("name", "phone", "location"):
        original = getattr(profile, field_name)
        cleaned = _clean_optional_text(original)
        if cleaned != original:
            changes.append(f"{field_name}: whitespace normalized")
        data[field_name] = cleaned

    if profile.email:
        lowered = profile.email.strip().lower()
        if lowered != profile.email:
            changes.append("email: lowercased")
        data["email"] = lowered

    # --- preferences --------------------------------------------------------------------
    cleaned_locations = _clean_string_list(profile.preferences.locations)
    if cleaned_locations != profile.preferences.locations:
        changes.append("preferences.locations: whitespace cleaned and deduplicated")
    data["preferences"]["locations"] = cleaned_locations

    # --- education ----------------------------------------------------------------------
    # Grades and scales pass through untouched. Normalization reports a scale-independent
    # view alongside them; it never rewrites the candidate's stated grade.
    for index, entry in enumerate(profile.education):
        for field_name in ("degree", "field_of_study", "institution"):
            original = getattr(entry, field_name)
            cleaned = _clean_optional_text(original)
            if cleaned != original:
                changes.append(f"education[{index}].{field_name}: whitespace normalized")
            data["education"][index][field_name] = cleaned

    normalized_grades = [
        normalize_grade(entry, index) for index, entry in enumerate(profile.education)
    ]

    unknown_scale_count = sum(1 for grade in normalized_grades if grade.fraction is None)
    if unknown_scale_count:
        changes.append(
            f"education: {unknown_scale_count} grade(s) left unnormalized because the "
            f"grade or scale is unknown - not assumed"
        )

    return CandidateProfile.model_validate(data), normalized_grades, changes


def _clean_optional_text(value: str | None) -> str | None:
    """Collapse whitespace; return None for a value that is empty once cleaned."""
    if value is None:
        return None
    cleaned = _collapse_whitespace(value)
    return cleaned or None


def _clean_string_list(values: list[str]) -> list[str]:
    """Clean, drop empties, and deduplicate case-insensitively, preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = _collapse_whitespace(value)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result
