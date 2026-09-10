# ADR-006 — Explainable eligibility and matching

**Status:** Accepted · **Date:** 2026-09-10 · **Source:** dossier §12.2, §13.4, §17

## Context

EligiCore's value proposition is not "more applications." It is "know why." A candidate told
`NOT_ELIGIBLE` with no reason learns nothing and cannot judge whether the system is right — and
the system will sometimes be wrong.

## Decision

**Every verdict, score and recommendation carries a human-readable reason. An unexplained
answer is treated as a failure, not a result.**

Concretely:

- Every eligibility verdict includes a **per-requirement breakdown**, each entry carrying
  `requirement`, `candidate_value`, `status`, `confidence`, `method`, and an optional `note`.
- `method` is `deterministic` or `ai_reasoning`. This is not cosmetic — it is how a reader knows
  which evaluation stage produced a verdict, and it makes ADR-003 auditable from the output.
- Ineligible jobs are excluded from ranking but **remain retrievable with their rejection
  reason**. A silent disappearance is not an explanation.
- Borderline cases are surfaced as a distinct flagged group rather than forced into a binary.

## Why TF-IDF rather than embeddings for matching

TF-IDF plus cosine similarity requires no training data, costs nothing, runs locally, and is
**explainable** — the system can state which specific terms drove a score.

This is the deciding factor. For a tool whose entire value proposition is transparency, an
unexplainable score is self-defeating. A marginally better but opaque score is worse than a
slightly weaker score that can be justified.

Embeddings remain a viable upgrade path, but only if explainability is preserved.

## Consequences

**Positive.** Candidates can evaluate the system's judgment rather than trusting it blindly.
Wrong verdicts are visibly wrong, which makes them fixable. Explanation output doubles as
debugging output.

**Negative / accepted costs.** Response payloads are substantially larger. Breakdowns must be
maintained alongside logic — a rule change that does not update its explanation is a defect.
Explanation text must not leak PII into logs (INV-4).

## Enforcement

INV-8 · QG-002 · `reviewers/qa.md`, `reviewers/architect.md` · `standards/eligibility.md`
