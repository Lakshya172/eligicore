# Standard — API Design (FastAPI)

> **Binding ADRs:** ADR-002, ADR-010 · **Invariants:** INV-7, INV-12

---

## 1. Routing

- Everything under `/api/v1/`. No exceptions, no unversioned convenience routes.
- One router module per resource area, mounted in `main.py`.
- Paths are lowercase plural nouns: `/candidates`, `/jobs`, `/resumes`, `/applications`.
- `/recommendations` is intentionally not nested under a resource — it is an operation over a
  supplied profile, per ADR-002.

## 2. Routers contain no business logic

A router function should read as: validate input → call a service → shape the response.

- No eligibility rules, no scoring, no parsing, no adapter calls in a router.
- Services must be importable and testable **without FastAPI**. If a service imports `Request`,
  `Depends`, or `HTTPException`, the boundary has leaked.
- Database sessions are injected via `Depends`; services receive a session, not a request.

The test: could this service be called from a CLI script with no server running? If not, fix it.

## 3. Schemas

- Every request body and every response is a Pydantic model. No raw `dict` in either direction.
- Request and response models are distinct types, even when they look identical today.
- Use `response_model=` on every route so the contract is enforced and the OpenAPI doc is
  accurate.
- Field names are `snake_case` and stable — a rename is a breaking change (ADR-010).
- Enums are declared as Python enums, never bare strings.

## 4. Statelessness

Per ADR-002, endpoints handling personal data take their input in the request body and return a
computed result. Specifically:

- No `GET` or `PATCH` on a candidate resource. They imply a server-held record.
- No application-status endpoint.
- `/recommendations` is `POST` because the profile travels in the body.
- No server-side session, no cookie holding candidate state.

**Adding a personal-data `GET` route is an architectural change** requiring an ADR — not a
routine endpoint addition.

## 5. Error handling

- Consistent error shape across every endpoint. Decide it once, in Week 1.
- Correct status codes: `400` malformed, `404` unknown job, `413` file too large, `415` wrong
  file type, `422` validation, `502` provider failure, `429` rate limited.
- **Error responses must not echo candidate data.** FastAPI's default 422 includes the offending
  input — override the handler before it ships (INV-4).
- Provider failures are surfaced honestly. Never return a fabricated eligibility result because
  the AI call failed; return `NEEDS_REVIEW` or an error.
- Every error response carries a correlation/request ID for support without needing the payload.

## 6. Responses

- Explanations are part of the contract, not decoration. Eligibility responses always carry the
  per-requirement breakdown and summary (INV-8, ADR-006).
- Bound list responses — paginate `/jobs`, cap batch sizes on `/eligibility/check`.
- Timestamps are ISO 8601 UTC.
- Nullable fields are explicitly `Optional` with a documented meaning. `null` and "absent" must
  not mean different things in different endpoints.

## 7. Documentation

FastAPI's generated OpenAPI document **is** the published contract, so it must be accurate.

- Every route gets a `summary` and a meaningful `description`.
- Every schema field gets a `Field(description=...)` where the name is not self-evident.
- Provide realistic examples — a stranger should understand the API from `/docs` in under ten
  minutes (dossier §17).
- Never put real personal data in an example. Use obvious fixtures.
