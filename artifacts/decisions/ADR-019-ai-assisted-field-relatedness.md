# ADR-019 — AI-assisted field-of-study relatedness

**Status:** Accepted · **Date:** 2026-09-17 · **Type:** Ruling (implements **A-3**, **R-2**; applies **C-14**)
**Source:** dossier §7 step 5, §12.1 · **Decided by:** project owner, Week 4 design gate and PR 4B brief
**Enforces:** INV-2, INV-3, INV-4, INV-5 · **Refines:** ADR-003, ADR-004, ADR-013, ADR-017, ADR-018

---

## Context

Dossier §12.1 reserves AI for requirements "deterministic rules cannot resolve", with the
canonical example *"Computer Science or a related field"* against a candidate holding
Information Technology. PR 4A (ADR-018, ruling A-2) made an exact normalized field match a
deterministic `PASS` and every other present field **ambiguous** — `UNKNOWN`, never `FAIL` —
because code has no field ontology. This ADR defines the only AI stage that may act on that
ambiguity.

## Decision

### 1. Deterministic rules have final authority

The deterministic engine runs first, evaluates every stated requirement, and alone can produce
`NOT_ELIGIBLE`. AI is a second-stage **ambiguity resolver**, never an eligibility authority.

### 2. AI answers exactly one question

*Is this field of study related to one of these permitted fields?* Nothing else. AI never
assesses CGPA, graduation year, backlogs, degree level, skills, experience, location, work
authorization, job status, or any other requirement. There is no generic "evaluate
eligibility" method.

### 3. When AI is consulted — structurally

Only for an `ALLOWED_FIELDS` entry that `ambiguous_requirements()` releases:

| Situation | AI consulted? | Provider built? | Entry |
|---|---|---|---|
| Any verified deterministic FAIL on the job | **No** | No | `UNKNOWN` · `SKIPPED_AFTER_HARD_FAILURE` |
| Exact normalized match | No | No | `PASS` · deterministic |
| Candidate field missing or blank | No | No | `UNKNOWN` · `MISSING_CANDIDATE_VALUE` |
| `allowed_fields` empty (C-14) | No | No | **omitted** — no field restriction |
| Present, non-exact, no hard failure | **Yes** | on first need | see §4 |

This is control flow, not a prompt instruction: `app/services/eligibility_ai.py` takes AI input
only from `ai_inputs()`, which iterates `ambiguous_requirements()` — empty for any job with a
verified hard failure — and additionally refuses a blank field, an empty permitted list, or a
non-field requirement. A request needing no AI never constructs a provider.

### 4. Result semantics — AI cannot create `NOT_ELIGIBLE`

| Assessment | Entry status | `method` | Confidence | `reason_code` |
|---|---|---|---|---|
| `RELATED`, HIGH or MEDIUM | `PASS` | `ai_reasoning` | MEDIUM | `AI_FIELD_RELATED` |
| `NOT_RELATED`, HIGH or MEDIUM | `FAIL` | `ai_reasoning` | MEDIUM | `AI_FIELD_NOT_RELATED` |
| `UNCERTAIN`, or any LOW confidence | `UNKNOWN` | `ai_reasoning` | LOW | `AI_ASSESSMENT_INCONCLUSIVE` |
| Provider error, invalid reply, or provider cannot be built | `UNKNOWN` | `deterministic` | LOW | `AI_ASSESSMENT_UNAVAILABLE` |

Verdicts come from ADR-017's unchanged `compose_verdict`. Only a **deterministic** FAIL counts
toward `NOT_ELIGIBLE`, so an AI `FAIL` yields `NEEDS_REVIEW` (R-2); an AI `PASS` with everything
else passing yields `LIKELY_ELIGIBLE`, never `ELIGIBLE`.

**Confidence is capped at MEDIUM.** A judgement that two disciplines are related is an
interpretation, not a comparison (ADR-003). HIGH is lowered to MEDIUM and no confidence is ever
raised. LOW is not "a weak pass": it is `UNKNOWN`.

