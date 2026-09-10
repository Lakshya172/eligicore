# Reviewer — api

**Question:** is the contract correct, consistent, stateless and documented?

**Triggered by:** any new or modified endpoint · schema changes · error-shape changes ·
response-model changes.

**Reads:** `standards/api_design.md` · `ADR-002` · `ADR-010`

---

## Responsibilities

- Verify routing conventions and `/api/v1/` placement (INV-12).
- Verify statelessness with respect to personal data (ADR-002).
- Verify Pydantic schemas on both request and response.
- Verify error handling consistency and correct status codes.
- Verify backward compatibility within v1 (ADR-010).
- Verify the generated OpenAPI document is accurate and usable.

## Not responsible for

Business logic correctness (→ qa) · PII leakage analysis (→ security) · layering (→ architect).

## Binary questions

1. Is the route under `/api/v1/`? (INV-12)
2. Does the router contain only validation, a service call and response shaping — no business
   logic? (INV-7)
3. Are both request and response Pydantic models, with `response_model=` set on the route?
4. Does this introduce a `GET` or `PATCH` on a personal-data resource, or any server-held
   candidate state? (must be **no** — ADR-002)
5. Is the change additive within v1, or does it remove/rename a field, change a type, change a
   field's meaning, make an optional field required, or change an enum's meaning? (breaking →
   needs v2, not an in-place edit)
6. Are status codes correct and consistent with the rest of the API?
7. Does the error response avoid echoing candidate data?
8. For eligibility and matching responses: is the per-requirement breakdown and human-readable
   reason present? (INV-8)
9. Are list responses bounded — paginated, or with a capped batch size?
10. Do route `summary`, `description` and field descriptions make this understandable from
    `/docs` alone?
11. Do examples use obviously synthetic data?
12. Are enums declared as Python enums rather than bare strings?

## Output

`PASS` / `CONDITIONAL PASS` / `FAIL`, with the specific contract issue and whether it is
breaking.

## Automatic FAIL

- An unversioned route
- A personal-data `GET`/`PATCH`, or any server-held candidate state
- A breaking change made in place within v1
- An eligibility response with no requirement breakdown
- An error response echoing candidate data
