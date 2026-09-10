# Standard — Testing

> **Framework:** pytest · **Rule:** tests are written alongside features, not at the end.
> The dossier makes 100% accuracy on the deterministic eligibility suite a success criterion.

---

## 1. The suite must run offline and free

**No network. No API key. No paid call. Ever.**

- All AI goes through the mock provider (`standards/ai.md` §2).
- A test that requires `ELIGICORE_*` AI credentials is a broken test.
- This is a dossier success criterion: the provider is "swappable via configuration, verified by
  running the test suite against a mock provider."

## 2. Test layers

| Layer | What it covers | Speed |
|---|---|---|
| **Unit** | Service logic in isolation, no server, no DB where avoidable | Fast, the bulk of the suite |
| **Integration** | Endpoint contracts via FastAPI `TestClient`, real DB session against SQLite | Slower, fewer |
| **Regression** | A test per fixed bug, named for the bug | Grows over time |

Most tests should be unit tests against services. If most of the suite needs a running app, the
layer boundaries have leaked (INV-7).

## 3. The deterministic eligibility suite

This is the most important test asset in the project. For **every** hard constraint — CGPA,
graduation year, backlogs, degree level:

| Case | Assertion |
|---|---|
| Comfortably passing | `PASS` |
| **Exactly at the boundary** | correct verdict — off-by-one here is the likeliest defect |
| One step below the boundary | correct verdict |
| One step above the boundary | correct verdict |
| **Value missing** | `UNKNOWN`/`NEEDS_REVIEW` — **never `FAIL`** |
| **Value invalid or unparseable** | `UNKNOWN`/`NEEDS_REVIEW` — **never `FAIL`** |
| Scale mismatch (10 vs 4 vs percentage) | normalized correctly, or `UNKNOWN` |
| Scale absent | `UNKNOWN` |

**And the precedence test, which is the direct test of INV-2:** a candidate who fails a hard
constraint *and* is ambiguous on another requirement must return `NOT_ELIGIBLE`, and the test
must assert **the mock provider was never called**. Asserting only on the output is not
sufficient — it would pass even if AI ran and happened to agree.

## 4. Privacy tests

Because privacy is architectural (ADR-001), it gets tested like any other behaviour:

- Assert no persistence: after a full eligibility or parse request, no candidate row and no
  evaluation row exists — ideally by asserting no such table exists at all (INV-1).
- Assert temp-file cleanup on **both** the success path and the exception path (INV-11).
- Assert log output contains no PII for a request carrying a realistic profile (INV-4).
- Assert the error response for an invalid payload does not echo candidate values back.

## 5. Fixtures

- Candidate fixtures are **obviously synthetic** — no real names, emails, phone numbers or
  institutions. Never commit a real resume.
- Resume fixtures: at least one PDF and one DOCX, plus a malformed file and an oversized file.
- Job fixtures cover each hard constraint, plus ambiguous-field cases for the AI stage.
- Build fixtures as the client would send them — profiles passed in request bodies, never
  inserted into a database (ADR-002).

## 6. What makes a test worth having

- A test that cannot fail is not a test. After writing one, confirm it fails when the code is
  wrong.
- Assert on behaviour and contract, not on internal call sequences — except where the invariant
  *is* about calls, as in §3's precedence test.
- One logical assertion per test; the name says what is being asserted.
- Prefer `pytest.mark.parametrize` for boundary tables over copy-pasted near-identical tests.

## 7. Coverage

No percentage target — chasing a number produces tests that assert nothing. Instead:

- Every hard constraint has its full boundary/missing/invalid table.
- Every endpoint has at least a success case and a validation-failure case.
- Every fixed bug has a regression test.
- Every invariant that can be tested, is tested.

## 8. When a test fails

Understand the failure before changing anything. Fix the code if the code is wrong; fix the test
only if the test encoded a wrong expectation — and say so explicitly in the report.

**Never weaken an eligibility assertion to make a suite green.** If a boundary test fails, the
boundary logic is wrong. That test is protecting a stated success criterion.
