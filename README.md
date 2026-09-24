# EligiCore

**An eligibility-first job application intelligence API.**

> Most job tools answer *"how well do I fit this role?"* EligiCore answers a different question:
> **"Am I actually eligible for these roles, and why?"**

[![Status](https://img.shields.io/badge/status-pre--release%20development-orange)](CHANGELOG.md)
[![Phase](https://img.shields.io/badge/phase-Week%203%20of%2010-blue)](context/state.md)
[![CI](https://github.com/Lakshya172/eligicore/actions/workflows/ci.yml/badge.svg)](https://github.com/Lakshya172/eligicore/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## The problem

Job hunting has three distinct problems. Most tools solve the wrong two.

| | Problem | Addressed by existing tools |
|---|---|---|
| 1 | **Discovery** — openings scattered across dozens of portals | Partially, by aggregators |
| 2 | **Eligibility** — *"am I even allowed to apply?"* | **Almost nobody** |
| 3 | **Volume** — can't fill out enough forms | Aggressively, by most tools |

Problem 2 is the gap. Every posting carries hard gates — minimum CGPA, permitted branches,
graduation-year windows, backlog limits, work authorization. Checking these by hand across
hundreds of listings is exhausting and error-prone. Students burn applications on roles they
were never eligible for, and skip roles they *were* eligible for out of uncertainty.

## The solution

A backend REST API. A candidate's resume is parsed into a profile, compared against a job
catalogue, and evaluated with **deterministic hard rules first** and AI reasoning **only** for
genuine ambiguity. The result is a ranked, explained list — plus a tracking spreadsheet.

Framed as a person: a knowledgeable senior who has read every posting for you and says *"You
qualify for these fourteen, here's why for each. These three you're borderline on. These you
don't qualify for, and here's the specific reason."*

**They do not apply on your behalf.** That is a design decision, not a missing feature — see
[ADR-008](artifacts/decisions/ADR-008-no-auto-submit.md).

**Who it's for:** students and recent graduates chasing internships and entry-level roles, where
hard eligibility criteria are strictly enforced. Secondarily, placement cells checking a cohort.
Not senior professionals — at that level eligibility gates barely exist and fit dominates.

---

## Project status

**Pre-release development. Weeks 1–8 of a 10-week solo build complete.**

Current stable checkpoint: **Checkpoint 8** (`9aba1f2`) — Week 8 refinement, caching and cost
logging. A résumé becomes a profile, the profile becomes explained eligibility verdicts and ranked
recommendations over a 40-job synthetic catalogue, those become an Excel tracker, and a chosen
job becomes a draft application in which every untraceable claim has been removed — all locally,
with a mock AI provider and no candidate data stored anywhere on the server. Week 8 added no
capability to that flow: it made the system cost-aware and quieter about repeated work, without
changing a single response.

**Checkpoint 6** (`13eb832`) — the complete, demoable Phase 1 MVP — remains the dossier's
declared safe stopping point; Weeks 7–10 are enhancement.

> **Not production-ready.** The Gemini Flash provider has not been exercised against the live
> API — no key is configured and the test suite runs without one. The provider contract is
> covered through a mocked transport; a live smoke test remains pending, and it would also be the
> first real measurement of the Week 8 cost accounting.

This section is kept honest deliberately. Nothing is listed as implemented until it exists,
runs, and is tested. The authoritative, always-current state lives in
[`context/state.md`](context/state.md).

### Implemented

- **Application foundation** — FastAPI app, environment-based configuration, operational
  database base (engine, session factory, declarative base), Alembic environment
- **Candidate profile schema** — universal profile supporting multiple education records, each
  preserving its own grading scale
- **`POST /api/v1/candidates/validate`** — validates a profile and reports gaps as issues rather
  than rejecting them
- **`POST /api/v1/candidates/normalize`** — canonicalizes skills, cleans text fields, and
  produces a scale-independent view of each grade
- **`POST /api/v1/resumes/parse`** — parses a PDF or DOCX resume into a structured profile with per-field confidence. The uploaded file is deleted after processing, on both the success and failure paths.
- **AI provider abstraction** — one interface, a mandatory deterministic mock, and a Google Gemini Flash implementation for Phase 1. Swapping providers is a configuration change.
- **`GET /api/v1/jobs`, `GET /api/v1/jobs/{id}`** — the job catalogue: 40 synthetic postings ingested from a pluggable source adapter with canonical deduplication, loaded locally with `python -m app.cli seed-catalogue`. Closed postings are kept and stay retrievable with their reason, never deleted.
- **`POST /api/v1/eligibility/check`** — evaluates a supplied profile against up to 50 catalogue jobs' stated requirements (minimum CGPA, graduation year window, backlog limit, minimum qualification level, permitted fields) and returns a verdict with a per-requirement breakdown. A field of study that is not an exact match is judged by an AI provider — sent only the field and the permitted fields — and the result is labelled `ai_reasoning`, capped at MEDIUM confidence, and can never make a candidate `NOT_ELIGIBLE`. Nothing is stored.
- **`GET /api/v1/health`** — liveness
- **Matching engine** — deterministic TF-IDF cosine similarity between a candidate's skills and experience and the job catalogue, with skill coverage, the shared terms behind each score and a template explanation. It reads no eligibility data and stores nothing.
- **`POST /api/v1/recommendations`** — eligibility verdicts and relevance scores side by side: eligible jobs ranked by match score, borderline jobs flagged separately, ineligible and closed jobs listed with their reasons but never ranked. The two are never combined into one number. Nothing is stored.
- **`POST /api/v1/applications/export`** — turns the tracking rows a client sends into an Excel tracker, built entirely in memory. Nothing that could run as a formula survives, and nothing is stored.
- **`POST /api/v1/applications/prepare`** — drafts a cover letter and answers to the questions a client supplies, for one catalogue job. Every claim that cannot be traced back to the supplied profile is **removed rather than reworded**, and the response lists what was removed and why. The AI provider is shown a narrow projection of the profile — skills, experience, projects, certifications, education — and never the candidate's name, contacts, employers, languages, grades or résumé text. The result is a draft for the candidate to review and send themselves: **EligiCore never submits an application.** Generation currently runs on the mock provider only. Nothing is stored.
- **AI cost and usage accounting** — résumé extraction and field-relatedness calls log their
  token usage and a derived cost, accumulated across retries. Pricing is configuration with an
  empty default, so no provider price is hard-coded and an unconfigured rate logs `unknown` rather
  than a guess. Operational log records only: no cost table, no ledger, and no cost figure keyed to
  a candidate. **Application generation is deliberately excluded** — a token count is a length that
  could characterize one candidate's content.
- **Corpus vectorizer cache** — the matching engine stops re-fitting the same job catalogue on
  every request, reusing the fitted artifacts for up to four catalogues per process, keyed by a
  fingerprint of the catalogue itself. **The candidate is never cached**: their transform is
  recomputed every request. Results are identical cold and warm.
- **Complete operational request logging** — every inbound request produces exactly one record,
  including the ones that end in an unhandled exception, which were previously missed. No candidate
  data in any log line.
- **1549 tests**, running offline with no credentials and no network — including a full-flow
  integration test that walks résumé → profile → eligibility → recommendations → application
  preparation → Excel export
- Engineering environment: architectural context, ADRs, standards, review lenses, quality gates
- Repository workflow: branching, conventional commits, PR standard, CI, checkpoint discipline

All endpoints are stateless. Nothing is stored: there is no `candidates` table, and a test
asserts none exists. Uploaded resumes exist only for the duration of processing.

**Nothing is fabricated.** Fields a resume does not state are left absent rather than guessed; a grade without a stated scale keeps `scale: UNKNOWN` rather than being assumed out of 10; an unstated backlog count stays `null` rather than becoming `0`; and extracted skills that cannot be traced back to the resume text are removed and reported.

### Planned — the 10-week build

| Week | Deliverable | Status |
|---|---|---|
| 1 | Foundation, config, database base, candidate profile schema, stateless validate/normalize endpoints | **Complete** |
| 2 | Resume parser and AI provider abstraction | **Complete** |
| 3 | Job schema, source adapters, ingestion, deduplication | **Complete** |
| 4 | Eligibility engine — deterministic rules plus AI for ambiguity | **Complete** — deterministic engine (PR #9) + AI field relatedness (PR #11), Checkpoint 4 |
| 5 | Matching engine — skill normalization, TF-IDF, cosine similarity | **Complete** — matching engine (PR #13) + recommendations endpoint (PR #15), Checkpoint 5 |
| 6 | **Polish, Excel export, testing — complete demoable MVP** | **Complete** — Excel export (PR #17, Checkpoint 6A) + demo path and full-flow test (PR #19), Checkpoint 6 |
| 7 | Application preparation with truthfulness validation | **Complete** — truthfulness validator (PR #24) + preparation endpoint (PR #28), Checkpoint 7; live provider generation deferred |
| 8 | Caching and AI cost logging | **Complete** — cost/usage accounting (PR #34) + corpus cache (PR #35) + operational logs (PR #36), Checkpoint 8; cost coverage excludes the generation path, and live Gemini application generation remains deferred |
| 9 | Documentation and deployment | Not started |
| 10 | Buffer | Not started |

**Week 6 is the declared safe stopping point.** Everything after it is enhancement.

### Future phases

Frontend dashboard and a browser extension that autofills within the candidate's own session
(Phase 2) · live job-source adapters within Terms of Service (Phase 3) · multi-user platform
with authentication (Phase 4) · institutional cohort evaluation (Phase 5).

### Deliberately out of scope

No auto-submit. No browser automation for submission. No CAPTCHA, OTP or anti-bot
circumvention. No scraping that violates a source's Terms of Service. These are permanent
constraints, not deferred features.

---

## Architecture

```
┌──────────────────────────────────────────────┐
│  API LAYER        app/routers/                │  HTTP only, no business logic
├──────────────────────────────────────────────┤
│  SERVICE LAYER    app/services/               │  All business logic,
│                                               │  framework-agnostic, testable
├───────────────────────┬──────────────────────┤  without a server
│  AI LAYER  app/ai/    │  ADAPTERS            │  Provider- and source-agnostic
├───────────────────────┴──────────────────────┤
│  SERVER DATA      app/models/ + database.py   │  OPERATIONAL DATA ONLY
└──────────────────────────────────────────────┘

                ═══ device boundary ═══

┌──────────────────────────────────────────────┐
│  CLIENT DATA (user's device, Phase 2)         │  IndexedDB: profile, resume,
│                                               │  results, tracking, notes
└──────────────────────────────────────────────┘
```

### Local-first privacy model

**Personal data lives on the user's device. The backend is a processing service, not a
personal-data database.** This is the project's defining architectural property.

| Stays on the device (IndexedDB) | Stored on the server |
|---|---|
| Candidate profile | Job catalogue |
| Resume file and extracted data | Adapter and ingestion state |
| Eligibility and matching results | Operational logs |
| Application tracking and status | |
| Notes, chat history, AI context | **Nothing else.** |

Personal data **passes through** the backend for processing and is not retained. There is no
`candidates` table, no `applications` table, and no `evaluations` table — and none may be
created ([ADR-011](artifacts/decisions/ADR-011-no-server-side-candidate-or-application-persistence.md)).

Consequences that follow from this, each load-bearing:

- Every personal-data endpoint is **stateless** — the client sends what an operation needs, the
  backend computes and returns, the client persists locally
- `candidate_id` is a **client-generated correlation identifier**, not a server-side key
- There is no `GET`/`PATCH` on a candidate resource — those would imply a server-held record
- There is no application-status endpoint — status lives in IndexedDB
- Uploaded resumes exist only for the duration of processing and are deleted afterwards, on both
  the success and failure paths

*Caveat, stated honestly:* this is a design commitment about how the application is built and
configured. It is not an absolute guarantee about every layer of underlying infrastructure.

### Eligibility: deterministic before probabilistic

```
1. Parse and normalize the requirement
2. Evaluate deterministic hard constraints
3. If a VERIFIED hard constraint fails → NOT_ELIGIBLE. The remaining deterministic checks
   still run, so every verified reason is reported; AI is not consulted for that job.
4. If deterministic rules pass but ambiguity remains → AI reasoning
5. Produce final state with confidence and explanation
```

**AI never overrides a verified deterministic hard failure.** Comparing two numbers with a
language model is slower, costlier and less reliable than `>=`.

*Verified* means the data is present and valid. Missing or unparseable data yields `UNKNOWN` or
`NEEDS_REVIEW` — **never a failure**. Absence of evidence is not evidence of ineligibility.

Confidence measures how much the system trusts its own determination, and is **independent of**
eligibility. A deterministic hard failure is a HIGH-confidence `NOT_ELIGIBLE`.

Every verdict carries a per-requirement breakdown and a human-readable reason. An unexplained
answer is treated as a failure, not a result.

---

## Technology stack

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.11+ | Best ecosystem for text processing, NLP and AI integration |
| Web framework | FastAPI | Self-documenting `/docs`; type hints double as validation; async-ready for slow AI calls |
| Server | Uvicorn | Standard ASGI pairing |
| Validation | Pydantic | Every request and response shape defined and enforced at the boundary |
| ORM | SQLAlchemy | Same model code targets SQLite in dev and PostgreSQL in production |
| Database | SQLite → PostgreSQL | Operational data only. Zero-setup locally; parity validated before deployment, not assumed |
| Migrations | Alembic | Schema changes as explicit reviewable scripts |
| Resume parsing | pdfplumber, python-docx | Layout-heavy documents need reliable layout handling |
| NLP fallback | spaCy | Deterministic extraction of predictable fields with no AI call |
| Matching | scikit-learn | TF-IDF and cosine similarity — no training, and **explainable** |
| Export | openpyxl | Excel tracker generation |
| AI provider | Google Gemini Flash | Phase 1 default ([ADR-013](artifacts/decisions/ADR-013-gemini-flash-phase-1-default-provider.md)). A concrete implementation behind the provider abstraction, not a dependency — swapping it is a config change plus one class. |
| HTTP client | httpx | Async-capable, for AI provider calls. Used instead of a vendor SDK. |
| Testing | pytest | Written alongside features, not at the end |

TF-IDF was chosen over embeddings specifically because it is explainable — the system can state
which terms drove a score. For a product whose value proposition is transparency, an
unexplainable score is self-defeating.

---

## Quickstart

Runs entirely on your machine: SQLite, a synthetic job catalogue, and a deterministic mock AI
provider. **No API key, no network and no configuration are required** — deployment and the
public documentation are Week 9.

**Requires Python 3.11 or newer** (built and tested on 3.12).

**1. Clone and create a virtual environment**

```bash
git clone https://github.com/Lakshya172/eligicore.git
cd eligicore
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell, activate it with:

```powershell
.venv\Scripts\Activate.ps1
```

**2. Install the dependencies**

```bash
pip install -r requirements.txt
```

**3. Configure (optional)**

The defaults — SQLite at `./eligicore.db` and the mock AI provider — need no `.env`. Copy the
example only if you want to change them:

```bash
cp .env.example .env
```

**4. Create the database and load the catalogue**

```bash
alembic upgrade head
python -m app.cli seed-catalogue
```

The seed command loads 40 synthetic postings through the normal adapter and ingestion path. It is
idempotent — run it again and it reports every job unchanged — and it deletes nothing. It refuses
to run unless the schema is at the latest migration, so if you have an `eligicore.db` from an
earlier checkout, run `alembic upgrade head` first (or delete the file and start again; it holds
only public job data).

There is deliberately **no HTTP endpoint that writes the catalogue**: seeding is local tooling.

**5. Start the API**

```bash
uvicorn app.main:app --reload
```

**6. Open the interactive documentation**

`http://127.0.0.1:8000/docs` — generated from the code itself, so it is always accurate. Every
endpoint can be tried from that page.

### Try the flow

The API is stateless: you send a profile, you get a result back, and **nothing about the candidate
is stored**. This example uses an obviously synthetic profile.

**Recommendations** — eligibility verdicts and relevance scores side by side:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/recommendations \
  -H "Content-Type: application/json" \
  -d '{"profile": {"candidate_id": "demo-1",
       "education": [{"degree": "B.Tech", "level": "BACHELORS",
                      "field_of_study": "Information Technology",
                      "grad_year": 2027, "cgpa": 8.2, "scale": "SCALE_10"}],
       "skills": ["Python", "SQL", "Docker", "Git"],
       "backlogs": 0}}'
```

The response groups every job: `ranked`, `needs_review`, `not_eligible` (kept, with reasons, never
scored) and `not_open`. Each item carries the per-requirement breakdown that explains its verdict.

**Excel tracker** — turn rows you keep on your side into a workbook:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/applications/export \
  -H "Content-Type: application/json" \
  -o eligicore-tracker.xlsx \
  -d '{"records": [{"job_id": "demo-job-1", "company_name": "Example Co",
       "role_title": "Backend Engineering Intern", "eligibility_state": "ELIGIBLE",
       "match_score": 73.2, "application_status": "APPLIED"}]}'
```

**Résumé parsing** (`POST /api/v1/resumes/parse`) accepts a PDF or DOCX, returns a structured
profile with per-field confidence, and deletes the file as soon as parsing finishes. With the
default mock provider the extraction is deterministic and offline; set `ELIGICORE_AI_PROVIDER` and
a key to use a real provider.

To see the whole journey — parse, complete the profile, check eligibility, recommend, export — read
`tests/test_full_flow.py`, which exercises exactly that against the seeded catalogue.

### Testing

```bash
pytest -q
```

The suite runs with **no network and no API key**. All AI calls go through a mock provider.

---

## Repository workflow

`main` is always a known-good checkpoint. Feature development never happens directly on it.

```
Human approves phase → feature branch → implement → test → review → quality gates
   → context update → commits → PR → human review → merge → stable checkpoint
```

| Branch | Purpose |
|---|---|
| `feature/week-N-<slug>` | An approved phase |
| `fix/<description>` | Bug fix |
| `docs/<description>` | Documentation only |

Conventional commits throughout. Every merged PR is a checkpoint the project can be recovered
to. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full working agreement.

### Engineering layer

This repository carries its own engineering context so that any session — human or AI — starts
with the same understanding.

| Path | Contents |
|---|---|
| [`AGENTOS.md`](AGENTOS.md) | Entry point, authority hierarchy, session protocol |
| [`context/`](context/) | Vision, **current state**, architecture, tech stack, decisions, workflow, memory |
| [`artifacts/decisions/`](artifacts/decisions/) | 12 ADRs — every architectural decision and why |
| [`standards/`](standards/) | Eligibility, security & privacy, AI, API design, code quality, testing |
| [`reviewers/`](reviewers/) | Eight review lenses, selected by change impact |
| [`checklists/`](checklists/) | Quality gates QG-001 … QG-007 |

**Start at [`context/state.md`](context/state.md)** — it describes what actually exists, as
opposed to what is planned.

---

## License

[MIT](LICENSE) © 2026 Lakshya Agarwal
