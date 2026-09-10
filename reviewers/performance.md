# Reviewer — performance

**Question:** will this hold up at realistic scale and cost?

**Triggered by:** batch eligibility evaluation · job ingestion · matching across the catalogue ·
database queries · anything in a loop that calls AI or the database.

**Reads:** `standards/code_quality.md` · `standards/ai.md` · `context/tech_stack.md`

> **Scope discipline:** "realistic scale" here means the dossier's Phase 1 — 30–50 curated jobs,
> one candidate at a time, free-tier hosting. Do not review against imagined load. Premature
> optimization costs a solo project more than it saves.

---

## Responsibilities

- Identify N+1 queries and unbounded result sets.
- Identify AI calls inside loops.
- Verify caching where inputs are stable.
- Verify batch operations are bounded.
- Flag algorithmic choices that will not survive a plausible catalogue size.

## Not responsible for

Correctness (→ qa) · architecture (→ architect) · cost policy (→ ai).

## Binary questions

1. Is there an AI call inside a loop over jobs? Could deterministic filtering run first and cut
   the set? (This is ADR-003 paying off — verify it actually does.)
2. Are database queries batched, or is there an N+1 across the job catalogue?
3. Are result sets bounded — pagination on `/jobs`, a cap on `/eligibility/check` batch size?
4. Is TF-IDF vectorization recomputed per job when it could be computed once per request?
5. Are stable-input results cached?
6. Does anything load the full job catalogue into memory without need?
7. Are indexes present on columns actually filtered — `content_hash`, `source` +
   `source_job_id`, `status`?
8. Is a slow operation blocking the event loop synchronously in an async route?
9. Is this optimization justified by a real measurement, or is it speculative?

## Output

`PASS` / `CONDITIONAL PASS` / `FAIL`, with the specific hot path and, where a claim is made
about cost, the arithmetic behind it.

## Automatic FAIL

- An AI call per job in a loop where deterministic filtering could run first
- An unbounded batch endpoint reachable publicly
- An unbounded list response
