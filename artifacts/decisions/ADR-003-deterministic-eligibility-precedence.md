# ADR-003 — Deterministic eligibility precedence

**Status:** Accepted · **Date:** 2026-09-10 · **Source:** dossier §12.1, §13.3

*This is the most important behavioural rule in the system.*

## Context

Eligibility mixes two kinds of requirement. Some are exactly comparable — CGPA against a
cutoff, graduation year against a window, backlog count against a limit, degree level against a
requirement. Others are linguistically ambiguous — "Computer Science or a related field" versus
a candidate holding Information Technology.

A language model can address both. It should only address the second.

## Decision

Evaluation runs in two ordered stages, and **deterministic hard constraints have final
authority.**

```
1. Parse and normalize the requirement
2. Evaluate deterministic hard constraints
3. If a VERIFIED hard constraint fails → NOT_ELIGIBLE.
   Evaluation stops. AI is NOT consulted for that requirement.
4. If deterministic rules pass but ambiguity remains → AI reasoning
5. Produce final state with confidence and explanation
```

**AI must never override a verified deterministic hard eligibility failure.** If the candidate
CGPA is 6.8 and the job minimum is 7.0, the answer is `NOT_ELIGIBLE` at HIGH confidence, and no
AI call is made for that requirement.

## "Verified", and the absence-of-evidence rule

A hard constraint counts as **verified** only when the required data is present and valid.
Missing or unparseable data produces `UNKNOWN` or `NEEDS_REVIEW` for that requirement — **never
a failure.** Absence of evidence is not evidence of ineligibility.

This cuts both ways, and both directions are mandatory: a missing CGPA must not become a
rejection, and it must not become a pass either.

## Confidence semantics

Confidence describes **how much the system trusts its own determination.** It is not a measure
of eligibility, and the two are independent.

| Level | Meaning |
|---|---|
| HIGH | Strong evidence, or deterministic evaluation. Sufficient reliable information. |
| MEDIUM | Reasonable evidence, but interpretation or incompleteness introduces real uncertainty. |
| LOW | Insufficient, ambiguous, conflicting or weak evidence. Treat as uncertain; may warrant review. |

A deterministic hard failure is a HIGH-confidence `NOT_ELIGIBLE`. An AI reading of "or related
field" may be a MEDIUM-confidence `ELIGIBLE`. High confidence does not mean good news, and low
confidence does not mean rejection.

## Rationale

Spending an AI call to compare two numbers is wasteful, slow, and less reliable than a
comparison operator. Reserving AI for genuine ambiguity keeps the system fast, cheap and
predictable while still handling the messy real-world cases pure rules cannot.

Beyond cost: a probabilistic override of a hard gate produces the worst failure mode available
to this system — telling a candidate they qualify for something a recruiter will reject them
from, on a rule the system had already evaluated correctly.

## Consequences

Deterministic logic must be exhaustively tested, including boundary, missing and invalid values
— the dossier requires 100% accuracy on this suite. The AI stage must be *structurally* unable
to reach a requirement that already failed deterministically; this is an architectural
constraint, not a prompt instruction.

## Enforcement

INV-2, INV-3 · QG-002 · `reviewers/ai.md`, `reviewers/qa.md` · `standards/eligibility.md`
