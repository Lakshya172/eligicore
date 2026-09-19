# ADR-024 — Week 6 MVP scope: local setup, curated catalogue, full-flow test

**Status:** Accepted · **Date:** 2026-09-20 · **Type:** Design ruling (Week 6B design gate, PR 6B)
**Source:** dossier §6, §7, §8.2, §11, §15 (Weeks 3 and 6), §16, §17
**Decided by:** project owner, Week 6B design gate
**Enforces:** INV-1, INV-4, INV-6, INV-7, INV-12 · **Refines:** ADR-005, ADR-011, ADR-014, ADR-023
**Rules on:** C-30, C-31, C-32, C-33, C-34, A-37..A-52

---

## Context

Dossier §15 makes Week 6 the safe stopping point: *"Complete, demoable product."* After Checkpoint
6A (the Excel tracker export) four gaps stood between the repository and that claim:

- A fresh clone had no way to load the job catalogue. `/api/v1/jobs/ingest` is deferred (C-25,
  ADR-023 §11), and nothing outside the tests called the ingestion service.
- The curated catalogue held 5 jobs; the Week 3 deliverable was *"30–50 curated jobs in database
  via adapter pattern"* (C-26).
- §17 asks for *"integration tests covering the full flow"* and for recommendations that *"rank
  sensibly across distinct candidate profiles"*.
- The README had no migration or seeding step, so §17's *"stranger … under 10 minutes"* could not
  be met (C-27).

PR 6B closes those gaps and adds no product feature.

## Decision

### 1. Local seed command, not an HTTP trigger (C-33, A-43..A-46)

`python -m app.cli seed-catalogue` — `app/cli.py`, standard-library `argparse`, no `__main__.py`.

- Reads the existing settings and connects to `ELIGICORE_DATABASE_URL`.
- **Refuses unless the database is at the Alembic head** — it compares the database's recorded
  revision with the script head, read-only. It never runs a migration, never calls
  `create_all`, never repairs a schema. A missing SQLite file is refused *before* connecting,
  because connecting would create an empty file. The message tells the developer to run
  `alembic upgrade head` and names no path or URL (a URL can carry credentials).
- Seeds through the **existing** path only: `ingest_all(session, [CuratedJobAdapter()])`.
  Normalisation, content hashing, deduplication, upserts, `ingestion_state` and authoritative
  closure are reused unchanged. The command is not a second ingestion implementation.
- **Idempotent.** A second run reports every job unchanged; no duplicate is created.
- **Deletes nothing** and has no reset flag. The curated source is authoritative (ADR-014), so a
  job removed from the file becomes `CLOSED` — existing behaviour, unchanged.
- **Takes no input** beyond the subcommand: no dataset path, no candidate data, no résumé, no
  network input. Prints counts only — seen, created, updated, unchanged, closed.
- Writes only `jobs` and `ingestion_state`.

**Why not HTTP `/jobs/ingest`.** An unauthenticated endpoint that writes the catalogue is an abuse
surface on a public deployment, and Phase 1 has no authentication. Dossier §7 step 4 says ingestion
*"runs independently"*; a local command satisfies that. C-25 stands.

**Why a structural addition.** Dossier §8.2's folder listing has no CLI (C-33). The command is the
smallest addition that gives setup without HTTP, and it holds no business logic.

### 2. Curated catalogue: 40 synthetic jobs (C-26, A-37..A-42)

- **Exactly 40 jobs** in `app/data/curated_jobs.json` — inside the dossier's 30–50 and below the
  recommendation default-scope cap of 50, so a default request considers every job.
- **The original 5 entries are byte-identical and first.** Their content hashes, database identity
  and Week 4 golden verdicts are unchanged. 35 jobs are appended, `EX-INT-006` … `EX-FT-040`,
  following the existing `EX-<INT|FT>-NNN` pattern.
- **Synthetic only.** Fictional "Example …" / "Sample …" companies, `careers.example.com` links, no
  contact details, no personal data, no real employer.
- **Every entry is a valid `RawJob`** and goes through the production adapter.
- **Diversity, asserted by tests:** software, backend, frontend, full-stack, data, ML, DevOps/SRE,
  QA, security, embedded/hardware, analyst, mechanical, electrical, finance/accounting; internships
  and full-time; CGPA on `SCALE_10`, `SCALE_4` and `PERCENTAGE`, plus a cutoff with no stated scale
  (`UNKNOWN`) and no cutoff; graduation windows across 2025–2029 including open-ended ones; no
  degree requirement, `BACHELORS` and `MASTERS`; exact permitted fields, fields that reach the AI
  relatedness stage, and no restriction; backlog limits 0, 1, 2 and unstated; skills including C++,
  C#, `.NET`, React.js, Node.js, Python, SQL and Java.
- **`NO_JOB_TERMS` edge case.** `EX-INT-039` is a general-application listing titled `Other` with
  no description and no skills. Its title is a stop word and matching reads only title, description
  and skills (ADR-020), so it has no job terms and scores `null` — exercised without touching the
  matching engine.
- **Deadlines** are in 2026–2027 or null. Status is never inferred from a deadline (ADR-014); the
  README says so.

