# ELIGICORE
## An Eligibility-First Job Application Intelligence API

### Project Dossier

**Document type:** Project overview and technical plan
**Status:** Pre-development (planning complete)
**Author:** Solo developer
**Version:** 1.0 — Final
**Date:** September 2026

---

# TABLE OF CONTENTS

1. Project Identity
2. Executive Summary
3. The Problem
4. The Solution
5. Who This Is For
6. What It Does NOT Do (and Why)
7. System Workflow
8. Technical Architecture
9. Technology Stack — What, How, and Why
10. Data Design
11. API Endpoint Reference
12. Core Algorithms Explained
13. Design Principles
14. Competitive Landscape
15. Development Roadmap
16. Risks and Mitigations
17. Success Criteria
18. Future Phases
19. Glossary

---

# 1. PROJECT IDENTITY

## Name

**EligiCore**

## Meaning

*Eligi-* from **eligibility** — the central question the system answers.
*-Core* signalling a **core engine**: infrastructure other software is built on top of, rather than a finished consumer app.

Together: **the eligibility engine at the core of a job search.**

## Positioning statement

> EligiCore is a backend API that determines which jobs and internships a candidate is genuinely eligible for — and explains exactly why.

## One-line description (for a repository or resume)

> Eligibility-first job application intelligence API with pluggable job-source adapters, explainable rule-plus-AI eligibility reasoning, and truthfulness-validated application generation.

## Why this name was chosen

- **It names the differentiator.** Most tools in this space score *fit*. EligiCore evaluates *eligibility* — the hard, rule-based gates that actually block student applications. The name puts that front and centre.
- **It signals engineering, not gimmick.** "Core" reads as infrastructure. This is a backend architecture project, and the name reflects that rather than implying a bulk-application bot.
- **It does not overpromise.** Nothing in the name suggests automatic applying, which the system deliberately does not do.
- **It does not box the project in.** The name works equally well if the audience later broadens beyond students, or beyond one country's education system.
- **It is practical.** Short, spellable, pronounceable, and unlikely to collide with an existing product.

## Naming conventions for the project

| Context | Form |
|---|---|
| Formal / documentation | EligiCore |
| Repository and package name | `eligicore` |
| API namespace | `/api/v1/...` |
| Environment variable prefix | `ELIGICORE_` |
| Database name | `eligicore` |

---

# 2. EXECUTIVE SUMMARY

**EligiCore is a backend REST API that answers one question reliably: "Which jobs and internships am I actually eligible for, and why?"**

A candidate uploads their resume once. The system extracts their profile, compares it against every job posting in its database, applies both hard eligibility rules (CGPA cutoffs, degree requirements, graduation year, backlog policies) and AI reasoning for ambiguous cases, then returns a ranked, explained list of opportunities — plus a downloadable tracking spreadsheet.

It deliberately does **not** submit applications automatically. It is a filter and a decision-support tool, not a bulk-application bot.

**Project scope:** 10 weeks, solo, backend only. A frontend is planned as a separate later phase.

**Primary purpose:** A portfolio-grade demonstration of backend architecture — pluggable adapters, provider abstraction, explainable rule engines, and AI integration with cost and truthfulness controls.

---

# 3. THE PROBLEM

Students and early-career candidates face three distinct problems during job hunting. Most existing tools address only the third.

### Problem 1: Discovery — "Where do I even look?"
Openings are scattered across dozens of portals (Unstop, Internshala, LinkedIn, Naukri) and hundreds of individual company career pages. No single place aggregates them meaningfully.

### Problem 2: Eligibility — "Am I even allowed to apply?" ← **the real gap**
Every posting has hard gates: minimum CGPA, permitted branches or degrees, graduation year windows, backlog limits, location or work-authorization constraints. Checking these manually across hundreds of listings is exhausting and error-prone. Candidates routinely waste hours applying to roles they were never eligible for, or skip roles they *were* eligible for out of uncertainty.

### Problem 3: Volume — "I can't apply to enough places."
One person can only fill out so many forms.

**Key insight:** Nearly every existing tool attacks Problem 3 (apply faster, apply to more) and some attack Problem 1 (aggregate listings). Almost none rigorously solve Problem 2 — the structured, explainable eligibility check. That gap is where this project lives.

---

# 4. THE SOLUTION

EligiCore is an API-first system built around explainable eligibility checking.

### In plain language

Think of it as a knowledgeable senior who has read every job posting for you. You hand them your resume, and they tell you: *"You qualify for these fourteen. Here's why you qualify for each. These three you're borderline on — check with the company. These you don't qualify for, and here's the specific reason."*

Then they hand you a spreadsheet so you can track what you've applied to.

They do **not** apply on your behalf. You keep control of what gets submitted in your name.

### In technical language

A FastAPI service exposing endpoints for resume parsing, candidate profile management, job ingestion via pluggable source adapters, deterministic-plus-AI eligibility evaluation, similarity-based match ranking, and spreadsheet export — backed by a relational database and an AI provider abstraction layer.

