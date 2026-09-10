# Standard — Security and Privacy

> **Binding ADRs:** ADR-001, ADR-002 · **Invariants:** INV-1, INV-4, INV-10, INV-11
> Privacy is an architectural property of EligiCore, not a compliance checkbox bolted on later.

---

## 1. Personal data must not be persisted server-side

**No `candidates` table. No `evaluations` table. No stored resumes. No application records.**

Forbidden without an explicit approved scope change and a new ADR:

- A SQLAlchemy model representing a candidate, profile, evaluation, or application
- A migration creating such a table
- Writing a profile, resume, or generated content to disk beyond temporary processing
- Caching a profile or an evaluation keyed by `candidate_id` in any server-side store

> **The tempting shortcut:** Phase 1 has no frontend, so persisting "just for testing" feels
> harmless. It is the single most likely way this architecture gets broken. Tests supply
> profiles in request bodies exactly as a client would. QG-005 exists to catch this.

`candidate_id` is a client-generated correlation identifier, not a server-side key. Never treat
it as a lookup handle into server storage.

## 2. Logging rules

**Never log:**

- Resume contents, raw or extracted
- Candidate profile payloads, whole or in part
- Any PII — name, email, phone, location, institution
- Generated application content containing personal information
- Sensitive AI context, including prompts populated with profile data

**Log instead:** request ID, operation type, status code, timing, counts, and safe technical
metadata.

**The leaks that actually happen are indirect.** Guard these specifically:

- **Stack traces.** An exception inside the parser will print the resume text via the captured
  frame. Sanitize exception handlers; do not attach request bodies to error records.
- **FastAPI's default 422 response.** Pydantic validation errors echo the offending input back
  to the client and into logs. Review and override this response shape before it ships.
- **Error telemetry.** Any external error-reporting integration must be configured not to
  capture request bodies.
- **AI provider logging.** A provider that logs prompts is logging profile data. Consider it
  when choosing the Phase 1 default (D-1).
- **Debug prints.** No `print()` of a payload survives review, even temporarily.

## 3. Resume file lifecycle

1. File arrives, exists only for processing.
2. Extracted data is returned to the client.
3. **File is deleted after processing — on the success path and the failure path** (INV-11).

Requirements:

- Use `tempfile` with an explicit `finally` block. Not a `try`/`except` that only cleans on
  success.
- Close file handles before unlinking. On Windows an open handle blocks deletion, and
  development is on Windows while production is Linux — this will pass locally and fail
  silently, or vice versa.
- Never write an uploaded file into the project tree or a predictable path.
- Test both branches. A cleanup path with no failure-case test is untested.

## 4. Input validation

- Every request body is a Pydantic model. No raw `dict` parameters reaching business logic.
- **File uploads:** validate declared content type *and* actual content; enforce a maximum size
  before reading into memory; accept only PDF and DOCX. A file named `.pdf` is not a PDF.
- Treat parsed resume text as untrusted — it reaches prompts and, later, generated output.
- Treat AI provider responses as untrusted input (see `standards/ai.md`).
- Job data from adapters is untrusted; a future adapter reads from the open internet.

## 5. Secrets

- Secrets live in `.env`, loaded via `python-dotenv`. Never in source, never in a committed
  config file, never in a test fixture.
- **`.gitignore` must exist and cover `.env` before any `.env` is created.** Tracked as
  Blocker 2 in `context/state.md`.
- `.env.example` carries key *names* with empty or dummy values, and is committed.
- Environment variables use the `ELIGICORE_` prefix.
- A secret that reaches a commit is compromised — rotate it; do not merely remove the line.

## 6. Dependency hygiene

- Pin versions in `requirements.txt`. Unpinned dependencies make builds non-reproducible.
- Review new dependencies before adding: is it maintained, and is it worth the supply-chain
  surface? Prefer the standard library.
- The dossier's stack is settled — adding a dependency outside it needs justification.

## 7. Rate limiting and abuse

Endpoints that trigger AI calls (`/resumes/parse`, `/eligibility/check`, `/recommendations`,
`/applications/prepare`) are the cost-exposed surface. Uncapped, a public deployment is an open
invitation to spend the owner's API budget.

- Apply rate limiting appropriate to a free-tier public deployment before Week 9.
- Cap batch sizes — `/eligibility/check` accepts many jobs; bound how many.
- Note that under ADR-002 there is no authenticated identity to key limits on. Limit by IP and
  by request shape.

## 8. Out of scope, permanently

Per ADR-008 and INV-10 — do not implement, and do not accept a task that requires:

auto-submission of applications · browser automation for submission · CAPTCHA solving or bypass
· OTP bypass · anti-bot circumvention · identity-verification bypass · scraping that violates a
source's Terms of Service.

If a task appears to require one of these, stop and report it rather than finding a way around.
