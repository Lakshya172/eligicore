# Engineering Memory — EligiCore

> Durable implementation knowledge: conventions, recurring pitfalls, discoveries, edge cases,
> integration notes, lessons from previous iterations.
>
> **This is not a notes file.** Every entry must be something a future session would otherwise
> rediscover the hard way. If an entry is not actionable, delete it.
>
> **Format:** each entry states the fact, why it matters, and what to do about it.

---

## Environment

### E-1 · Git initialized 2026-09-10, branch `master`, no remote, no commits yet
**Why it matters:** the dossier lists "clean, incremental commit history" as a success
criterion, so commit hygiene from here counts as portfolio evidence.
**What to do:** no remote is configured — do not invent one, and do not push. As of Phase 0
close, nothing has been committed; confirm with the owner before making the first commit.
`.gitignore` is verified working (`git check-ignore`): `.env` ignored, `.env.example` tracked.

### E-2 · Local Python is 3.12.10, dossier specifies 3.11+
**Why it matters:** satisfied, but pin the target explicitly in `requirements.txt` and any
deployment config so dev and prod do not silently diverge.
**What to do:** state the Python version in deployment config at Week 9, not before.

### E-3 · Development is on Windows; deployment target is Linux (Render/Railway)
**Why it matters:** two things bite here specifically. Temporary-file handling differs (Windows
will not delete a file that is still open — relevant to the resume lifecycle, INV-11), and path
separators leak into code that builds paths by string concatenation.
**What to do:** always use `pathlib` / `os.path.join`. For temp files use `tempfile` with an
explicit `finally` cleanup, and close handles before unlinking. Test the resume cleanup path on
both the success and exception branches.

---

## Conventions

### C-1 · Naming, fixed by the dossier
Formal name **EligiCore** · package and repo `eligicore` · API namespace `/api/v1/...` ·
environment variable prefix `ELIGICORE_` · database name `eligicore`.
**What to do:** do not invent variants. `ELIGICORE_DATABASE_URL`, not `DATABASE_URL`.

### C-2 · Prompts are files, not inline strings
Dossier §8.2 places prompts under `app/ai/prompts/`.
**Why it matters:** inline prompt strings are undiffable, untestable, and get edited by accident
during unrelated refactors.
**What to do:** one prompt per file, loaded by name. Version them alongside the code.

### C-3 · Education is a JSON list, not flat columns
**Why it matters:** candidates hold multiple qualifications and different education systems use
different grading scales. The dossier's "universal by default" principle depends on this.
**What to do:** `{degree, field, institution, grad_year, cgpa, scale}` per entry. Always carry
`scale` — a bare `cgpa: 8.2` is meaningless without knowing whether the scale is 10 or 4.

---

## Pitfalls — things likely to go wrong here

### P-1 · The tempting shortcut is a server-side candidates table
Phase 1 has no frontend, so there is no IndexedDB, so it feels natural to "just persist the
profile so testing is easier." That silently breaks INV-1, ADR-001 and ADR-002 — the project's
main architectural differentiator.

**There is a second, sneakier route to the same mistake:** the dossier's §8.2 folder listing
literally shows `models/candidate.py` and `models/application.py`. Reading it at face value and
"just following the dossier" recreates the forbidden tables. That listing is **stale** and was
ruled on — see **ADR-011**. Do not create those models on the strength of §8.2.

**What to do:** tests build profile fixtures and pass them in request bodies, exactly as a
client would. If a test feels awkward without persistence, the test is wrong, not the
architecture. QG-005 exists to catch this.

**Related, opposite direction:** `app/models/ingestion_state.py` *is* legitimate (ADR-012) —
§8.2 omits it but §10.2 requires it. Operational data only; a `candidate_id` column there would
be a defect.

### P-2 · Grading-scale comparison is not a float comparison
A CGPA of 8.2 on a 10-point scale and 3.6 on a 4-point scale are not comparable by `>=`, and a
job's `min_cgpa` carries an implicit scale too.
**What to do:** normalize scale before comparing. If the scale is absent or unknown on either
side, the requirement is `UNKNOWN`, **not** a failure (INV-3). This is the most likely source of
a silently wrong eligibility verdict.

### P-3 · "Missing data" and "failing data" are different, and conflating them is the worst bug
this system can have
Defaulting a missing CGPA to 0.0 turns an unknown into a rejection and tells a candidate they
are ineligible when they may not be.
**What to do:** never default a missing value to something comparable. Absence routes to
`UNKNOWN`/`NEEDS_REVIEW`. Test this explicitly for every hard constraint.

### P-4 · Boundary values are where eligibility logic breaks
CGPA exactly equal to the cutoff, graduation year exactly at either window edge, backlogs
exactly at the limit.
**What to do:** every hard constraint gets `at`, `just below` and `just above` tests. The
dossier requires 100% accuracy on the deterministic suite including boundaries — this is a
stated success criterion, not a nice-to-have.

