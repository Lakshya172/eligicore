# ADR-025 — Week 7 application preparation and truthfulness validation

**Status:** Accepted · **Date:** 2026-09-20 · **Type:** Design ruling (Week 7 design gate)
**Source:** dossier §6, §7 (STEP 8), §8.2, §11, §12.3, §13.5, §13.6, §15 (Week 7), §17
**Decided by:** project owner, Week 7 design gate and two revision rounds
**Enforces:** INV-1, INV-2, INV-4, INV-5, INV-7, INV-9, INV-10 · **Refines:** ADR-004, ADR-007,
ADR-011, ADR-019
**Rules on:** C-3, C-35, C-36, C-37, C-39, C-40, A-53..A-70, R-020..R-031

---

## Context

Dossier §15 gives Week 7 one deliverable: *"Reviewable application packages."* §7 STEP 8 defines
the content — *"Tailored cover letter + answers → truthfulness validated"*, *"Output: ready to
REVIEW, never auto-submitted"* — and §11 gives it one endpoint,
`POST /api/v1/applications/prepare`, described as *"Generate reviewable application package from
the supplied profile and job."*

This is the first slice in which the system writes prose **in a real person's name**, and the
first in which **untrusted job text** meets a generation prompt. ADR-007 already requires claim-by-
claim validation inside the generation pipeline rather than after it. What was missing was the
exact contract: what may leave the service, what the validator actually does, and what the
response looks like when generation or validation fails.

Week 6 is closed at Checkpoint 6 (`13eb8325149cab60a039534631265803250b767a`); this ADR is
recorded before any Week 7 implementation exists.

## Decision

**D1 — Supplied profile only (C-3).** Truthfulness validation runs against the profile supplied in
the same request. No stored profile exists. Dossier §12.3's *"stored candidate profile"* predates
the §8.1a local-first revision; ADR-001, ADR-002 and ADR-011 have authority. C-3 is closed as stale
wording, not as a design conflict.

**D2 — One catalogue job id (C-35, A-53).** The request carries exactly one `job_id` (the existing
`JobId` type). A client-supplied job object is rejected by `extra="forbid"`. An unknown id returns
**404** in the standard envelope (`error: "HTTP_ERROR"`, `message: "Job not found."`), matching
`GET /api/v1/jobs/{job_id}`. The batch `not_found_job_ids` pattern (ADR-022) does not apply: a
single-job request has no partial result to return.

**D3 — Client-supplied questions (C-36, A-55).** At most five, supplied by the client, **never
inferred** from the job description, `apply_link` or any other source. No dossier data model
carries employer questions — §10.2's `jobs` table has none and §10.1 has no client store for them.

**D4 — Zero caching (C-37).** No persistent cache, no cross-request cache, no memoization of
generated content, no new caching dependency and no cache configuration key. Generated prose is
**derived personal data**; caching it server-side would be hidden persistence (INV-1, ADR-011). The
existing `@lru_cache` on settings and prompt-file loading is unaffected — it caches configuration
and static files, never candidate data. Caching remains Week 8.

**D5 — Remove-by-default (C-39).** Untraceable claims are removed **before the response is
constructed** and disclosed through a structured audit list. There is no warn-only mode, no
`validate=false`, no header and no configuration key that weakens removal.

**D6 — Deterministic-only validator (A-59).** `app/services/truthfulness_validator.py` is AI-free,
database-free, network-free, framework-free and persistence-free. An AI claim extractor is
**deferred**; if it is ever added it may only *propose* spans and can never promote an untraceable
claim to traceable. Adding it requires its own ADR.

**D7 — No eligibility coupling (A-62).** Preparation invokes no eligibility evaluation and refuses
nothing on verdict grounds. The response carries no verdict and no requirement breakdown. §11
states no precondition; §12.1's ordering governs eligibility evaluation and ADR-003 governs verdict
authority — preparation produces no verdict, so neither is engaged. §13.5 points the other way: the
human decides what to prepare.

**D8 — Unaddressed and unsigned (A-69).** No recipient name, no candidate name, no signature block,
no contact details; a post-generation guard removes email- and phone-shaped tokens. A neutral
salutation is permitted because it asserts nothing. Identity is inserted client-side, because
identity fields never reach the provider (D10) and a model-written name would be fabricated
identity.

**D9 — Bounds (A-56).** Five questions · question text ≤ 500 characters · answer ≤ 250 words ·
cover letter ≤ 400 words · exactly one job. A word is a whitespace-delimited token. Limits are sent
to the provider **and** enforced server-side after generation; an over-length item is invalid output
for that item only and becomes `null`, never truncated and never rewritten.