---

# 5. WHO THIS IS FOR

**Primary users:** Students and recent graduates applying for internships and entry-level roles, where hard eligibility criteria (CGPA, branch, graduation year, backlogs) are strictly enforced and are the main source of confusion.

**Secondary users:** Career services offices and placement cells, who could use the API to check an entire cohort against a set of openings at once.

**Not designed for:** Senior professionals. At that level, eligibility gates barely exist — fit and networking dominate. Tools optimized for that audience already exist and solve a different problem.

---

# 6. WHAT IT DOES NOT DO (AND WHY)

This section is deliberately prominent, because these are design decisions, not missing features.

### It does not auto-submit applications

**Why:**
- **Terms of Service.** Most major job portals explicitly prohibit automated submission. Building on top of that is legally fragile and can get user accounts permanently banned.
- **Reliability.** Application forms differ wildly between companies. CAPTCHAs, login walls, multi-step wizards, and file-upload quirks mean automation breaks constantly. Maintenance cost is enormous and the success rate is poor.
- **Quality.** Mass-applying lowers response rates and wastes recruiter time. Filtering to fewer, better-matched applications produces better outcomes for everyone.
- **Accountability.** An application submitted in your name should be one you saw and approved. Automated submission removes that.

This constraint is stated openly rather than treated as a limitation — it is the same conclusion reached independently by mature tools in this space.

### It does not scrape live portals in Phase 1

The initial dataset is manually curated. This de-risks the hardest unsolved part of the problem (legally and technically sound job data acquisition) while everything downstream is built and validated. The adapter architecture means adding real sources later requires no changes to the rest of the system.

### It does not include a user interface in Phase 1

This is an API-first project by design. A frontend is a separate later phase that will consume the same API without modification.

### It does not fabricate anything

Any AI-generated application content is validated against the candidate's actual profile data. Claims that cannot be traced to real profile data are flagged or removed.

---

# 7. SYSTEM WORKFLOW

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1 — RESUME UPLOAD                                       │
│ Candidate uploads PDF or DOCX                                │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 2 — PARSING                                             │
│ Text extracted → AI structures it into profile fields        │
│ Each field tagged: high / medium / low confidence            │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 3 — PROFILE COMPLETION                                  │
│ Candidate fills gaps and corrects low-confidence fields      │
│ Result: complete Candidate Profile in local IndexedDB        │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 4 — JOB INGESTION (runs independently)                  │
│ Adapters fetch → normalize → deduplicate → store             │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 5 — ELIGIBILITY EVALUATION                              │
│ Hard rules first (deterministic, no AI):                     │
│   degree level · CGPA · graduation year · backlogs           │
│ AI reasoning only for ambiguous cases:                       │
│   "CS or related field" vs candidate's "IT" degree           │
│ Output: state + per-requirement breakdown                    │
│   ELIGIBLE · LIKELY_ELIGIBLE · NEEDS_REVIEW · NOT_ELIGIBLE   │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 6 — MATCH RANKING                                       │
│ Skill normalization → TF-IDF → cosine similarity → 0–100     │
│ Eligible jobs ranked; borderline jobs flagged separately     │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 7 — DELIVERY                                            │
│ Ranked JSON list with reasons  ·  Excel tracker export       │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 8 — APPLICATION PREPARATION (later phase)               │
│ Tailored cover letter + answers → truthfulness validated     │
│ Output: ready to REVIEW, never auto-submitted                │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 9 — CANDIDATE ACTS                                      │
│ Reviews, applies manually, updates tracking status           │
└─────────────────────────────────────────────────────────────┘
```

### The six questions the system answers

| # | Question | Answered by |
|---|---|---|
| 1 | Can I apply? | Eligibility Engine |
| 2 | Should I apply? | Matching Engine |
| 3 | How do I apply? | Job record (link, deadline, source) |
| 4 | What do I submit? | Application Preparation |
| 5 | Is it truthful? | Truthfulness Validator |
| 6 | Did I already apply? | Tracker and Excel export |

---

# 8. TECHNICAL ARCHITECTURE

## 8.1 Layered structure

```
┌──────────────────────────────────────────────┐
│  API LAYER (routers/)                         │
│  HTTP endpoints, request validation,          │
│  response shaping. No business logic here.    │
└───────────────────┬──────────────────────────┘
                    ▼
┌──────────────────────────────────────────────┐
│  SERVICE LAYER (services/)                    │
│  All business logic: parsing, eligibility,    │
│  matching, application prep, validation.      │
│  Framework-agnostic and independently testable│
└──────┬────────────────────────────┬──────────┘
       ▼                            ▼
┌──────────────────┐    ┌───────────────────────┐
│  AI LAYER (ai/)  │    │ ADAPTER LAYER         │
│  Provider-       │    │ (adapters/)           │
│  agnostic        │    │ Source-agnostic job    │
│  interface       │    │ ingestion              │
└──────┬───────────┘    └───────────┬───────────┘
       ▼                            ▼
