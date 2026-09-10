# QG-003 — AI Change

**Applies:** AI provider, interface, prompts, AI service, application preparation, truthfulness
validator · **Reviewers:** ai + security + qa

## Entry criteria

QG-001 passed. AI-related code changed.

## Checklist

| # | Requirement | Evidence |
|---|---|---|
| 1 | No vendor AI SDK imported outside `app/ai/providers/` (INV-5) | Import scan |
| 2 | Provider selection is configuration, not a code branch in a service | file:line |
| 3 | The mock provider supports this change | Mock file:line |
| 4 | The full suite passes with **no network and no API key** | pytest output, credentials unset |
| 5 | Every AI response is validated against a Pydantic model before use | file:line |
| 6 | A malformed/truncated/out-of-enum response yields `NEEDS_REVIEW` — not a crash, not a silent pass | Test name |
| 7 | Prompts are files under `app/ai/prompts/`, not inline strings | File paths |
| 8 | Prompts containing profile data are not logged (INV-4) | Logging review |
| 9 | AI usage/cost logging is in one place, logging counts and cost only — never content | file:line |
| 10 | Retries are capped | file:line |
| 11 | This AI call could not have been a deterministic comparison | Justification |
| 12 | AI output is marked `method: "ai_reasoning"` with an explicit confidence level | Test |
| 13 | AI contributes a per-requirement verdict only; the engine composes the final state | Code review |

### Additionally, for generated application content (ADR-007)

| # | Requirement | Evidence |
|---|---|---|
| 14 | Every claim is traced to profile data supplied in the request | file:line |
| 15 | Untraceable claims are flagged or removed **before the content is returned** (INV-9) | Test name |
| 16 | Validation is inside the generation pipeline, not an optional post-step a caller can skip | Code path |
| 17 | Tests cover both directions: a fabricated claim is caught, and a legitimate paraphrase is not rejected | Test names |

## Exit decision

- **PASS** — all applicable items evidenced.
- **FAIL** — any of items 1–6, 14–16 unmet.
- **PASS WITH WARNINGS** — items 9–11 or 17 incomplete; record as debt.
