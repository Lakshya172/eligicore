# QG-001 — Feature Completion

**Applies:** any feature or unit of work is finished · **Reviewers:** qa + documentation

## Entry criteria

The approved scope is implemented, and the code runs.

## Checklist

| # | Requirement | Evidence |
|---|---|---|
| 1 | The approved scope is fully implemented — nothing quietly dropped | Diff vs the approved plan |
| 2 | Nothing beyond the approved scope was implemented | Diff vs the approved plan |
| 3 | Tests exist for the new logic | Test file paths and names |
| 4 | Tests cover failure paths, not only the happy path | Named failure-case tests |
| 5 | The tests would fail if the code were wrong | Confirmed by breaking it, or by construction |
| 6 | The full suite passes | pytest output |
| 7 | The suite runs with no network and no API key | pytest output with credentials unset |
| 8 | Type hints on every new function signature | File:line |
| 9 | Docstrings on new public modules, classes and functions | File:line |
| 10 | Business logic is in `services/`, not routers (INV-7) | File paths |
| 11 | No debug prints, no commented-out code, no stray TODOs left silently | Diff |
| 12 | `context/state.md` updated to reflect **actual** state | Diff of `state.md` |
| 13 | Anything learned that would otherwise be rediscovered is in `context/memory.md` | Diff, or an explicit "nothing new" |
| 14 | Any architectural decision made is recorded as an ADR | ADR path, or "none made" |

## Exit decision

- **PASS** — all items evidenced.
- **PASS WITH WARNINGS** — items 11 or 13 incomplete; record as debt in `state.md`.
- **FAIL** — any of items 1–10, 12, or 14 unmet.

## Note on item 12

`state.md` is how the next session knows what is real. Marking something complete that is
partial does not merely mislead a reader — it causes the next step to be built on a false
premise. Item 12 fails on overstatement, not just on omission.