### 3. Curated jobs stay ACTIVE (C-30, A-41)

`RawJob` gains **no** `status` field. Every job loaded from the curated file is `ACTIVE`, exactly
as ingestion has always behaved. `CLOSED`, `EXPIRED` and `UNKNOWN` remain valid operational states:
`CLOSED` is produced by authoritative disappearance today; `EXPIRED` and `UNKNOWN` are reserved for
future sources and lifecycle rules. `not_open` stays covered by controlled test fixtures and the
Week 5 recommendation tests.

**ADR-014's revisit condition** (collapse the enum if `EXPIRED` and `UNKNOWN` were unused by the end
of Week 5) is answered: **the enum is kept.** Both states are consumed by the recommendation layer
(`not_open`, default scope) and by `GET /jobs` filters, and Phase 3 live sources are expected to
produce them. Revisit when the first non-curated adapter is designed.

### 4. Existing tests coupled to the 5-job file (C-31)

Exactly three existing assertions assumed the file held five jobs. They are changed, and nothing
else:

| Test | Was | Now |
|---|---|---|
| `test_job_ingestion.py::test_curated_dataset_ingests` | `jobs_seen == 5`, `jobs_created == 5` | equal to the number of entries in the dataset file |
| `test_job_ingestion.py::test_curated_dataset_is_idempotent` | `jobs_unchanged == 5` | equal to the number of entries in the dataset file |
| `test_eligibility_engine.py::test_curated_dataset_golden_verdicts` | exact verdicts for every job in the file | the same five verdicts, for the original five ids only |

The golden expectations themselves are unchanged.

### 5. Full-flow integration test (A-47)

`tests/test_full_flow.py` drives the public HTTP API through `TestClient`, offline:

- **Database:** in-memory SQLite built with the repository's test convention, seeded with
  `app.cli.seed_catalogue` — the function the command uses — from the real curated file.
- **Profile A:** the existing synthetic résumé fixture → `POST /resumes/parse` → dossier §7 step 3
  modelled explicitly (the client completes `field_of_study`, `level` and `backlogs`, which the mock
  parse leaves empty) → `/candidates/validate` → `/candidates/normalize` → `/eligibility/check` →
  `/recommendations` → tracker rows built from the response → `/applications/export` → workbook
  reopened and checked.
- **Profile B:** a distinct synthetic profile (Mechanical Engineering, 4-point scale, one backlog)
  that must produce a different recommendation structure.
- **AI:** the default mock (field relatedness `UNCERTAIN`) on the main path; one run overrides the
  AI dependency with the existing mock pinned to `RELATED` / `MEDIUM` to show `LIKELY_ELIGIBLE`. A
  socket guard fails the test on any network connection attempt. No provider, prompt or AI schema
  changes.
- **Assertions:** golden group membership by curated `source_job_id` for both profiles; rank order;
  eligibility verdicts equal between `/eligibility/check` and `/recommendations`; no score in
  `not_eligible`; the `NO_JOB_TERMS` job; the tracker workbook's rows, null score and Requirements
  sheet; no candidate data in the database, logs, errors or files.

The golden expectations are deliberate: a catalogue edit that changes an outcome must update the
test in the same change.

### 6. Local quickstart and OpenAPI text (C-32, C-34, A-48, A-50)

- README gains a **local** quickstart: Python 3.11+, venv (Bash and PowerShell), `pip install`,
  optional `.env`, `alembic upgrade head`, `python -m app.cli seed-catalogue`, `uvicorn`, `/docs`,
  and a synthetic parse → recommendations → export walk-through, with a note on an out-of-date local
  `eligicore.db`. Full documentation and deployment stay in Week 9.
- The OpenAPI status keeps *"Weeks 1–5 of a 10-week build are complete and Week 6 is underway"*
  until Checkpoint 6 is recorded, and mentions the seeded catalogue. The existing assertion on that
  sentence remains valid and is not modified.

### 7. Checkpoint (A-49, A-52)

One PR, `feature/week-6-polish`. After merge and post-merge verification, **Checkpoint 6 — Week 6
MVP (final)** is recorded by a separate documentation PR; Checkpoint 6A stays the intermediate
record. A checkpoint is not a release, version or tag (C-28).

## Non-goals

`/api/v1/matching/score` · `/api/v1/jobs/ingest` · `/api/v1/applications/prepare` · application
preparation · truthfulness validation · caching · cost logging · deployment · frontend ·
authentication · live job sources · new AI, providers or prompts · eligibility or matching changes ·
status inference from deadlines · a `RawJob` status field · any candidate, evaluation, application
or tracker storage · auto-submit · browser automation · CAPTCHA/OTP bypass · AgentOS as a product
runtime.

## Consequences

**Positive.** A fresh clone reaches a working demo with four commands and no HTTP write surface.
The catalogue exercises every eligibility and matching path the engines have. One test proves the
whole Phase 1 flow end to end, offline.

**Negative / accepted.** Golden expectations tie the full-flow test to the catalogue's content.
Static deadlines and graduation windows age; statuses do not follow them. The seed command depends
on Alembic's read-only APIs to compare revisions.
