# Quality Gates — EligiCore

> **A task is not complete because code exists, the server starts, and the happy path works.**
> A gate is passed by **evidence**, not by assertion.

---

## The gates

| Gate | Applies when | Reviewers |
|---|---|---|
| [QG-001](QG-001-feature-completion.md) | Any feature or unit of work is finished | qa + documentation |
| [QG-002](QG-002-eligibility-change.md) | Eligibility logic changes | architect + ai + qa |
| [QG-003](QG-003-ai-change.md) | AI provider, prompts, or generated content changes | ai + security + qa |
| [QG-004](QG-004-api-contract.md) | An endpoint or schema changes | api + qa |
| [QG-005](QG-005-privacy-data.md) | Anything touches personal data | security |
| [QG-006](QG-006-migration.md) | A database model or migration changes | architect + security + qa |
| [QG-007](QG-007-deployment.md) | Deploying | security + release |

---

## Selecting gates by change size

**Proportion matters.** Running seven gates on a typo is how a process gets abandoned.

| Change | Gates |
|---|---|
| Typo, comment, docstring | None |
| Small internal refactor, no contract change | QG-001 |
| New service logic | QG-001 + whichever domain gate applies |
| New endpoint | QG-001 + QG-004 (+ QG-005 if personal data) |
| Eligibility rule change | QG-001 + QG-002 (+ QG-005) |
| New AI call or prompt | QG-001 + QG-003 (+ QG-005) |
| New model or migration | QG-001 + QG-006 |
| Deployment | QG-007 |

**QG-005 is non-negotiable** on anything touching personal data, regardless of change size. It
guards the project's differentiating property, and the differentiator is the thing that erodes
quietly.

---

## Outcomes

| Outcome | Meaning |
|---|---|
| **PASS** | Every item verified with evidence. |
| **PASS WITH WARNINGS** | Non-blocking issues found, recorded in `context/state.md` as technical debt with a note on when they get addressed. |
| **FAIL** | One or more items unmet. The task is not complete. Fix and re-run — do not proceed and do not negotiate the item away. |

**Evidence means a file path, a line number, a test name, or command output.** "Verified" on its
own is not evidence, and neither is a confident summary.