**D10 — The provider allow-list (A-64).** The provider input is a separate `extra="forbid"`
projection (`ApplicationEvidence`), built by one explicit projection function — never a
`model_dump()` of `CandidateProfile`:

| Allowed candidate field | Why |
|---|---|
| `skills[]` | The core claim vocabulary; tailoring against `required_skills` needs it |
| `experience[].title` | Describes real roles instead of inventing one |
| `experience[].duration` | §12.3 names duration a claim category; unseen durations get invented |
| `experience[].description` | The substance of what the candidate did |
| `projects[].name`, `projects[].description` | §12.3 names project a claim category |
| `certifications[].name` | Credential claims |
| `education[].degree`, `.level`, `.field_of_study`, `.grad_year` | Qualification and discipline; graduation year is the most common screening question |

Job brief: `role_title`, `company_name`, `description` (truncated to 4000 characters),
`required_skills`.

**Structurally absent** from the provider input schema: `candidate_id`, `name`, `email`, `phone`,
`location`, `education[].institution`, `education[].cgpa`, `education[].scale`, `backlogs`,
`preferences.*`, `field_confidence`, `languages[]`, `experience[].company`,
`certifications[].issuer`, `certifications[].year`, `resume_raw_text`. `projects[]` and
`certifications[]` are re-projected field by field, never passed as objects. Job text is passed as
a labelled JSON **data** block, never as instructions (the ADR-019 §7 pattern), because
adapter-sourced description text is untrusted.

**D11 — `resume_raw_text` is not validator evidence, and never leaves the service (A-70).**
It is never sent to any provider, never logged, and never returned. It is also **not part of
the validator's traceability evidence**: it may corroborate what the structured profile already
says, which changes no verdict, but it can never create evidence. It is the most sensitive
payload in the profile, and it is the one field the generator is guaranteed not to have seen,
so a claim only it supports is a claim the model could not have known.

**D12 — Knowledge boundary. Provider-visible structured evidence is the knowledge boundary.**
A claim in a category the model was **not given** is untraceable by construction and is removed
unconditionally, even when it matches the local profile. The model never saw the CGPA, the
backlog count or the employer name, so any such claim is a guess — and a guess that happens to
be correct is still a fabrication.

A claim may pass **only** when its evidence is represented in the provider-visible structured
allow-list of D10. The validator may not use hidden local evidence — `resume_raw_text` above
all — to pass a claim the provider could not have known. Concretely, `resume_raw_text` cannot
create a project, skill, role, duration, credential or quantity claim, and cannot rescue an
excluded-data claim.

**D13 — No persistence (C-40).** No model, table, column, index, constraint or migration. The
Alembic head stays `b3e8d2c61a47`. No file is written. A test asserts the table set is unchanged,
mirroring the existing export privacy tests.

**D14 — Out of scope.** Submission of any kind, browser automation, CAPTCHA/OTP/anti-bot and
identity-verification bypass (ADR-008, INV-10) · résumé tailoring · PDF/DOCX output · question
inference · application-status endpoints (§11 forbids them) · caching and AI cost logging (Week 8)
· rate limiting and deployment (Week 9) · authentication (Phase 4) · frontend (Phase 2) · a second
AI provider · any change to eligibility, matching, recommendation or export behaviour · any change
to `ENGINE_VERSION`.

## Contracts

### Endpoint

`POST /api/v1/applications/prepare` — synchronous, stateless, unauthenticated, **JSON only**. The
binary-response exception stays unique to `/applications/export` (C-23, ADR-023 §8).

**Request** (`extra="forbid"`): `profile`, `job_id`, `questions[]` (≤ 5),
`include_cover_letter = True`, `cover_letter_max_words = 400` (50..400),
`answer_max_words = 250` (20..250). A request with no cover letter and no questions asks for
nothing and is **422** — rather than inventing a "nothing requested" package status.

**`ApplicationQuestion`:** `id` required, 1..64 characters, `^[A-Za-z0-9._:-]{1,64}$`, unique within
the request (duplicate → 422, mirroring `TrackerExportRequest._unique_job_ids`); `text` stripped
then 1..500 characters; control characters rejected at the boundary as in `app/schemas/tracker.py`;
`max_words` optional, 20..250, defaulting to `answer_max_words`.

**Response** (`extra="forbid"`): `candidate_id?`, `job_id`, `company_name`, `role_title`, `status`,
`generation_outcome`, `cover_letter`, `answers[]`, `removed_claims[]`, `review_required = true`,
`notice`, `provider`, `model`, `method = "ai_reasoning"`, `confidence`, `validator_version`,
`generated_at`.

