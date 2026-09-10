# Standard — Eligibility Engine

> **Binding ADRs:** ADR-003, ADR-006 · **Invariants:** INV-2, INV-3, INV-8
> This standard governs EligiCore's core differentiator. Nothing here is stylistic.

---

## 1. Evaluation order is architecture, not convention

```
1. Parse and normalize the requirement
2. Evaluate deterministic hard constraints
3. If a VERIFIED hard constraint fails → NOT_ELIGIBLE. Stop. AI is not consulted.
4. If deterministic rules pass but ambiguity remains → AI reasoning
5. Produce final state with confidence and explanation
```

The AI stage must be **structurally unable** to reach a requirement that already failed
deterministically. Enforce this in control flow, not by instructing the model. A prompt saying
"do not override hard failures" is not an implementation of INV-2.

## 2. Hard constraints (deterministic, no AI, ever)

| Constraint | Comparison |
|---|---|
| Minimum CGPA | candidate CGPA vs `min_cgpa`, **after scale normalization** |
| Graduation year window | `grad_year` within `[min_grad_year, max_grad_year]` inclusive |
| Maximum backlogs | `backlogs` vs `max_backlogs` |
| Degree level | candidate degree level vs required level |

Anything numerically or categorically comparable belongs here. If you are reaching for an AI
call to compare two values, the requirement is in the wrong stage.

## 3. Verified, unknown, and failed — the three-way distinction

This is the most consequential rule in the codebase.

| Situation | Result |
|---|---|
| Data present, valid, comparison passes | `PASS` |
| Data present, valid, comparison fails | `FAIL` → `NOT_ELIGIBLE`, HIGH confidence |
| Data **missing** on either side | `UNKNOWN` or `NEEDS_REVIEW` — **never `FAIL`** |
| Data present but **unparseable or invalid** | `UNKNOWN` or `NEEDS_REVIEW` — **never `FAIL`** |
| Scale missing or unknown on either side of a CGPA comparison | `UNKNOWN` — **never `FAIL`** |

**Absence of evidence is not evidence of ineligibility.**

Required, and non-negotiable:

- **Never default a missing value to something comparable.** A missing CGPA is not `0.0`. A
  missing backlog count is not `0`. A missing graduation year is not the current year.
- The rule cuts both ways: missing data must not become a pass either.
- Every hard constraint needs an explicit missing-data test and an explicit invalid-data test.

## 4. Grading scales

A CGPA is meaningless without its scale. `8.2` on a 10-point scale and `3.6` on a 4-point scale
are not comparable with `>=`, and a job's `min_cgpa` carries an implicit scale too.

- Always carry `scale` alongside `cgpa` in the education entry.
- Normalize both sides to a common basis before comparing.
- If either scale is absent or unrecognized → `UNKNOWN`. Do not guess, and do not assume 10.
- Percentage-based systems and letter grades are conversions, not comparisons; if a conversion
  is not defined, the result is `UNKNOWN`.

## 5. AI reasoning stage — permitted scope

AI may reason **only** about genuinely ambiguous requirements deterministic rules cannot
resolve. The canonical case: *"Computer Science or a related field"* against a candidate holding
Information Technology.

AI may **not**:

- Re-evaluate any requirement that has a deterministic answer
- Override, soften, revisit or contextualize a verified hard failure
- Decide the overall eligibility state — it contributes a per-requirement verdict; the engine
  composes the final state
- Invent requirements the job posting does not state

Every AI-produced verdict is marked `method: "ai_reasoning"` and carries a confidence level.

## 6. Output contract

States: `ELIGIBLE` · `LIKELY_ELIGIBLE` · `NEEDS_REVIEW` · `NOT_ELIGIBLE` · `UNKNOWN`

Every verdict carries a per-requirement breakdown. Each entry:

```json
{
  "requirement": "Minimum CGPA 7.5",
  "candidate_value": "8.2",
  "status": "PASS",
  "confidence": "high",
  "method": "deterministic",
  "note": "optional, required when method is ai_reasoning"
}
```

Plus a human-readable `summary`. A verdict without a breakdown and a reason is a defect
regardless of whether the verdict is correct (INV-8).

## 7. Confidence is not eligibility

Confidence measures how much the system trusts its own determination. The two axes are
independent.

- Deterministic hard failure → HIGH confidence `NOT_ELIGIBLE`
- AI reading of "or related field" → possibly MEDIUM confidence `ELIGIBLE`
- Missing data → LOW confidence, and a state of `UNKNOWN`/`NEEDS_REVIEW`

High confidence does not mean good news. Low confidence does not mean rejection. Never derive
one from the other.

## 8. Testing requirements

The dossier requires **100% accuracy on the maintained deterministic test suite**. That suite
must cover, for every hard constraint:

- **Boundary values** — exactly at the cutoff, one step below, one step above. Off-by-one at the
  boundary is the most likely defect in this engine.
- **Missing values** — asserting `UNKNOWN`/`NEEDS_REVIEW`, never `FAIL`
- **Invalid values** — non-numeric CGPA, impossible year, negative backlogs
- **Scale mismatches** — 10-point vs 4-point vs percentage; and absent scale
- **Precedence** — a candidate failing a hard rule while being ambiguous on another must return
  `NOT_ELIGIBLE`, and the test must assert **no AI call was made**

That last one is the direct test of INV-2. Assert on the mock provider's call count, not just
on the output.
