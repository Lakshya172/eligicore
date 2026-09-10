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

## Lessons

*(Empty. Populate from real incidents — what broke, why, and what prevents a repeat. An entry
here should have cost real time.)*