Lists are **always present and may be empty**; only scalars are nullable — the convention already
set by `RecommendationResponse`. Metadata is **flat**, not nested, for the same reason.
`confidence` is capped at `MEDIUM` for generated content (the ADR-019 §4 precedent) and is `LOW`
whenever anything was removed.

`answers[]` holds one `PreparedAnswer` per supplied question, in request order:
`{question_id, answer, outcome, removed_claims[]}`, with `outcome` one of `GENERATED`,
`REMOVED_ENTIRELY`, `UNAVAILABLE`, `INVALID`, `EMPTY`, `REQUIRES_EXCLUDED_DATA`.

**Removal disclosure rule.** Per-answer `removed_claims[]` is local to that answer. Top-level
`removed_claims[]` is the authoritative **aggregate**: every cover-letter removal plus a copy of
every per-answer removal, each tagged `scope` (`COVER_LETTER` / `ANSWER`) and `question_id` (null
for cover-letter entries). Cover-letter removals appear **only** in the aggregate — there is no
third list. Invariant, enforced by test: aggregate length equals cover-letter removals plus the sum
of per-answer removals. A `RemovedClaim` carries `{text (≤ 500 chars), truncated, category, reason,
scope, question_id}` and no character offsets, because the pre-removal draft is never returned.

New enums live in `app/schemas/application.py`: `PackageStatus`, `GenerationOutcome`,
`AnswerOutcome`, `ClaimCategory`, `RemovalReason`, `RemovalScope`. `ReasonCode` — the eligibility
contract — is **not** extended; `Confidence` and `EvaluationMethod` are reused unchanged.

### Failure semantics

`GenerationOutcome` describes what the **provider** did; `PackageStatus` describes what **survived
validation**. No AI failure produces a 5xx (ADR-019 §5).

| Case | HTTP | `PackageStatus` | `GenerationOutcome` |
|---|---|---|---|
| Complete generation, nothing removed | 200 | `COMPLETE` | `GENERATED` |
| Partial removal, content survives | 200 | `PARTIAL` | `GENERATED` |
| Everything removed by validation | 200 | `NOTHING_VERIFIABLE` | `GENERATED` |
| Provider unavailable, including timeout | 200 | `NOTHING_VERIFIABLE` | `AI_GENERATION_UNAVAILABLE` |
| Provider output invalid as a whole | 200 | `NOTHING_VERIFIABLE` | `AI_GENERATION_INVALID` |
| One item invalid, others fine | 200 | `PARTIAL` | `GENERATED` |
| Valid but empty provider output | 200 | `NOTHING_VERIFIABLE` | `AI_GENERATION_EMPTY` |
| Nothing requested | 422 | — | — |
| Unknown `job_id` | 404 | — | — |
| Malformed request | 422 | — | — |
| Unhandled fault | 500 | — | — |

A question answerable only from excluded data yields `answer: null` with
`outcome: REQUIRES_EXCLUDED_DATA` and a `removed_claims` entry reasoned
`ANSWER_REQUIRES_EXCLUDED_DATA`. Timeout needs no new setting: `ai_timeout_seconds = 30.0` and
`ai_max_retries = 2` already exist, and the Gemini provider already translates
`httpx.TimeoutException` into `AIProviderUnavailableError`. Across every path, no candidate value,
prompt fragment, provider message or generated prose appears in a response body or a log line;
logging stays counts-only.

### Validator (Slice 7A)

The removal unit is the **sentence**, or the **list item** inside an enumerated list — nothing
smaller, because clause surgery produces ungrammatical or subtly altered meaning. Claim categories:
`SKILL`, `PROJECT`, `EMPLOYMENT`, `DURATION`, `CREDENTIAL`, `QUANTITY`, `EXCLUDED_DATA`.

Matching is normalized containment over the evidence corpus, which holds the **provider-visible
structured fields only** (`skills`, `experience[].*`, `projects[].*`, `certifications[].*` and
`education[].*` — never `resume_raw_text`, per D11 and D12), with **canonical
equality** for skills — `Java` must not satisfy a `JavaScript` claim — exact equality for numbers,
and `claim ≤ evidence` within ±1 month for durations, where a claim above the evidence is
`CLAIM_EXCEEDS_PROFILE_VALUE` and unparseable evidence is a removal. Skill canonicalization reuses
the Week 5 `normalize_skill` (ADR-021) rather than re-implementing it.

