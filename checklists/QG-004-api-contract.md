# QG-004 — API Contract

**Applies:** a new or modified endpoint, schema, error shape, or response model
**Reviewers:** api + qa

## Entry criteria

QG-001 passed. An endpoint or schema changed.

## Checklist

| # | Requirement | Evidence |
|---|---|---|
| 1 | Route is under `/api/v1/` (INV-12) | Path |
| 2 | Router contains only validation, a service call, and response shaping (INV-7) | file:line |
| 3 | Request and response are both Pydantic models; `response_model=` is set | file:line |
| 4 | No `GET`/`PATCH` on a personal-data resource, and no server-held candidate state (ADR-002) | Route list |
| 5 | Change is additive within v1, or a genuine v2 was created — no in-place breaking change (ADR-010) | Diff of schemas |
| 6 | No enum value removed or redefined | Diff |
| 7 | Status codes correct and consistent with the rest of the API | Code review |
| 8 | Error responses do not echo candidate data — including the 422 handler (INV-4) | Test name |
| 9 | Eligibility/matching responses carry the requirement breakdown and reason (INV-8) | Test |
| 10 | List responses are bounded — paginated or batch-capped | file:line |
| 11 | Route `summary`, `description` and field descriptions are sufficient to use from `/docs` alone | OpenAPI output |
| 12 | Examples use obviously synthetic data | file:line |
| 13 | Integration test covers a success case and a validation-failure case | Test names |
| 14 | The OpenAPI document still generates and is accurate | `/docs` loads |

## Exit decision

- **PASS** — all items evidenced.
- **FAIL** — any of items 1–6, 8, 9 unmet.
- **PASS WITH WARNINGS** — items 11–12 incomplete; record as debt.

## Note on item 5

The API is the product — Phase 2's frontend, a browser extension, and possibly institutional
consumers all depend on it. A breaking change made quietly inside v1 breaks every consumer with
no signal. If the change is breaking, that is a decision for the human, not a detail to absorb.
