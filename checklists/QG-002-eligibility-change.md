# QG-002 — Eligibility Change

**Applies:** any change to eligibility logic, rules, states, or confidence handling
**Reviewers:** architect + ai + qa

> This gate guards EligiCore's core. The dossier makes 100% accuracy on the deterministic suite
> a success criterion. Nothing here is negotiable to ship faster.

## Entry criteria

QG-001 passed. Eligibility logic changed.

## Checklist

| # | Requirement | Evidence |
|---|---|---|
| 1 | Deterministic constraints evaluate **before** any AI call | Code path, file:line |
| 2 | A verified hard failure stops evaluation — AI is not consulted for that requirement (INV-2) | Control flow, file:line |
| 3 | INV-2 is enforced in **control flow**, not by a prompt instruction | file:line |
| 4 | A test asserts `NOT_ELIGIBLE` on a hard failure **and** that the mock provider was never called | Test name |
| 5 | Boundary tests exist for every hard constraint touched: at, just below, just above | Test names |
| 6 | Missing values yield `UNKNOWN`/`NEEDS_REVIEW`, never `FAIL` (INV-3) | Test names |
| 7 | Invalid/unparseable values yield `UNKNOWN`/`NEEDS_REVIEW`, never `FAIL` | Test names |
| 8 | No missing value is defaulted to a comparable value (no CGPA→0.0, no backlogs→0) | Code review, file:line |
| 9 | Grading scales are normalized before comparison; absent or unknown scale → `UNKNOWN` | file:line + test |
| 10 | Every verdict carries a per-requirement breakdown and human-readable reason (INV-8) | Response shape + test |
| 11 | Each breakdown entry carries a correct `method` (`deterministic` / `ai_reasoning`) | Test |
| 12 | Confidence is independent of eligibility — not derived from the verdict | Code review |
| 13 | A deterministic hard failure reports HIGH confidence | Test |
| 14 | The full deterministic suite passes at 100% | pytest output |
| 15 | Eligibility states used are exactly the five defined; no new state introduced without an ADR | Code review |

## Exit decision

- **PASS** — all items evidenced.
- **FAIL** — any item unmet. There is no "pass with warnings" on this gate.

## Why no warning tier

A partially correct eligibility engine tells real candidates they cannot apply for jobs they
qualify for, or that they can apply for jobs they cannot. Both outcomes land on a person making
decisions about their career. Items here either hold or they do not.