Paraphrase passes because only **claim tokens** are matched, never whole sentences. Stemming beyond
lowercase and simple plural folding, synonym expansion and semantic similarity are deliberately
**not** attempted — each would let the validator *infer*, which is the behaviour ADR-007 exists to
prevent. If any claim in a unit is untraceable the **whole unit** is removed and disclosed;
surviving units are preserved **verbatim**, in order, with paragraph breaks retained. Prose that
asserts nothing is kept, and self-assessments ("I am a strong communicator") are kept as a
**documented limitation**, in the same spirit as `check_traceability`'s stated limitation. When all
units are removed the validator returns `""`, which the service maps to `null` and
`NOTHING_VERIFIABLE`. The validator never generates or rewrites text.

## Slices

**7A — deterministic truthfulness validator.** `app/schemas/application.py` and
`app/services/truthfulness_validator.py`, plus the §17 maintained corpus (≥ 40 cases, both
directions: verbatim, paraphrase, invented project, invented employer, absent skill,
`Java`/`JavaScript` near-miss, inflated and deflated durations, invented quantities, knowledge-
boundary claims, mixed sentences, enumerated lists, connective prose, injection fixture, unicode
and control characters, empty profile, empty content). No endpoint, no AI, no persistence.
Gates QG-001 and QG-005; mutations ≥ 25 at 100%.

**7B — application preparation endpoint.** The provider method, the mandatory conservative mock,
the prompt file, `app/services/application_prep.py`, router wiring in the existing
`applications.py`, and OpenAPI documentation including the no-submit notice. Carries the
prompt-injection fixtures. Gates QG-001, QG-003, QG-004 and QG-005; mutations ≥ 30 at 100%;
provider-boundary marker test (every `CandidateProfile` field populated with a marker, no excluded
marker present in the serialized provider payload); table-set and no-files assertions; a zero-AI-
call test.

**Deferred to Week 8/9:** the Gemini generation implementation, caching and AI cost logging. Week 7
therefore ships **mock-provider generation only**, and the Checkpoint 7 record, README and OpenAPI
must state that plainly rather than implying a polished generator exists. §17's engineering
criterion — *"AI provider swappable via configuration, verified by running the test suite against a
mock provider"* — is satisfied; letter quality is not claimed.

**No intermediate checkpoint.** A single **Checkpoint 7** is recorded after PR 7B merges and is
verified post-merge. QG-006 is N/A throughout, with the migration chain re-verified as a regression
check.

## Rejected alternatives

- **Client-supplied job object** — an untrusted text channel straight into a prompt, duplicating the
  adapter and normalizer contract.
- **Warn-only validation, or a flag that disables removal** — lets an unattended client ship a
  fabrication; `standards/ai.md` §8 forbids surfacing untraceable content as an ignorable warning.
- **Refusing generation for `NOT_ELIGIBLE` jobs** — makes preparation an eligibility authority and
  removes a legitimate human choice (§13.5).
- **Sending `experience[].company`, `languages[]` or `resume_raw_text`** — employer history and
  résumé text re-identify a person at a third-party provider; nothing in Week 7 requires them.
- **Trusting a claim that matches the profile but was never shown to the model** — a correct guess
  is still a guess (D12).
- **Clause-level excision** — produces ungrammatical or subtly altered meaning; the unit goes.
- **Caching generated content** — hidden persistence of derived personal data (ADR-019 precedent).
- **A "nothing requested" package status** — a request that asks for nothing is malformed, and 422
  keeps the status model to three honest values.

## Consequences

**Positive.** Generated content is defensible claim by claim. Identity never reaches a provider —
the boundary is the method signature, not a prompt instruction. Every AI failure degrades to an
honest empty result rather than an error or a fabrication. No migration, no table, no new
dependency and no change to any existing endpoint or engine.

**Negative / accepted.** Mock-only generation makes Week 7's prose plain until a live provider
lands in Week 8/9. Removal-by-default will sometimes delete legitimate paraphrase the deterministic
matcher cannot trace — the direction to err in, per `standards/ai.md` §8. Self-assessments pass
unvalidated, a documented limitation. Letters end unsigned, so the client must insert identity
locally. Claim extraction and tracing remain genuinely hard, exactly as ADR-007 warned.

## Revisit conditions

`experience[].company` and `languages[]` in the allow-list · the deferred AI claim extractor ·
caching and AI cost logging (Week 8) · the live provider generation implementation (Week 8/9) ·
paraphrase tolerance if the corpus shows systematic over-removal.

## Enforcement

`app/schemas/application.py` · `app/services/truthfulness_validator.py` ·
`app/services/application_prep.py` · `app/ai/providers/base.py` · `app/ai/providers/mock.py` ·
Week 7 mutation suites · QG-001, QG-003, QG-004, QG-005 · `standards/ai.md` §8 ·
`reviewers/ai.md`, `reviewers/security.md`, `reviewers/qa.md`
