"""Deterministic truthfulness validation of generated application content (ADR-025, ADR-007).

Dossier §12.3 is unambiguous: *"Any AI-generated application content is checked claim by claim
against the … candidate profile. A claim about a skill, project, duration, or achievement must be
traceable to actual profile data. Untraceable claims are flagged or removed before the content is
returned."* This module is that check, and it is the authority — not the model that wrote the
text, and not a second model asked to grade the first (ADR-025 D6).

**What it does.** Text in, text out, plus an audit list of what it deleted. It removes whole
sentences or list items and never writes a word of its own: there is no rewriting, no bridging
phrase, no re-casing and no reordering. Content it keeps is byte-for-byte what it was given; only
the joining whitespace between surviving units is defined by this module.

**Remove by default** (D5). A claim that cannot be traced is removed, not flagged for a caller to
ignore. There is no parameter, flag or setting that weakens this, because the failure being
guarded against — a fabricated claim on a real person's application — is not one a caller should
be able to opt into.

**The knowledge boundary** (D12). A claim in a category the provider was never given is
untraceable *by construction*, however well it matches the profile. The generator never saw the
CGPA, the backlog count, the institution, the contact details or the employer names
(ADR-025 D10), so a sentence asserting one is a guess — and a guess that happens to be right is
still a guess.

**Deliberate non-goals.** No stemming beyond case folding, no synonym expansion, no semantic
similarity, no embeddings, no NLP service, no AI. Each of those would let the validator *infer*,
which is precisely the behaviour ADR-007 exists to prevent. Paraphrase passes not because the
validator understands it but because only **claim tokens** are matched, never whole sentences.

**Known limitations**, stated rather than hidden:

* Self-assessments ("I am a strong communicator") assert nothing about the candidate's history,
  match no §12.3 category, and are kept.
* A fabricated technology named outside a skill-context clause and without a technology-shaped
  spelling is not detected as a skill claim.
* Detection errs toward removal: a capitalized common noun inside a skill clause may be treated
  as a skill claim. That is the direction `standards/ai.md` §8 requires.

Pure and framework-free (INV-7): no FastAPI, no database, no network, no filesystem, no clock, no
randomness, no environment read, no cache and no module-level mutable state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType

from app.schemas.application import (
    MAX_REMOVED_CLAIM_TEXT,
    ClaimCategory,
    RemovalReason,
    RemovalScope,
    RemovedClaim,
)
from app.schemas.candidate import CandidateProfile
from app.services.candidate_normalizer import skill_comparison_key

#: Bumped when removal behaviour changes, so a caller can tell which rules produced a package.
VALIDATOR_VERSION = "1"

#: A duration claim may exceed the evidence by at most this, absorbing "about six months" for a
#: five-month internship without licensing a year-long exaggeration (ADR-025 D9 § Validator).
DURATION_TOLERANCE_MONTHS = 1

_NON_ALNUM = re.compile(r"[^0-9a-z]+")
_WHITESPACE_RUN = re.compile(r"[ \t]+")
_PARAGRAPH_SPLIT = re.compile(r"\n[ \t]*\n+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_BULLET = re.compile(r"^[ \t]*(?:[-*•–]|\d+[.)])\s+")
_COLON_LIST = re.compile(r"^(?P<lead>[^:\n]{1,200}:)\s*(?P<items>.+)$", re.DOTALL)
_WORD = re.compile(r"\.?[^\W_][\w+#.\-]*")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")

# -- Knowledge boundary: categories the generator was never given (ADR-025 D10, D12) ------------

_GRADE_CLAIM = re.compile(
    r"(?i)\b(?:cgpa|gpa|grade[ -]point|aggregate marks|percentage marks|class rank)\b"
)
_BACKLOG_CLAIM = re.compile(r"(?i)\bbacklogs?\b")
_INSTITUTION_CLAIM = re.compile(
    r"(?i)\b(?:university|college|institute|polytechnic|alma mater)\b"
)
_CONTACT_CLAIM = re.compile(
    r"(?i)(?:[\w.+-]+@[\w-]+\.[\w.-]+|\+?\d[\d\s-]{7,}\d"
    r"|\bmy (?:e-?mail|phone|mobile|contact|address|number)\b|\breach me at\b)"
)
_LOCATION_CLAIM = re.compile(
    r"(?i)\b(?:based in|located in|living in|currently in|relocat\w+ to|resident of)\b"
)
_PAST_EMPLOYMENT_CUE = re.compile(
    r"(?i)\b(?:worked|working|interned|interning|employed|my (?:internship|job|role|position|"
    r"time|tenure|stint)|previous (?:employer|company))\b"
)
_EMPLOYER_NAMED = re.compile(r"\bat\s+(?:the\s+)?[A-Z][\w&.\-]*")

# -- Duration ----------------------------------------------------------------------------------

#: Read-only: the module holds no mutable state, so nothing a caller does can change a verdict.
_SPELLED = MappingProxyType(
    {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    }
)
_NUM_WORD = r"(?:\d+|" + "|".join(_SPELLED) + r")"
_DURATION_CLAIM = re.compile(
    rf"(?i)\b(?:{_NUM_WORD})[ -]?(?:\+)?\s*(?:year|yr|month|mo)s?\b"
    rf"(?:\s*(?:and|,)?\s*(?:{_NUM_WORD})\s*(?:month|mo)s?\b)?"
)
_OPEN_ENDED_DURATION = re.compile(r"(?i)\b(?:since|from)\s+(?:19|20)\d{2}\b|\bto date\b")
_YEAR_RANGE = re.compile(r"\b((?:19|20)\d{2})\s*[-–—]\s*((?:19|20)\d{2})\b")
_YEARS_PART = re.compile(rf"(?i)\b({_NUM_WORD})\s*(?:year|yr)s?\b")
_MONTHS_PART = re.compile(rf"(?i)\b({_NUM_WORD})\s*(?:month|mo)s?\b")

# -- Quantity ----------------------------------------------------------------------------------

_QUANTITY_CLAIM = re.compile(
    rf"(?i)(?:\b(\d+(?:\.\d+)?)\s*(?:%|percent)"
    rf"|\b(?:team|group|cohort|squad) of ({_NUM_WORD})\b"
    rf"|\b(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:users|customers|people|members|students|developers|"
    rf"engineers|clients|projects|releases|deployments|records|rows|requests|downloads|hours)\b)"
)

# -- Skills ------------------------------------------------------------------------------------

_SKILL_CUE = re.compile(
    r"(?i)\b(?:experience (?:with|in|of)|proficient (?:in|with)|skilled (?:in|with)|"
    r"expertise in|expert in|familiar with|worked with|working with|knowledge of|"
    r"fluent in|competent in|hands[- ]on with|using|built with|comfortable with)\b"
)
#: Capitalized words that begin no technology name; treating them as skills would delete prose.
_NOT_A_SKILL = frozenset(
    {
        "i", "a", "an", "the", "my", "our", "we", "this", "these", "their", "your", "it",
        "and", "or", "but", "dear", "hiring", "team", "manager", "sincerely", "regards",
        "ok", "cv", "pdf", "us", "uk", "ai", "it", "hr", "api", "apis", "rest", "ceo",
        "cto", "faq", "ui", "ux", "qa", "eu", "ceo", "sql",
    }
)
_TECH_SHAPED = re.compile(r"^(?=.*[A-Za-z])(?:[\w.+#-]*[.+#][\w.+#-]*|[\w-]*\d[\w-]*)$")

# -- Projects, roles and credentials -----------------------------------------------------------

_PROJECT_CUE = re.compile(
    r"(?i)\b(?:built|build|developed|created|designed|implemented|launched|shipped|"
    r"architected|authored)\b\s+(?:a|an|the|my|our)?\s*(?P<object>[^.,;:!?]{2,80})"
)
_QUOTED = re.compile(r"[\"“‘']([^\"”’']{2,60})[\"”’']")
_ROLE_NOUN = re.compile(
    r"(?i)\b(?:engineer|developer|intern|analyst|scientist|manager|designer|consultant|"
    r"administrator|architect|lead|associate|trainee|researcher|specialist)s?\b"
)
_ROLE_CLAIM = re.compile(r"(?i)\bas an?\s+(?P<title>[A-Za-z][A-Za-z /\-]{2,60})")
_CREDENTIAL_CUE = re.compile(r"(?i)\b(?:certified|certification|certificate)\b")


def _normalize(text: str) -> str:
    """Casefold and strip everything but letters and digits.

    The same shape of normalization :func:`app.services.resume_parser.check_traceability` uses:
    punctuation, spacing and case differ freely between a résumé line and a generated sentence,
    and none of those differences make a claim less true.
    """
    return _NON_ALNUM.sub("", text.casefold())


def _spelled_to_int(token: str) -> int | None:
    """Return the integer a numeral or an English number word denotes, or ``None``."""
    token = token.strip().casefold()
    if token.isdigit():
        return int(token)
    return _SPELLED.get(token)


def _duration_months(text: str) -> int | None:
    """Return the length in whole months that ``text`` states, or ``None`` if it states none.

    An open-ended span ("since 2023") is deliberately unparseable: converting it would require
    reading the clock, and a validator whose verdicts change with the date is not deterministic.
    """
    if _OPEN_ENDED_DURATION.search(text):
        return None

    span = _YEAR_RANGE.search(text)
    if span:
        return (int(span.group(2)) - int(span.group(1))) * 12

    months = 0
    found = False
    years_match = _YEARS_PART.search(text)
    if years_match:
        value = _spelled_to_int(years_match.group(1))
        if value is not None:
            months += value * 12
            found = True
    months_match = _MONTHS_PART.search(text)
    if months_match:
        value = _spelled_to_int(months_match.group(1))
        if value is not None:
            months += value
            found = True
    return months if found else None


@dataclass(frozen=True)
class _Evidence:
    """Everything the profile actually says, in the forms the detectors compare against.

    Built once per :func:`validate` call and never mutated. ``resume_raw_text`` is part of the
    corpus because it is the richest evidence available — and it is used **here only**, never
    sent to a provider (ADR-025 D11).
    """

    skill_keys: frozenset[str]
    project_names: tuple[str, ...]
    role_titles: tuple[str, ...]
    credential_names: tuple[str, ...]
    duration_months: tuple[int, ...]
    numbers: frozenset[float]
    corpus: str


def _collect_numbers(values: list[str]) -> set[float]:
    numbers: set[float] = set()
    for value in values:
        for token in _NUMBER.findall(value):
            numbers.add(float(token))
    return numbers


def build_evidence(profile: CandidateProfile) -> _Evidence:
    """Project a profile into the evidence the validator traces claims against.

    Two exclusions, both load-bearing, both from the knowledge boundary (D12):

    **Data outside the allow-list is never gathered** — grades, backlog counts, institutions,
    contact details, locations, languages and employer names. Gathering them would turn a lucky
    guess into a pass.

    **``resume_raw_text`` is not evidence.** It may corroborate what the structured profile
    already says, and corroborating something already true changes no verdict — but it can never
    *create* evidence, because the generator was given the allow-listed structured fields and
    nothing else (D10). A project, skill, role, credential, duration or number that appears only
    in the résumé was never in front of the model, so a sentence asserting it is a guess. The
    text stays local either way: it is not read here and it is never sent anywhere (D11).
    """
    texts: list[str] = []
    for entry in profile.experience:
        texts.extend(filter(None, (entry.title, entry.duration, entry.description)))
    for project in profile.projects:
        texts.extend(filter(None, (project.name, project.description)))
    for certification in profile.certifications:
        texts.append(certification.name)
    for education in profile.education:
        texts.extend(filter(None, (education.degree, education.field_of_study)))
        if education.grad_year is not None:
            texts.append(str(education.grad_year))
    texts.extend(profile.skills)

    durations = tuple(
        months
        for months in (_duration_months(e.duration or "") for e in profile.experience)
        if months is not None
    )
    return _Evidence(
        skill_keys=frozenset(filter(None, (skill_comparison_key(s) for s in profile.skills))),
        project_names=tuple(p.name for p in profile.projects),
        role_titles=tuple(e.title for e in profile.experience),
        credential_names=tuple(c.name for c in profile.certifications),
        duration_months=durations,
        numbers=frozenset(_collect_numbers(texts)),
        corpus=_normalize(" ".join(texts)),
    )


Failure = tuple[ClaimCategory, RemovalReason]


def _excluded_data_failure(unit: str) -> Failure | None:
    """Claims about data the generator never received (D12). No lookup: these always go."""
    for pattern in (
        _GRADE_CLAIM,
        _BACKLOG_CLAIM,
        _INSTITUTION_CLAIM,
        _CONTACT_CLAIM,
        _LOCATION_CLAIM,
    ):
        if pattern.search(unit):
            return ClaimCategory.EXCLUDED_DATA, RemovalReason.CLAIM_OUTSIDE_KNOWLEDGE_BOUNDARY
    named_employer = _EMPLOYER_NAMED.search(unit)
    if named_employer and (_PAST_EMPLOYMENT_CUE.search(unit) or _DURATION_CLAIM.search(unit)):
        return ClaimCategory.EXCLUDED_DATA, RemovalReason.CLAIM_OUTSIDE_KNOWLEDGE_BOUNDARY
    return None


def _duration_failure(unit: str, evidence: _Evidence) -> Failure | None:
    """A stated length of time must fit something the profile actually records."""
    for match in _DURATION_CLAIM.finditer(unit):
        claimed = _duration_months(match.group(0))
        if claimed is None:
            continue
        if not evidence.duration_months:
            return ClaimCategory.DURATION, RemovalReason.CLAIM_NOT_TRACEABLE
        if claimed > max(evidence.duration_months) + DURATION_TOLERANCE_MONTHS:
            return ClaimCategory.DURATION, RemovalReason.CLAIM_EXCEEDS_PROFILE_VALUE
    if _OPEN_ENDED_DURATION.search(unit):
        return ClaimCategory.DURATION, RemovalReason.CLAIM_NOT_TRACEABLE
    return None


def _quantity_failure(unit: str, evidence: _Evidence) -> Failure | None:
    """Numbers are matched exactly. A percentage the profile never states is invention."""
    for match in _QUANTITY_CLAIM.finditer(unit):
        raw = next(group for group in match.groups() if group)
        value = _spelled_to_int(raw)
        number = float(value) if value is not None else float(raw)
        if number not in evidence.numbers:
            return ClaimCategory.QUANTITY, RemovalReason.CLAIM_NOT_TRACEABLE
    return None


def _skill_tokens(unit: str) -> list[tuple[int, str]]:
    """Return each word of ``unit`` with its position, trailing sentence punctuation removed.

    A trailing dot belongs to the sentence, not to the word: without stripping it, every word
    that ends a sentence looks as technology-shaped as ``Node.js``. A *leading* dot is kept,
    because it is part of the name in ``.NET`` (ADR-021, C-17).
    """
    tokens: list[tuple[int, str]] = []
    for match in _WORD.finditer(unit):
        token = match.group(0).rstrip(".,-")
        if token and token != ".":
            tokens.append((match.start(), token))
    return tokens


def _covered_by_profile_skill(unit: str, evidence: _Evidence) -> set[str]:
    """Return the surface tokens that belong to a skill the profile genuinely lists.

    Phrases are checked up to three words long, so "Data Structures and Algorithms" is matched as
    the skill it is rather than as four unknown words.
    """
    tokens = [token for _, token in _skill_tokens(unit)]
    covered: set[str] = set()
    for size in (3, 2, 1):
        for index in range(len(tokens) - size + 1):
            window = tokens[index : index + size]
            if skill_comparison_key(" ".join(window)) in evidence.skill_keys:
                covered.update(window)
    return covered


def _is_skill_candidate(token: str) -> bool:
    if token.casefold().strip(".") in _NOT_A_SKILL:
        return False
    if _TECH_SHAPED.match(token):
        return True
    return token[:1].isupper()


def _skill_failure(unit: str, evidence: _Evidence, listed: bool = False) -> Failure | None:
    """Skills are compared by canonical equality, never by substring (ADR-021, ADR-025).

    Substring matching is what makes ``Java`` look like evidence for ``JavaScript``; canonical
    keys keep them two different skills, and keep ``C``, ``C++`` and ``C#`` three.

    A named token counts as a skill claim when it sits in a skill-context clause, when it is
    spelled like a technology (``Node.js``, ``C#``), or when the unit is a **list item** — an
    item in "My tools: …" asserts itself, which is the whole reason it was listed.
    """
    covered = _covered_by_profile_skill(unit, evidence)
    cue = _SKILL_CUE.search(unit)
    clause_start = 0 if listed else (cue.end() if cue else None)
    other_names = evidence.project_names + evidence.credential_names + evidence.role_titles

    for position, token in _skill_tokens(unit):
        if token in covered or not _is_skill_candidate(token):
            continue
        in_clause = clause_start is not None and position >= clause_start
        technology_shaped = bool(_TECH_SHAPED.match(token))
        if not (in_clause or technology_shaped):
            continue
        if skill_comparison_key(token) in evidence.skill_keys:
            continue
        if listed and _traceable_by_containment(unit, other_names, evidence.corpus):
            continue
        return ClaimCategory.SKILL, RemovalReason.CLAIM_NOT_TRACEABLE
    return None


def _traceable_by_containment(
    candidate: str, names: tuple[str, ...], corpus: str = ""
) -> bool:
    """True when a named thing appears in the structured profile.

    ``corpus`` is the normalized text of the **allow-listed structured fields only** (D10): the
    same evidence the generator was given, so a description that mentions a project by name
    counts, and a résumé that mentions one the profile never listed does not.
    """
    normalized = _normalize(candidate)
    if not normalized:
        return False
    if corpus and normalized in corpus:
        return True
    return any(
        normalized in _normalize(name) or _normalize(name) in normalized
        for name in names
        if _normalize(name)
    )


def _project_failure(unit: str, evidence: _Evidence) -> Failure | None:
    """A named project must be one the profile lists. Generic work is not a project claim."""
    for match in _PROJECT_CUE.finditer(unit):
        obj = match.group("object")
        quoted = _QUOTED.search(obj)
        if quoted:
            if not _traceable_by_containment(
                quoted.group(1), evidence.project_names, evidence.corpus
            ):
                return ClaimCategory.PROJECT, RemovalReason.CLAIM_NOT_TRACEABLE
            continue
        covered = _covered_by_profile_skill(obj, evidence)
        named = [
            token
            for _, token in _skill_tokens(obj)
            if token[:1].isupper()
            and token not in covered
            and token.casefold().strip(".") not in _NOT_A_SKILL
        ]
        if named and not _traceable_by_containment(
            " ".join(named), evidence.project_names, evidence.corpus
        ):
            return ClaimCategory.PROJECT, RemovalReason.CLAIM_NOT_TRACEABLE
    return None


def _role_failure(unit: str, evidence: _Evidence) -> Failure | None:
    """A role title must be one the profile records. Only role-shaped phrases are checked."""
    for match in _ROLE_CLAIM.finditer(unit):
        title = match.group("title").strip()
        if not _ROLE_NOUN.search(title):
            continue
        if not _traceable_by_containment(title, evidence.role_titles, evidence.corpus):
            return ClaimCategory.EMPLOYMENT, RemovalReason.CLAIM_NOT_TRACEABLE
    return None


def _credential_failure(unit: str, evidence: _Evidence) -> Failure | None:
    """A certification claim must name a certification the profile holds."""
    if not _CREDENTIAL_CUE.search(unit):
        return None
    normalized_unit = _normalize(unit)
    if any(
        _normalize(name) and _normalize(name) in normalized_unit
        for name in evidence.credential_names
    ):
        return None
    return ClaimCategory.CREDENTIAL, RemovalReason.CLAIM_NOT_TRACEABLE


#: Order matters: the knowledge boundary is checked before any lookup, so a claim the generator
#: could not have known is never rescued by a coincidental match in the profile (D12).
_DETECTORS = (
    _duration_failure,
    _quantity_failure,
    _project_failure,
    _role_failure,
    _credential_failure,
)


def _unit_failure(unit: str, evidence: _Evidence, listed: bool = False) -> Failure | None:
    """Return why this unit must go, or ``None`` if every claim in it is traceable."""
    excluded = _excluded_data_failure(unit)
    if excluded is not None:
        return excluded
    skill = _skill_failure(unit, evidence, listed=listed)
    if skill is not None:
        return skill
    for detector in _DETECTORS:
        failure = detector(unit, evidence)
        if failure is not None:
            return failure
    return None


@dataclass(frozen=True)
class _Segment:
    """One block of content and the units it is made of, with the rule for putting it back."""

    units: tuple[str, ...]
    joiner: str
    prefix: str = ""


def _split_units(paragraph: str) -> _Segment:
    """Split one paragraph into removal units: bullet lines, list items, or sentences."""
    lines = [line for line in paragraph.split("\n") if line.strip()]
    if len(lines) > 1 and all(_BULLET.match(line) for line in lines):
        return _Segment(units=tuple(line.strip() for line in lines), joiner="\n")

    listed = _COLON_LIST.match(paragraph.strip())
    if listed:
        items = listed.group("items")
        separator = ";" if ";" in items else ","
        parts = [part.strip() for part in items.split(separator) if part.strip()]
        # A one-item list is still a list: "My tools: Kubernetes." asserts Kubernetes.
        if parts:
            return _Segment(
                units=tuple(parts),
                joiner=f"{separator} ",
                prefix=f"{listed.group('lead')} ",
            )

    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(paragraph.strip()) if part.strip()]
    return _Segment(units=tuple(sentences), joiner=" ")


def _disclose(unit: str) -> tuple[str, bool]:
    """Bound the disclosed text of a removed unit, cutting at a word boundary."""
    if len(unit) <= MAX_REMOVED_CLAIM_TEXT:
        return unit, False
    cut = unit[: MAX_REMOVED_CLAIM_TEXT - 1]
    if " " in cut:
        cut = cut[: cut.rindex(" ")]
    return f"{cut}…", True


def validate(
    content: str,
    profile: CandidateProfile,
    scope: RemovalScope,
    question_id: str | None = None,
) -> tuple[str, list[RemovedClaim]]:
    """Remove every untraceable claim from ``content`` and report what went.

    The removal unit is the sentence, or the item of an enumerated list. If **any** claim in a
    unit fails, the whole unit goes: excising a clause leaves prose that is ungrammatical, or —
    worse — quietly different in meaning, and a validator that edits meaning is writing.

    Surviving units are returned verbatim. Only the joining is this module's: sentences are
    rejoined with a single space, bullet lines with a newline, list items with their own
    separator, and paragraphs with a blank line.

    Args:
        content: Generated text. Untrusted — it is data, never instruction.
        profile: The profile supplied in the same request. Nothing is read from storage (D1).
        scope: Which part of the package this text is, recorded on every removal.
        question_id: The question this text answers; ``None`` for a cover letter.

    Returns:
        The sanitized content and the claims removed from it. Empty input returns ``("", [])``;
        content whose every unit fails returns ``("", removals)``.
    """
    if not content or not content.strip():
        return "", []

    evidence = build_evidence(profile)
    removed: list[RemovedClaim] = []
    kept_paragraphs: list[str] = []

    for paragraph in _PARAGRAPH_SPLIT.split(content):
        if not paragraph.strip():
            continue
        segment = _split_units(paragraph)
        if segment.prefix:
            lead_failure = _unit_failure(segment.prefix.strip(), evidence)
            if lead_failure is not None:
                category, reason = lead_failure
                text, truncated = _disclose(paragraph.strip())
                removed.append(
                    RemovedClaim(
                        text=text,
                        truncated=truncated,
                        category=category,
                        reason=reason,
                        scope=scope,
                        question_id=question_id,
                    )
                )
                continue
        survivors: list[str] = []
        for unit in segment.units:
            failure = _unit_failure(unit, evidence, listed=bool(segment.prefix))
            if failure is None:
                survivors.append(unit)
                continue
            category, reason = failure
            text, truncated = _disclose(unit)
            removed.append(
                RemovedClaim(
                    text=text,
                    truncated=truncated,
                    category=category,
                    reason=reason,
                    scope=scope,
                    question_id=question_id,
                )
            )
        if survivors:
            joined = segment.joiner.join(survivors)
            kept_paragraphs.append(_WHITESPACE_RUN.sub(" ", f"{segment.prefix}{joined}").strip())

    return "\n\n".join(kept_paragraphs), removed
