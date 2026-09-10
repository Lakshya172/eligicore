# Reviewer — release

**Question:** is this safe to deploy?

**Triggered by:** deployment · version tag · configuration changes affecting production ·
migrations reaching production.

**Reads:** `standards/security_privacy.md` · `ADR-009` · `context/state.md`

> Relevant from Week 9. Before then, this reviewer has nothing to do — do not invoke it.

---

## Responsibilities

- Verify secrets are configured in the environment and absent from the repository.
- Verify migrations apply cleanly against **PostgreSQL**, not just SQLite.
- Verify the deployed configuration matches the intended one.
- Verify the public deployment is not an open cost liability.
- Verify rollback is possible.

## Not responsible for

Feature correctness (→ qa) · code security review (→ security).

## Binary questions

1. Are all secrets supplied via environment variables in the host, with none in the repository
   and `.env` ignored?
2. **Have migrations been applied and verified against PostgreSQL** — not assumed to work
   because SQLite passed? (ADR-009, risk I-2)
3. Are portable column types used, with no SQLite-specific behaviour relied upon?
4. Is the production database holding operational data only, with no personal-data table?
   (INV-1)
5. Is logging configured so PII cannot reach production logs or error telemetry? (INV-4)
6. Are rate limits and batch caps active on AI-cost-exposed endpoints — is the public API a
   bounded spend?
7. Is `/docs` intentionally public or intentionally closed, and is that decision deliberate?
8. Does the full test suite pass against the release commit?
9. Is there a rollback path — a previous deploy to revert to, and a migration downgrade?
10. Does `context/state.md` reflect what is actually deployed?
11. Are debug mode and verbose tracebacks disabled in production?

## Output

`PASS` / `CONDITIONAL PASS` / `FAIL`.

## Automatic FAIL

- A secret present in the repository or in a deployed image
- Migrations unverified against PostgreSQL
- Personal-data tables in the production database
- Uncapped AI-cost exposure on a public endpoint
- Debug mode or verbose tracebacks enabled in production
