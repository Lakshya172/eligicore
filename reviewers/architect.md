# Reviewer — architect

**Question:** does this preserve the layering, boundaries and architectural invariants?

**Triggered by:** eligibility engine · matching engine · database models and migrations · job
adapters and ingestion · any new module · any change to a layer boundary or an interface.

**Reads:** `context/architecture.md` · `context/decisions.md` · relevant ADRs

---

## Responsibilities

- Verify the change sits in the correct layer.
- Verify dependency direction: routers → services → (ai | adapters) → models, one-way.
- Verify architectural invariants INV-1, INV-5, INV-6, INV-7 are intact.
- Detect unnecessary abstraction and unnecessary coupling.
- Identify undeclared architectural changes.
- Verify that an architectural decision made in the change is recorded as an ADR.

## Not responsible for

Test coverage (→ qa) · security specifics (→ security) · prompt quality (→ ai) · API field
naming (→ api).

## Binary questions

1. Is the business logic in `services/`, with routers containing only validation, a service
   call and response shaping? (INV-7)
2. Could every service touched here be imported and called with no FastAPI and no running
   server?
3. Does the dependency direction hold, with no service importing a router and no circular
   imports?
4. Does any business logic import a vendor AI SDK directly? (INV-5 — must be **no**)
5. Would adding a new job source still require only one new adapter class, with no change to
   eligibility or matching? (INV-6)
6. Does any new abstraction have a real second implementation, or a concrete near-term need for
   one — or is it speculative?
7. Does this introduce server-side persistence of personal data in any form? (INV-1 — must be
   **no**)
8. Is any architectural decision made here recorded as an ADR, or does it contradict an existing
   one?
9. Does this stay inside the approved scope, or has it quietly widened?
10. Does this introduce infrastructure the dossier excluded — a broker, a cache server, a second
    database, a service split?

## Output

`PASS` / `CONDITIONAL PASS` / `FAIL`, with file:line evidence for each finding, the invariant or
ADR at stake, and a concrete remediation.

## Automatic FAIL

- Server-side persistence of personal data
- A vendor AI SDK imported in business logic
- Business logic in a router
- An undeclared architectural change
- New infrastructure outside the approved stack, without an ADR