### P-5 · Stack traces leak PII
INV-4 forbids logging profile payloads. An unhandled exception inside the parser will happily
print the resume text into logs via the captured frame, and FastAPI's default validation errors
echo the offending input back.
**What to do:** sanitize exception handlers. Do not attach request bodies to error logs. Review
the default 422 response shape before it ships — it may echo candidate values.

### P-6 · AI output is untrusted input
Structured output from a provider can be malformed, truncated, or contain values outside the
allowed enum.
**What to do:** validate every AI response against a Pydantic model before it touches business
logic. An AI response that fails validation is a `NEEDS_REVIEW`, never a silent pass and never a
crash.

### P-7 · Deduplication over raw text will produce duplicates
Two sources will format the same posting differently, so hashing raw description text creates
duplicate jobs.
**What to do:** hash the canonicalized field set per `context/architecture.md` §7. Keep
`source` + `source_job_id` as an exact-match fast path.

---

## Integration notes

### I-1 · The test suite must run with no network and no API key
Dossier §17 requires the provider to be swappable "verified by running the test suite against a
mock provider."
**What to do:** the mock provider is not an afterthought written at Week 8 — it lands in the
same change as the provider interface in Week 2. CI must pass with no `ELIGICORE_*` AI key set.

### I-2 · SQLite and PostgreSQL are not silently interchangeable
The dossier flags this itself (§9): SQLAlchemy minimizes but does not eliminate engine
differences, and JSON columns, enum handling and case-sensitivity all differ.
**What to do:** validate migrations against PostgreSQL before Week 9 deployment. Do not assume
parity because SQLite tests pass. Prefer portable column types.

---

## Implementation discoveries

### D-1 · Pydantic enum validators must run in `mode="before"` to accept explicit `null`
Found in Week 1. `@field_validator("scale")` defaults to *after* mode, which runs only once
enum coercion has already succeeded — so `{"scale": null}` raised a 422 before the validator
could map it to `UNKNOWN`. A test caught it.
**Why it matters:** semantically `"scale": null` and an omitted `scale` say the same thing —
the scale is not known. Rejecting one and accepting the other is an arbitrary distinction that
would surface as a confusing client error.
**What to do:** any validator normalizing `None` into an enum member needs
`@field_validator(..., mode="before")`. This will recur for every UNKNOWN-bearing enum, and
Week 4 introduces several.

### D-2 · FastAPI's default 422 echoes the submitted value, and `ctx` leaks too
`RequestValidationError.errors()` includes an `input` key holding the exact rejected value, and
Pydantic embeds offending values inside `ctx` for several error types.
**Why it matters:** the direct route to a candidate's email or name landing in a caller's log or
error tracker (INV-4). This is the highest-probability PII leak in the application.
**What to do:** the custom handler in `app/main.py` drops **both** `input` and `ctx`, keeping
only `loc`, `type` and `msg`. Do not "simplify" it back to passing `exc.errors()` through.
Three tests guard this with marker strings — top level, unknown field, and nested.

### D-3 · Naive punctuation stripping merges C, C++ and C#
The skill lookup key strips separators so `React.js` and `ReactJS` collapse. Stripping *all*
punctuation would collapse `C++` and `C#` into `C` — three genuinely different skills becoming
one, which would corrupt match scoring in Week 5.
**What to do:** `_SKILL_LOOKUP_STRIP` deliberately preserves `+` and `#`. There is a test.
Adding a language whose name carries punctuation needs the same care.

### D-4 · `alembic check` is a cheap INV-1 guard
It reports "No new upgrade operations detected" only when no model registers a table that the
database lacks. With zero models it proves the operational database is empty.
**What to do:** it runs in CI. Once real models exist (Week 3) it stops being an emptiness proof
and becomes a drift check — still useful, but the personal-data guard then rests on the explicit
`Base.metadata` assertion in CI and on QG-005.

### D-5 · Grade normalization must clamp, not raise
`normalize_profile` runs on profiles that `validate_profile` would flag — 8.2 on a 4-point scale,
for instance. An out-of-range grade is reported as `GRADE_EXCEEDS_SCALE`, but normalization is a
separate endpoint and must not crash on the same input.
**What to do:** `normalize_grade` clamps the fraction to 1.0. The error is surfaced by
validation, not by an exception in normalization.

### D-6 · GitHub over HTTPS on this machine fails intermittently with `SEC_E_UNTRUSTED_ROOT`
A `git push` failed with a schannel untrusted-root error, and `gh api` failed with x509
simultaneously; an immediate retry of both succeeded with no configuration change. Suggests an
intercepting proxy or AV TLS scanner that is occasionally slow to present its chain.
**What to do:** retry once before investigating. **Do not** disable TLS verification
(`http.sslVerify=false`) or add a CA to work around it — that is a real security downgrade in
exchange for a transient failure.