### 5. Failure and invalid output fail closed

Provider errors, invalid or unvalidated replies, and a provider that cannot be built (for
example Gemini selected without a key) become `UNKNOWN` with `AI_ASSESSMENT_UNAVAILABLE`. The
request still succeeds; no exception text reaches the response or the logs beyond an error type.

### 6. Missing data is never sent to AI

AI cannot supply facts the profile does not contain. A missing field, a blank field, or an empty
permitted list produces no AI input (§3).

### 7. Privacy — minimum input, nothing persisted, nothing logged

- The provider method is `assess_field_relatedness(field_of_study, allowed_fields)`. Its
  signature is the boundary: no candidate id, name, email, phone, resume text, grade, year,
  degree, backlog count, job id, description or other job field can reach a provider.
- The Gemini request carries the prompt file plus a JSON data block of exactly
  `{candidate_field_of_study, allowed_fields}`. Values are data, not instructions.
- No prompt, response, input, reason or result is logged. `AIService` logs provider, model,
  outcome, the *number* of permitted fields and timing; the eligibility log line adds
  `ai_assessments` and `ai_unavailable` counts.
- **No raw AI output is persisted.** The validated reason is returned to the caller in the
  entry's `note` and nowhere else. No table, cache or file is added.

### 8. De-duplication is request-scoped

Identical questions — normalized field plus the normalized, sorted permitted-field set — are
asked once per request, at most `MAX_CONCURRENT_AI_CALLS` (4) at a time. The memo lives in memory
for one request and is discarded. A failed assessment is not retried within the request.

### 9. The provider abstraction and the mock are mandatory; Gemini is replaceable

- `AIProvider.assess_field_relatedness` is abstract; every provider implements it and must
  return a validated `FieldRelatednessAssessment` (extra fields rejected).
- The mock provider is mandatory and **conservative by default**: `UNCERTAIN` at LOW for any
  input. It is the runtime default, so an unconfigured deployment can never fabricate a pass.
  Tests pin answers, confidences, provider errors and invalid replies.
- Gemini is one concrete implementation (ADR-013), reusing its existing httpx transport,
  retries, status translation and configuration. Replacing it remains a new provider class and
  a configuration change.

### 10. Rules version

`ENGINE_VERSION` moves from `1` to `2`: a verdict computed under version 1 can differ now that
ambiguity may be resolved.

## Rejected alternatives

- **AI evaluates the whole job.** Makes a model an eligibility authority; ruled out by ADR-003.
- **AI "not related" → `NOT_ELIGIBLE`.** A probabilistic interpretation must not tell a person
  they cannot apply (R-2).
- **Treat LOW-confidence answers as weak passes or failures.** Invents certainty the provider
  did not claim.
- **Send the profile for context.** Unnecessary for the question and a privacy regression.
- **Persistent relatedness cache.** Would store a statement about a candidate's field server-side;
  request-scoped memoization captures the cost benefit that matters within a batch.
- **Eager provider construction.** Would make a provider misconfiguration break requests that need
  no AI.

## Consequences

- `LIKELY_ELIGIBLE` becomes reachable; `NOT_ELIGIBLE` remains exclusively deterministic.
- With the default mock, ambiguous fields stay `UNKNOWN`, so behaviour matches PR 4A except for
  the reason code (`AI_ASSESSMENT_INCONCLUSIVE` rather than `FIELD_NOT_EXACT_MATCH`).
- Gemini's relatedness call has not been exercised against the live service (ADR-013 § Unverified).
- QG-002 item 4 is now evidenced by a literal zero-call test.

## Enforcement

`app/services/eligibility_ai.py` · `app/ai/providers/base.py` · `app/ai/ai_service.py` ·
`tests/test_eligibility_ai_stage.py` · `tests/test_ai_field_relatedness.py` · mutation suite
(27 mutations) · QG-002, QG-003, QG-005
