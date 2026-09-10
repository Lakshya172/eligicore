# ADR-007 — Truthfulness validation

**Status:** Accepted · **Date:** 2026-09-10 · **Source:** dossier §12.3, §6, §13.6

## Context

Application preparation (Week 7) generates cover letters and application answers with a language
model. Language models confidently invent plausible experience — a project that sounds right, a
duration that fits, a skill the role wants.

In a job-application context this is not a minor quality bug. It produces content that
**misrepresents a real person to a real employer**, under that person's name, with consequences
that land on them and not on the system.

## Decision

**Any AI-generated application content is checked claim by claim against the candidate's actual
profile data.** A claim about a skill, project, duration or achievement must be traceable to
real profile data. Untraceable claims are flagged or removed **before the content is returned**.

Validation is a **required component of the generation pipeline, not an optional safeguard** and
not a post-hoc review step the caller can skip.

## Consequences

**Positive.** Generated content is defensible. The candidate is not exposed to a fabrication
they did not write and might not notice. "Truth over fluency" becomes enforceable rather than
aspirational.

**Negative / accepted costs.** Generated content will be blander than an unconstrained model
would produce — accepted deliberately. Claim extraction and tracing is genuinely hard: it must
handle paraphrase and reasonable inference without either rubber-stamping everything or
rejecting every legitimate rewording. Validation adds latency and possibly a second model call.

## Design constraint

Under ADR-001 and ADR-002 the profile is not stored server-side. Validation therefore runs
against the profile **supplied in the same request** as the generation call.

> Note: dossier §12.3 says content is checked against the "stored candidate profile." That
> wording predates the local-first revision and is tracked as contradiction C-3 in
> `context/state.md`. It reads as stale phrasing rather than a design conflict, but it has not
> been resolved unilaterally.

## Enforcement

INV-9 · QG-003 · `reviewers/ai.md`, `reviewers/qa.md` · `standards/ai.md`