### D-7 · Verify a merge with the REST API, not `gh pr view --json merged`
`gh` 2.97.0 rejects `merged` as a JSON field (`Unknown JSON field: "merged"`), and
`gh pr merge` succeeds silently with no output. `gh pr view --json state` alone is not proof
either — it returns `CLOSED` for both a merged and an abandoned PR.
**Why it matters:** claiming "merged" on the strength of a local `git log` or a silent command
is exactly the kind of unverified success this project's process exists to prevent.
**What to do:** `gh api repos/OWNER/REPO/pulls/N` returns `merged`, `merged_at`, `merged_by` and
`merge_commit_sha`. Confirm `merge_commit_sha` equals `main` HEAD after pulling.

### D-8 · Recording a checkpoint SHA needs its own PR, by construction
`main` is protected and requires a PR, so the merge commit's SHA cannot be written into the
documentation by the same PR that produces it — the SHA does not exist until the merge happens.
**Why it matters:** it is not a process failure, it is inherent. Expect one small follow-up
`docs/checkpoint-N-record` PR after every phase merge.
**What to do:** keep that PR to documentation only. Do not use the admin bypass
(`enforce_admins` is false) to push the record straight to `main` — the bypass existing is not a
reason to use it.

### D-9 · pdfminer logs the entire resume at DEBUG level
Found in Week 2 by a privacy test, not by inspection. pdfminer — which pdfplumber sits on —
logs the contents of every text-showing operator at DEBUG. That is the literal resume text,
line by line.
**Why it matters:** no application log statement is involved. Raising the root log level to
DEBUG, in production or while chasing an unrelated bug, would dump candidate data into the
logs. A direct INV-4 violation reachable with zero code changes.
**What to do:** `app/services/resume_parser.py` pins `pdfminer`, `pdfplumber` and `docx`
loggers at WARNING with `propagate = False`. Do not remove it. **Apply the same treatment to
any future library that touches document or candidate content** — assume a third-party
library logs its input until proven otherwise, and add a test rather than trusting it.

### D-10 · `caplog.at_level("DEBUG")` with no logger argument captures everything
The privacy test that caught D-9 only caught it because it captured *all* loggers rather than
just `eligicore`.
**Why it matters:** a privacy test scoped to your own logger proves only that *you* did not
log the secret. The leak is usually somewhere else.
**What to do:** privacy log tests stay unscoped. Scoping them to `eligicore` would have made
the suite green and shipped the leak.

### D-11 · Windows temp files must be closed before unlinking
`NamedTemporaryFile(delete=True)` cannot be reopened by another library on Windows, and an
open handle blocks deletion.
**What to do:** `delete=False`, write, `close()`, read with the library, then `unlink` in a
`finally`. Tested on both the success and the failure path (INV-11). Development is Windows
and deployment is Linux, so this differs between the two and a success-path-only test would
pass on both while leaking on neither reliably.

### D-12 · Stripping all punctuation merges C, C++ and C# — and the same trap appears in skill traceability
Already recorded as D-3 for skill normalization; Week 2's traceability check normalizes text
the same way and hit it again.
**What to do:** any comparison that strips punctuation from a technology name needs the same
care. Preserve `+` and `#`.

### D-13 · An httpx exception message can echo the request body
`httpx.HTTPError` string representations may include the URL and, for some error types, the
request content. The request content here is a prompt containing resume text.
**What to do:** the Gemini provider never includes `str(exc)` in an error it raises — only
`type(exc).__name__`. Same rule for Pydantic `ValidationError`, whose detail embeds the
offending values; the provider reports `exc.error_count()` instead. Both have tests.

### D-15 · A merged PR reports `state: CLOSED`, and `gh pr merge` can silently no-op
Merging PR #4 returned `! Pull request ... was already merged` — the merge had gone through on a
prior invocation whose output was swallowed.
**Why it matters:** `state` alone cannot distinguish merged from abandoned, and the CLI's
success is not evidence. Acting on either would have produced a false report.
**What to do:** always confirm with `gh api repos/OWNER/REPO/pulls/N` and check `merged`,
`merged_at` and `merge_commit_sha`, then assert `merge_commit_sha` equals `main` HEAD after
pulling. Already recorded as D-7; this is the second time it mattered.

### D-14 · FastAPI file uploads need `python-multipart` and fail at import time without it
Not at request time — the app will not import at all.
**What to do:** it is pinned in `requirements.txt`. Any future endpoint accepting `File` or
`Form` depends on it.

---

## Lessons

*(Empty. Populate from real incidents — what broke, why, and what prevents a repeat. An entry
here should have cost real time.)*