┌──────────────────────────────────────────────┐
│  SERVER DATA LAYER (models/ + database.py)    │
│  SQLAlchemy ORM, database sessions            │
│  Operational data only: job catalogue,        │
│  adapter state, logs. Personal data not      │
│  intentionally persisted (see 8.1b)          │
└──────────────────────────────────────────────┘

                  ═══ device boundary ═══

┌──────────────────────────────────────────────┐
│  CLIENT DATA LAYER (on the user's device)     │
│  IndexedDB  — profile, resume, evaluations,   │
│               matches, tracking, notes,       │
│               chat history, AI context        │
│  localStorage — small preferences and UI state│
└──────────────────────────────────────────────┘
```

**Why layered:** Business logic stays independent of both the web framework and the AI provider. This means the matching engine can be tested without starting a server, and the AI provider can be swapped without touching business logic. It also makes the code readable to anyone reviewing it.

## 8.1a Local-first data ownership

EligiCore is **local-first**. The user's personal data lives on the user's own device by default; the backend is a processing service, not a personal data store.

**Stored locally on the device**
- Candidate profile
- Resume file and extracted resume data
- User preferences
- Jobs cached for that user
- Eligibility results
- Matching results
- Application tracking and status
- Notes
- Chat and conversation history
- AI memory and context
- Any other user-specific EligiCore data

**Handled by the backend (processing and services)**
- Resume parsing
- Job ingestion
- Eligibility evaluation
- Matching
- AI processing
- Recommendations
- Other required API operations

**Retained by the backend**
Only what is genuinely required for system operation: the job catalogue, adapter and ingestion state, and operational logs.

**How this works in practice:** the client sends the data needed for a given operation, the backend computes a result and returns it, and the client persists that result locally. Personal data passes through the backend for processing; it is not kept there by default.

**Why local-first:**
- The user owns their resume, profile, and application history outright
- The system stores far less sensitive personal data server-side, reducing exposure
- Results the user has already computed remain available on their device
- The processing architecture, adapters, AI abstraction, and endpoint design are unchanged — only the resting place of personal data moves

## 8.1b Data handling rules

### What "not persisted" means precisely

Personal data is not intentionally persisted by the application as part of normal operation. Request handling, temporary processing storage, infrastructure-level logs, and error telemetry must be designed and configured to avoid retaining unnecessary personal data.

This is a design commitment about how the application is built and configured, not an absolute guarantee about every layer of underlying infrastructure.

### Identifier semantics

`candidate_id` is a **client-generated stable identifier** used to correlate operations and results across requests. It is not a pointer to a server-side personal-data record. The client generates it, owns it, and stores it alongside the profile in IndexedDB.

### Resume lifecycle

- Resume files may exist temporarily in backend memory or temporary storage while being processed
- They are **not** persisted as permanent user records by default
- Temporary files are deleted after processing completes, whether it succeeds or fails, subject to normal error handling
- Extracted data returned to the client is persisted locally by the client
- The backend does not retain the original resume unless a future, explicitly documented feature requires it

### Logging rules

Do not log:
- Resume contents
- Candidate profile payloads
- Generated application content containing personal information

Sanitize exception and error logging so personal data is not accidentally persisted through stack traces or captured request bodies.

Log instead: request IDs, timings, status codes, operation type, and safe technical metadata. Operational logs are retained for system diagnostics.

## 8.2 Project folder structure

```
eligicore/
├── app/
│   ├── main.py                  # FastAPI entrypoint
│   ├── config.py                # Environment configuration
│   ├── database.py              # DB engine, session, base
│   │
│   ├── models/                  # SQLAlchemy database models
│   │   ├── candidate.py
│   │   ├── job.py
│   │   └── application.py
│   │
│   ├── schemas/                 # Pydantic request/response shapes
│   │   ├── candidate.py
│   │   ├── job.py
│   │   └── eligibility.py
│   │
│   ├── routers/                 # HTTP endpoint definitions
│   │   ├── candidates.py
│   │   ├── resumes.py
│   │   ├── jobs.py
│   │   ├── eligibility.py
│   │   ├── matching.py
│   │   └── applications.py
│   │
│   ├── services/                # Business logic
│   │   ├── resume_parser.py
│   │   ├── eligibility_engine.py
│   │   ├── matching_engine.py
│   │   ├── application_prep.py
│   │   └── truthfulness_validator.py
│   │
│   ├── ai/                      # AI provider abstraction
│   │   ├── ai_service.py
│   │   ├── prompts/             # Prompts as files, not inline strings
│   │   └── providers/
│   │       ├── base.py          # Abstract interface
│   │       └── openai_provider.py
│   │
│   ├── adapters/                # Job source abstraction
│   │   ├── base_adapter.py      # Abstract interface
│   │   └── manual_adapter.py    # Curated dataset source
│   │
│   └── data/
│       └── curated_jobs.json
│
├── alembic/                     # Database migrations
│   └── versions/
├── tests/
├── docs/
├── .env                         # Secrets — never committed
├── .gitignore
├── requirements.txt
└── README.md
```

---

# 9. TECHNOLOGY STACK — WHAT, HOW, AND WHY

| Technology | What it does | Why this choice |
|---|---|---|
| **Python 3.11+** | Core language | Best ecosystem for text processing, NLP, and AI integration. The parsing and matching libraries needed here are Python-native. |
| **FastAPI** | Web framework | Automatically generates interactive API documentation (Swagger UI) from the code itself, which means the project is demoable in a browser with zero frontend work. Type hints give free request validation. Modern and async-capable. |
| **Uvicorn** | ASGI server | The server that actually runs FastAPI. Standard pairing, minimal configuration. |
| **SQLAlchemy** | ORM | Lets the code talk to the database in Python objects rather than raw SQL. It also abstracts the database engine itself, so the same model code targets SQLite in development and PostgreSQL in production. |
| **Pydantic** | Data validation | Defines the exact shape of every request and response. Invalid data is rejected at the boundary with clear error messages rather than causing failures deep in the logic. |
| **SQLite → PostgreSQL** | Server-side database | Holds operational data only — the job catalogue, adapter state, and logs. Personal data is not intentionally persisted here. SQLite requires zero setup and is a single file — ideal for solo development. The SQLAlchemy abstraction minimizes database-specific application changes, while Alembic migrations and PostgreSQL compatibility must still be validated before production deployment. |
| **Alembic** | Database migrations | Versions schema changes as explicit, reviewable migration scripts rather than relying on table recreation. Necessary because the schema will evolve during development and because the development and production databases differ. |
| **IndexedDB** | Primary client-side storage | Holds all user data and large application data on the user's own device: profile, resume and extracted data, cached jobs, eligibility and matching results, application tracking, notes, chat history, and AI context. Chosen because it handles structured records and sizeable payloads, supports indexed queries, and is the standard browser store for anything beyond trivial values. |
| **localStorage** | Small preferences only | Used strictly for small settings and UI state. Not used for profile, resume, results, or any substantial user data — it is size-limited and synchronous, which makes it unsuitable for the primary store. |
| **pdfplumber** | PDF text extraction | More reliable layout handling than most alternatives, which matters because resumes are layout-heavy documents. |
| **python-docx** | DOCX text extraction | The standard library for Word documents. |
| **spaCy** | NLP fallback | Provides deterministic extraction of predictable fields (emails, phone numbers, dates) without an AI call. Used as a fallback and cost-saver. |
| **scikit-learn** | Similarity scoring | Provides TF-IDF vectorization and cosine similarity out of the box. No model training required, and the results are explainable — important, because every score must come with a reason. |
| **openpyxl** | Excel generation | Direct, well-documented Excel file creation. |
| **python-dotenv** | Configuration | Keeps API keys and database URLs out of source code and out of version control. |
| **httpx** | HTTP client | Async-capable, needed for calling AI provider APIs efficiently. |
| **pytest** | Testing | Standard Python testing framework. Tests are written alongside features, not at the end. |
| **Git + GitHub** | Version control | Commit history is itself portfolio evidence of consistent, incremental work. |
| **Render / Railway** | Deployment | Free tiers sufficient for this scale. Produces a live public URL. |

## 9.1 Why FastAPI specifically

Three reasons dominated this choice:

1. **Self-documenting.** FastAPI generates a complete interactive API explorer at `/docs` automatically. Anyone can open a browser and test every endpoint without writing a line of client code. For a backend-only portfolio project, this is enormously valuable — it makes an invisible system visible.
2. **Type-driven validation.** Python type hints double as validation rules. Less code, fewer bugs, clearer intent.
3. **Async-ready.** AI API calls are slow and I/O-bound. Async support means the system can handle concurrent requests properly without architectural changes later.

## 9.2 Why an AI provider abstraction

Rather than calling OpenAI directly throughout the codebase, all AI calls route through a single abstract interface with concrete provider implementations behind it.

**Benefits:**
- Switching providers (OpenAI, OpenRouter, Anthropic, or a local model) is a configuration change, not a refactor
- No vendor lock-in
- AI calls can be mocked in tests, so the test suite runs fast and free
- Cost and usage logging happens in one place

## 9.3 Why an adapter pattern for job sources

Every job source — a curated JSON file, a portal API, a scraper — implements the same interface and returns the same normalized shape.

**Benefits:**
- Adding a new source means writing one new class; nothing else changes
- Sources can be enabled or disabled independently
- The system is testable with a fake source
- The hardest unsolved problem (real data acquisition) is isolated behind a stable boundary

---

# 10. DATA DESIGN

Data is split across two locations. The schemas below are unchanged in shape; what changes is where each one lives.

| Data | Location | Store |
|---|---|---|
| Candidate profile | User's device | IndexedDB |
| Resume file and extracted data | User's device | IndexedDB |
| Eligibility and matching results | User's device | IndexedDB |
| Application tracking and status | User's device | IndexedDB |
| Notes, chat history, AI context | User's device | IndexedDB |
| Cached jobs for that user | User's device | IndexedDB |
| Preferences and UI state | User's device | localStorage |
| Job catalogue | Server | SQLite / PostgreSQL |
| Adapter and ingestion state | Server | SQLite / PostgreSQL |
| Operational logs | Server | SQLite / PostgreSQL |

---

## 10.1 Client-side stores (IndexedDB, on the user's device)

### Object store: `candidates`

| Field | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| name, email, phone, location | String | Contact details |
| education | JSON | List of `{degree, field, institution, grad_year, cgpa, scale}` — supports multiple degrees |
| experience | JSON | List of `{title, company, duration, description}` |
| skills | JSON | List of normalized skill strings |
| projects, certifications, languages | JSON | Supporting profile data |
| backlogs | Integer | Active backlog count |
| preferences | JSON | Location, job type, remote/onsite |
| resume_raw_text | Text | Retained for re-parsing and debugging |
| field_confidence | JSON | Per-field confidence from parsing |
| created_at, updated_at | DateTime | |

**Design note:** Education is a JSON list rather than flat columns because candidates may hold multiple qualifications, and different education systems use different grading scales. This keeps the profile universal rather than locked to one degree type or one country's system.

### Object store: `evaluations`

| Field | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| candidate_id, job_id | References | |
| eligibility_state | Enum | ELIGIBLE / LIKELY_ELIGIBLE / NEEDS_REVIEW / NOT_ELIGIBLE / UNKNOWN |
| requirement_breakdown | JSON | Per-requirement verdicts with reasons |
| match_score | Float | 0–100 |
| reason | Text | Human-readable summary |
| application_status | Enum | NOT_APPLIED / APPLIED / INTERVIEW / REJECTED / OFFER |
| evaluated_at | DateTime | |

Computed by the backend, returned to the client, and persisted on the device.

### Object store: `cached_jobs`

Jobs the user has retrieved, stored locally so previously seen results and their evaluations remain available on the device. Same field shape as the server-side `jobs` table below.

### Object store: `notes_and_context`

Notes, chat and conversation history, and AI memory and context, keyed by candidate.

### localStorage keys

Small preferences and UI state only — selected filters, sort order, display options, onboarding flags. Nothing substantial and nothing sensitive.

---

## 10.2 Server-side tables (operational data only)

### Table: `jobs`

| Field | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| company_name, role_title | String | |
| job_type | Enum | internship / full-time |
| description | Text | Original posting text |
| requirements | JSON | Structured eligibility criteria |
| min_cgpa | Float | |
| allowed_fields | JSON | Permitted degrees or branches |
| max_backlogs | Integer | |
| min_grad_year, max_grad_year | Integer | |
| required_skills | JSON | Used for match scoring |
| apply_link | String | |
| deadline | Date | Nullable |
| source | String | Which adapter supplied it |
| source_job_id | String | Original ID at the source |
| content_hash | String | Deduplication key — see note below |
| status | Enum | ACTIVE / EXPIRED / CLOSED / UNKNOWN |
| last_verified_at | DateTime | Freshness tracking |

**Deduplication note:** `content_hash` is computed over a **canonicalized** set of stable fields, not over raw posting text. Formatting differences between sources should not create duplicate jobs.

Canonicalization inputs:
- Normalized company name
- Normalized role title
- Normalized location
- Apply URL, when available
- Source job ID, when available
- Normalized description and requirements

Normalization means lowercasing, whitespace collapsing, and stripping punctuation and common suffixes before hashing. The implementation stays deliberately simple in Phase 1; `source` and `source_job_id` remain available as an exact-match fast path when a source provides stable IDs.

### Table: `ingestion_state`

Adapter run history, last-fetch timestamps, and deduplication hashes — required for ingestion to work correctly across runs.

### Operational logs

Request counts, AI usage and cost logging, and error records. Kept for system operation and diagnostics, not as a record of any individual's profile or applications.

**Note:** there is no server-side `candidates` table and no server-side store of evaluations by default. Those records live on the user's device.

---

# 11. API ENDPOINT REFERENCE

**All endpoints handling personal data are stateless.** The client sends the data an operation needs, the backend computes and returns a result, and the client persists that result in IndexedDB. No endpoint below creates a permanent server-side record of a candidate.

## Candidate profile operations (stateless)

These endpoints validate, normalize, and structure candidate data. They do not store profiles.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/candidates/validate` | Validate and normalize a candidate profile payload; returns the canonical profile shape plus any validation issues. The client generates `candidate_id` and persists the result. |
| POST | `/api/v1/candidates/normalize` | Normalize profile fields (skill canonicalization, grade-scale handling, field cleanup) and return the normalized profile to the client. |

**Note on the earlier design:** `GET` and `PATCH` on a candidate resource were removed because they implied a server-held record. Retrieval and update happen against IndexedDB on the client; the backend is called only when processing is needed.

## Resumes (stateless)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/resumes/parse` | Accept a resume file, extract and structure its contents, return the parsed profile with per-field confidence. The uploaded file exists only for the duration of processing and is deleted afterwards, whether processing succeeds or fails. The client persists both the file and the extracted data locally. |

## Jobs
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/jobs/ingest` | Run all adapters, normalize, deduplicate, store |
| GET | `/api/v1/jobs` | List jobs with filters |
| GET | `/api/v1/jobs/{id}` | Job detail |

## Eligibility and Matching
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/eligibility/check` | Evaluate a candidate profile (sent in the request body) against one or many jobs; returns verdicts for the client to persist |
| POST | `/api/v1/matching/score` | Score a single candidate-job pair from the supplied profile |
| POST | `/api/v1/recommendations` | Full ranked list for the supplied profile. `POST` rather than `GET` because the profile travels in the request body rather than being fetched from server storage. |

## Applications
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/applications/prepare` | Generate reviewable application package from the supplied profile and job |
| POST | `/api/v1/applications/export` | Generate an Excel tracker from tracking records supplied by the client and return the file |

**Application status tracking has no endpoint.** Status changes (`NOT_APPLIED` → `APPLIED` → `INTERVIEW` and so on) are written directly to IndexedDB by the client. The backend is not involved, because it holds no application records.

## Sample response — eligibility check

```json
{
  "candidate_id": "a3f2...",
  "job_id": "b7c1...",
  "company": "TechCorp",
  "role": "Software Engineering Intern",
  "eligibility_state": "ELIGIBLE",
  "match_score": 87,
  "requirement_breakdown": [
    {
      "requirement": "Minimum CGPA 7.5",
      "candidate_value": "8.2",
      "status": "PASS",
      "confidence": "high",
      "method": "deterministic"
    },
    {
      "requirement": "Computer Science or related field",
      "candidate_value": "Information Technology",
      "status": "PASS",
      "confidence": "medium",
      "method": "ai_reasoning",
      "note": "IT is generally accepted as a related field for this role type"
    },
    {
      "requirement": "Graduating 2026–2027",
      "candidate_value": "2027",
      "status": "PASS",
      "confidence": "high",
      "method": "deterministic"
    }
  ],
  "summary": "Eligible. Meets all hard requirements. 5 of 6 preferred skills matched.",
  "apply_link": "https://...",
  "deadline": "2026-11-15"
}
```

---

# 12. CORE ALGORITHMS EXPLAINED

## 12.1 Eligibility evaluation — hard rules before AI

The engine evaluates in two ordered stages.

**Stage 1 — Deterministic checks.** Anything numerically or categorically comparable is evaluated in plain code: CGPA against cutoff, graduation year against range, backlog count against limit, degree level against requirement. These are fast, free, perfectly consistent, and fully explainable.

**Stage 2 — AI reasoning, only where genuinely needed.** Some requirements are linguistically ambiguous. "Computer Science or a related field" requires judgment about whether Information Technology, Electronics, or Data Science qualifies. Only these cases invoke an AI call, and the result carries a confidence level and is marked as AI-reasoned in the output.

### Hard-rule precedence

**Deterministic hard constraints have final authority.**

If a candidate fails a verified hard requirement — minimum CGPA, graduation year window, maximum backlogs, required degree level — AI reasoning **must not** override that failure. AI is permitted to reason only about genuinely ambiguous requirements that deterministic rules cannot resolve.

### Evaluation order

1. Parse and normalize the requirement
2. Evaluate deterministic hard constraints
3. **If a verified hard constraint fails → `NOT_ELIGIBLE`. Evaluation stops; AI is not consulted for that requirement.**
4. If deterministic rules pass but ambiguity remains → AI reasoning
5. Produce the final eligibility state with confidence and explanation

A hard constraint counts as *verified* only when the required data is present and valid. Missing or unparseable data produces `UNKNOWN` or `NEEDS_REVIEW` for that requirement rather than a failure — absence of evidence is not evidence of ineligibility.

### Confidence semantics

Confidence describes **how much the system trusts its own determination**. It is not a measure of eligibility.

| Level | Meaning |
|---|---|
| **HIGH** | Strong evidence or deterministic evaluation. The system has sufficient reliable information to make the determination with high confidence. |
| **MEDIUM** | Reasonable evidence exists, but interpretation or incomplete information introduces meaningful uncertainty. |
| **LOW** | Insufficient, ambiguous, conflicting, or weak evidence. The result should be treated as uncertain and may warrant user review. |

**Confidence and eligibility are independent.** A deterministic hard failure is a HIGH confidence `NOT_ELIGIBLE`. An AI interpretation of "or related field" may be a MEDIUM confidence `ELIGIBLE`. High confidence does not mean good news, and low confidence does not mean rejection.

**Why this ordering matters:** Spending an AI call to compare two numbers is wasteful, slow, and less reliable than a comparison operator. Reserving AI for genuine ambiguity keeps the system fast, cheap, and predictable, while still handling the messy real-world cases that pure rules cannot.

## 12.2 Match scoring

1. **Skill normalization.** Variants map to canonical forms: "ReactJS", "React.js", and "React" all become "React". Without this step, scoring is dominated by naming noise rather than actual overlap.
2. **Vectorization.** Candidate skills and experience text and job requirement text are converted to TF-IDF vectors, which weight terms by how distinctive they are.
3. **Similarity.** Cosine similarity produces a 0–100 score.
4. **Ranking.** Eligible jobs are ranked by score. Borderline jobs appear in a separate flagged group. Ineligible jobs are excluded from ranking but remain retrievable with their rejection reason.

**Why TF-IDF rather than embeddings or a trained model:** It requires no training data, runs locally with no API cost, is fast, and — most importantly — is explainable. The system can state which specific terms drove a score. For a tool whose entire value proposition is transparency, an unexplainable score would be self-defeating. Embeddings remain a viable upgrade path later.

## 12.3 Truthfulness validation

Any AI-generated application content is checked claim by claim against the stored candidate profile. A claim about a skill, project, duration, or achievement must be traceable to actual profile data. Untraceable claims are flagged or removed before the content is returned.

**Why this exists:** Language models will confidently invent plausible experience. In a job application context, that is not a minor bug — it produces content that could misrepresent a real person to a real employer. Validation is treated as a required component, not an optional safeguard.

---

# 13. DESIGN PRINCIPLES

These were fixed before development and are not revisited mid-build.

**1. Universal by default.** The candidate profile supports any degree, field, and grading system. Narrowing later is easy; widening a hard-coded schema is a rewrite.

**2. Everything pluggable.** Job sources and AI providers sit behind abstract interfaces. New sources and providers are additions, never modifications.

**3. Deterministic before probabilistic.** Rules run first, and they have final authority. A verified hard-constraint failure is never overridden by AI reasoning. AI handles only what rules genuinely cannot resolve.

**4. Explainability is mandatory.** Every verdict, score, and recommendation carries a human-readable reason. An unexplained answer is treated as a failure, not a result.

**5. Human decides.** The system informs and prepares. It never submits.

**6. Truth over fluency.** Generated content that cannot be traced to real data does not ship.

**7. Ship the core, then extend.** A complete, tested, documented core beats a broad, half-finished system.

---

# 14. COMPETITIVE LANDSCAPE

### Existing tools

Some mature open-source tools in this space — the most prominent being a widely-adopted CLI-based job search system — focus on deep, one-job-at-a-time fit analysis for experienced professionals. They evaluate a single posting thoroughly against a CV, generate tailored resumes and cover letters, and track applications, typically running inside an AI coding CLI.

Notably, some such tools have independently reached the same conclusion this project did: they explicitly refuse to auto-submit applications, positioning themselves as filters rather than bulk appliers. This is meaningful external validation of the core design decision.

### How EligiCore differs

| Dimension | The comparable tools surveyed | EligiCore |
|---|---|---|
| Core question | "How well do I fit this role?" | "Am I eligible for these roles, and why?" |
| Hard eligibility gates | Not a primary focus | The central feature |
| Target user | Experienced professionals | Students and early-career candidates |
| Interface | CLI-embedded | REST API consumable by any client |
| Data layer | Files (Markdown, YAML) | Local-first: IndexedDB on the user's device for personal data, relational database server-side for the job catalogue |
| Breadth | Deep on one job at a time | Broad across many jobs simultaneously |

### The gap being filled

The tools surveyed evaluate *fit* — a soft, judgment-based question. They do not systematically evaluate *eligibility* — the hard, rule-based gates that dominate student and campus recruitment. For a candidate weighing a senior role, fit is the binding constraint. For a student facing a CGPA cutoff and a branch restriction, eligibility is. That is a different problem, and among the tools surveyed it appears underserved. This survey is limited and informal; the comparison should be read as positioning rather than an exhaustive market analysis.

---

# 15. DEVELOPMENT ROADMAP

**Total: 10 weeks solo, 10–15 hours per week.**

| Week | Focus | Deliverable |
|---|---|---|
| 1 | Foundation and candidate profile schema | Running API, operational database connected, profile schema and validation working |
| 2 | Resume parser and AI service layer | Resume → structured, confidence-scored profile |
| 3 | Job schema, adapters, ingestion | 30–50 curated jobs in database via adapter pattern |
| 4 | Eligibility engine | Explainable verdicts with requirement breakdowns |
| 5 | Matching engine | Ranked, explained recommendations |
| 6 | **Polish, Excel export, testing** | **Complete, demoable product — safe stopping point** |
| 7 | Application preparation | Reviewable application packages |
| 8 | Refinement, caching, cost logging | Polished, cost-aware system |
| 9 | Documentation and deployment | Live public API with full documentation |
| 10 | Buffer | Slippage absorption and final polish |

**Week 6 is a deliberate checkpoint.** At that point the system is complete and demonstrable. Everything after is enhancement.

---

# 16. RISKS AND MITIGATIONS

| Risk | Severity | Mitigation |
|---|---|---|
| Job data acquisition at scale is legally and technically hard | High | Phase 1 uses manually curated data. The adapter boundary isolates this problem so it can be solved independently without touching the rest of the system. |
| Resume parsing accuracy varies with format | Medium | Confidence scoring surfaces uncertainty rather than hiding it; candidates correct flagged fields. Deterministic fallbacks handle predictable fields. |
| AI API costs accumulate | Medium | Rules run before AI; results are cached; usage is logged. AI is called only for genuine ambiguity. |
| Eligibility false positives or negatives | Medium | Full reasoning is exposed for every verdict, so candidates can evaluate the system's judgment rather than trusting it blindly. Borderline cases are explicitly flagged rather than forced into a binary. |
| Scope creep derailing a solo build | High | Feature set fixed in advance. Week 6 checkpoint defined. Automation and frontend explicitly deferred. |
| Loss of momentum mid-project | High | Weekly deliverables, frequent commits, and a working system by Week 6 rather than only at the end. |

---

# 17. SUCCESS CRITERIA

**Functional**
- Resume upload extracts 80%+ of fields accurately on well-formatted resumes
- Every eligibility verdict carries a per-requirement breakdown and a human-readable reason; verdicts match expected results across the maintained test set
- Hard-constraint evaluation achieves 100% accuracy on the maintained deterministic test suite, which explicitly covers CGPA cutoffs, graduation year windows, backlog limits, degree requirements, boundary values, missing values, and invalid values
- No AI-reasoned verdict overrides a verified deterministic hard-constraint failure
- Recommendations rank sensibly across distinct candidate profiles
- Excel export is clean and usable
- Generated application content passes truthfulness validation on the maintained test set, with no claim traceable to data absent from the profile

**Engineering**
- Layered architecture with business logic independent of framework and provider
- New job source addable by writing one class
- AI provider swappable via configuration, verified by running the test suite against a mock provider
- Integration tests covering the full flow
- Clean, incremental commit history

**Portfolio**
- Live, publicly accessible deployed API
- Documentation allowing a stranger to understand and run the project in under 10 minutes
- Interactive API documentation demonstrating every endpoint
- Architecture decisions documented and defensible in discussion

---

# 18. FUTURE PHASES

**Phase 2 — Frontend.** A web dashboard consuming the existing API without modification. Possibly a browser extension that autofills application forms within the candidate's own session, preserving the no-auto-submit constraint.

**Phase 3 — Live job sources.** Real adapters for portals and ATS platforms, built within Terms of Service constraints. The adapter interface already accommodates this.

**Phase 4 — Multi-user platform.** Authentication, per-user isolation, notification digests, deadline reminders.

**Phase 5 — Institutional features.** Cohort-level evaluation for placement cells: check an entire batch against a set of openings at once.

---

# 19. GLOSSARY

**API (Application Programming Interface)** — A structured way for software to communicate. Here, the system exposes functionality that any application can call, rather than a website humans browse.

**REST** — A conventional style for structuring web APIs around resources and standard HTTP methods.

**Endpoint** — A single callable address in the API, such as `/api/v1/eligibility/check`.

**ORM (Object-Relational Mapper)** — A layer letting code interact with a database using objects instead of raw SQL.

**Adapter pattern** — A design pattern where different external sources are wrapped in a common interface, so the rest of the system treats them identically.

**Provider abstraction** — The same idea applied to services (here, AI providers), allowing substitution without code changes.

**TF-IDF** — A technique that weights terms by how distinctive they are within a document set, used here for skill and requirement similarity.

**Cosine similarity** — A measure of how closely two vectors align, producing the match score.

**Deterministic** — Producing the same output for the same input every time, with no randomness. Contrasted with AI-generated output.

**Swagger UI** — Interactive API documentation generated automatically by FastAPI, letting anyone test endpoints in a browser.

**IndexedDB** — A storage system built into browsers for keeping structured data on the user's own device. Suitable for large records and supports indexed lookups. Used here as the primary store for all personal data.

**localStorage** — A simpler browser storage mechanism for small values. Size-limited and synchronous, so it is used here only for preferences and interface state.

**Local-first** — An architecture where the user's data lives primarily on their own device rather than on a server, with the server used for processing rather than permanent personal storage.

**ATS (Applicant Tracking System)** — Software companies use to manage job applications.

---

*End of dossier.*
