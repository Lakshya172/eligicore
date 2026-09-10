# EligiCore

**An eligibility-first job application intelligence API.**

> Most job tools answer *"how well do I fit this role?"* EligiCore answers a different question:
> **"Am I actually eligible for these roles, and why?"**

[![Status](https://img.shields.io/badge/status-pre--release%20development-orange)](CHANGELOG.md)
[![Phase](https://img.shields.io/badge/phase-Week%201%20of%2010-blue)](context/state.md)
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

**Pre-release development. Week 1 of a 10-week solo build.**

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
- **`GET /api/v1/health`** — liveness
- **86 tests**, running offline with no credentials
- Engineering environment: architectural context, ADRs, standards, review lenses, quality gates
- Repository workflow: branching, conventional commits, PR standard, CI, checkpoint discipline

Both candidate endpoints are stateless. Nothing is stored: there is no `candidates` table, and a
test asserts none exists.

### Planned — the 10-week build

| Week | Deliverable | Status |
|---|---|---|
| 1 | Foundation, config, database base, candidate profile schema, stateless validate/normalize endpoints | **Complete** |
| 2 | Resume parser and AI provider abstraction | Not started |
| 3 | Job schema, source adapters, ingestion, deduplication | Not started |
| 4 | Eligibility engine — deterministic rules plus AI for ambiguity | Not started |
| 5 | Matching engine — skill normalization, TF-IDF, cosine similarity | Not started |
| 6 | **Polish, Excel export, testing — complete demoable MVP** | Not started |
| 7 | Application preparation with truthfulness validation | Not started |
| 8 | Caching and AI cost logging | Not started |
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
3. If a VERIFIED hard constraint fails → NOT_ELIGIBLE. Stop. AI is not consulted.
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
| HTTP client | httpx | Async-capable, for AI provider calls |
| Testing | pytest | Written alongside features, not at the end |

TF-IDF was chosen over embeddings specifically because it is explainable — the system can state
which terms drove a score. For a product whose value proposition is transparency, an
unexplainable score is self-defeating.

---

## Development setup

```bash
git clone https://github.com/Lakshya172/eligicore.git
cd eligicore

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env           # then fill in local values
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Interactive API documentation is then at `http://127.0.0.1:8000/docs` — generated from the code
itself, so it is always accurate.

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
