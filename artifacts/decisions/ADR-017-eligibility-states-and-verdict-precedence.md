# ADR-017 — Eligibility states and verdict precedence

**Status:** Accepted · **Date:** 2026-09-17 · **Type:** Ruling (resolves **C-9**, **C-13**, **R-2**, **R-4**)
**Source:** dossier §7 step 5, §10.1, §11, §12.1 · **Decided by:** project owner, Week 4 design gate
**Enforces:** INV-2, INV-3, INV-8 · **Refines:** ADR-003, ADR-006

---

## The gaps

- **C-9.** Dossier §7 lists four verdict states (`ELIGIBLE · LIKELY_ELIGIBLE · NEEDS_REVIEW ·
  NOT_ELIGIBLE`); §10.1 lists five, adding `UNKNOWN`. The dossier never distinguishes `UNKNOWN`
  from `NEEDS_REVIEW`, and §12.1 describes an AI reading as a "MEDIUM-confidence ELIGIBLE",
  which leaves no stated use for `LIKELY_ELIGIBLE`.
- **C-13.** §12.1 step 3 says that after a verified hard failure "evaluation stops". It does not
  say whether the whole job stops, or only the AI stage.
- **R-2.** The dossier does not say whether an AI judgement that a field is *not* related may
  produce `NOT_ELIGIBLE`.
- **R-4.** The dossier does not say what a job stating no structured requirement yields.

## Decision

### Requirement outcomes

Each stated structured requirement resolves to exactly one of `PASS`, `FAIL`, `UNKNOWN`.
A requirement the job does not state is omitted from the breakdown — it is not a pass.

### Five final states

| State | Meaning |
|---|---|
| `ELIGIBLE` | Every stated requirement passed deterministically — or the job states none |
| `LIKELY_ELIGIBLE` | Every stated requirement passed, at least one by approved AI reasoning |
| `NEEDS_REVIEW` | Something is unresolved: an unverifiable requirement, or an AI assessment that failed or returned "not related" |
| `UNKNOWN` | Nothing could be verified — every stated requirement is `UNKNOWN` |
| `NOT_ELIGIBLE` | At least one verified deterministic requirement failed |

No other state exists. Adding one requires a new ADR (QG-002 item 15).

### Precedence — exact and ordered

```
1. Zero structured requirements          → ELIGIBLE (summary says so explicitly)
2. Any deterministic FAIL                 → NOT_ELIGIBLE
3. Every requirement UNKNOWN              → UNKNOWN
4. Any UNKNOWN, or any AI-reasoned FAIL   → NEEDS_REVIEW
5. All PASS, at least one AI-reasoned     → LIKELY_ELIGIBLE
6. All PASS, all deterministic            → ELIGIBLE
```

Implemented in `compose_verdict` (`app/services/eligibility_engine.py`).

### Evaluation after a hard failure (C-13)

**Deterministic evaluation continues; AI evaluation stops.**

Every deterministic check always runs, so a candidate who fails learns *every* verified reason,
not only the first. Once any deterministic requirement fails, the job is closed to the AI stage:
`ambiguous_requirements()` returns nothing for it, and ambiguous entries are reported as
`UNKNOWN` with `SKIPPED_AFTER_HARD_FAILURE`. The guard is control flow, not a prompt instruction.

### AI results never produce `NOT_ELIGIBLE` alone (R-2)

Only a **verified deterministic** failure counts toward rule 2. An AI-reasoned `FAIL` is shown
honestly in the breakdown, and routes the verdict to `NEEDS_REVIEW`. A probabilistic judgement
about whether two fields are related is not strong enough evidence to tell a person they may not
apply.

### Zero structured requirements (R-4)

`ELIGIBLE`, with a summary stating that the job lists no structured eligibility requirements.
Whenever a job carries free-text requirement notes, the summary discloses that they were not
evaluated — including when structured requirements also exist.

### Confidence

Per requirement only: deterministic `PASS`/`FAIL` are `HIGH`, `UNKNOWN` is `LOW`. There is no
top-level confidence: a single number beside a verdict reads as "how good is my result", which
is the conflation ADR-003 forbids.

## Rejected alternatives

- **Four states, dropping `UNKNOWN`.** Loses the difference between "partly verified, check the
  rest" and "we could verify nothing", which tell a candidate different things to do.
- **Stop all evaluation at the first failure.** Cheaper by nothing — deterministic checks are
  comparisons — and it hides further disqualifying reasons from the candidate.
- **Let AI "not related" yield `NOT_ELIGIBLE`.** Makes a model's interpretation a hard gate.
- **Zero requirements → `UNKNOWN`.** Misreports a job that genuinely states no gate.

## Consequences

- `NOT_ELIGIBLE` is always backed by at least one `HIGH`-confidence deterministic `FAIL` in the
  breakdown. That is auditable from the response alone.
- PR 4B adds AI-reasoned entries without changing composition: the precedence already handles
  them and is tested with hand-built AI entries today.
- A candidate with sparse data sees `UNKNOWN` or `NEEDS_REVIEW` rather than a rejection.

## Enforcement

`compose_verdict`, `has_verified_hard_failure`, `ambiguous_requirements` ·
`tests/test_eligibility_engine.py` (precedence table, guard tests, mutation-verified) · QG-002
