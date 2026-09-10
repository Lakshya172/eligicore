# Reviewer — security

**Question:** does this leak, persist or expose anything it must not?

**Triggered by:** anything touching personal data (always) · file uploads · logging · secrets ·
configuration · database models and migrations · AI providers · deployment · new dependencies.

**Reads:** `standards/security_privacy.md` · `ADR-001` · `ADR-002` · `ADR-008`

> This reviewer is **not optional** on any change touching personal data. Privacy is EligiCore's
> architectural differentiator; a leak is not a bug, it is a product failure.

---

## Responsibilities

- Verify no server-side persistence of personal data (INV-1).
- Verify no PII reaches logs by any route, including indirect ones (INV-4).
- Verify temporary resume files are deleted on success *and* failure paths (INV-11).
- Verify secrets handling and `.gitignore` coverage.
- Verify input and file validation.
- Verify nothing in scope touches ADR-008's prohibited territory (INV-10).
- Review new dependencies for supply-chain surface.

## Not responsible for

Performance (→ performance) · test coverage (→ qa) · API field naming (→ api).

## Binary questions

1. Does this create, or make possible, any server-side store of a candidate profile, resume,
   evaluation or application record? (must be **no**)
2. Does any migration create a table holding personal data? (must be **no**)
3. Can resume contents, profile payloads or PII reach a log — including via a **stack trace**, a
   captured request body, or FastAPI's default 422 echo?
4. Are temporary files deleted in a `finally`, with handles closed first, and is the failure path
   tested?
5. Are all secrets in `.env`, with `.gitignore` covering it, and no secret in source, config, or
   test fixture?
6. Is every request body a validated Pydantic model, with no raw `dict` reaching business logic?
7. Are file uploads validated for actual content type and maximum size **before** being read
   into memory?
8. Are AI provider responses validated before use, and treated as untrusted?
9. Do error responses avoid echoing candidate data back to the caller?
10. Does this touch auto-submit, browser automation, CAPTCHA/OTP handling, or anti-bot
    circumvention? (must be **no** — INV-10)
11. Are new dependencies pinned, maintained, and worth their surface?
12. Are AI-cost-exposed endpoints bounded — rate limited, batch size capped?

## Output

`PASS` / `CONDITIONAL PASS` / `FAIL`, with file:line evidence and the specific leak path
described concretely — "profile reaches the log at `x.py:42` via the exception handler," not
"possible PII risk."

## Automatic FAIL

- A secret in a commit, or a `.env` not covered by `.gitignore`
- Any server-side persistence of personal data
- PII reachable in logs by any path
- Temp-file cleanup missing from the failure path
- Anything in ADR-008's prohibited territory
