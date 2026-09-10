# Architecture — EligiCore

> **Derived from:** dossier §§8, 10, 11, 12. The dossier is authoritative.
> **This file records the approved architecture and its invariants.** Changing anything here
> requires an ADR and human approval — see `context/workflow.md` § Architectural change.

---

## 1. Layered structure

```
┌────────────────────────────────────────────────────────┐
│  API LAYER          app/routers/                        │
│  HTTP endpoints, request validation, response shaping.  │
│  NO business logic.                                     │
└──────────────────────┬─────────────────────────────────┘
                       ▼
┌────────────────────────────────────────────────────────┐
│  SERVICE LAYER      app/services/                       │
│  All business logic: parsing, eligibility, matching,    │
│  application prep, truthfulness validation.             │
│  Framework-agnostic. Independently testable without     │
│  starting a server.                                     │
└────────┬───────────────────────────────┬───────────────┘
         ▼                               ▼
┌──────────────────────┐    ┌────────────────────────────┐
│  AI LAYER  app/ai/   │    │  ADAPTER LAYER             │
│  Provider-agnostic   │    │  app/adapters/             │
│  interface, concrete │    │  Source-agnostic job       │
│  providers, mock     │    │  ingestion                 │
└────────┬─────────────┘    └───────────┬────────────────┘
         ▼                              ▼
┌────────────────────────────────────────────────────────┐
│  SERVER DATA LAYER   app/models/ + app/database.py      │
│  SQLAlchemy ORM, sessions.                              │
│  OPERATIONAL DATA ONLY: job catalogue, ingestion state, │
│  operational logs. Personal data is not persisted here. │
└────────────────────────────────────────────────────────┘

                ═══ device boundary ═══

┌────────────────────────────────────────────────────────┐
│  CLIENT DATA LAYER   (on the user's device, Phase 2)    │
│  IndexedDB    — profile, resume + extracted data,       │
│                 cached jobs, evaluations, matches,      │
│                 tracking, notes, chat history, AI ctx   │
│  localStorage — small preferences and UI state only     │
└────────────────────────────────────────────────────────┘
```

**Why layered:** business logic stays independent of both the web framework and the AI
provider. The matching engine is testable without a server; the AI provider is swappable
without touching business logic.

**Dependency direction is one-way and downward.** Services never import from routers. The AI
and adapter layers never import from services.

---

## 2. Data ownership — the device boundary

This is the single most important architectural property of EligiCore, and the easiest one to
erode accidentally.

### Lives on the user's device (IndexedDB)

Candidate profile · resume file and extracted data · preferences · jobs cached for that user ·
eligibility results · matching results · application tracking and status · notes · chat and
conversation history · AI memory and context.

### Lives on the server (SQLite → PostgreSQL)

Job catalogue (`jobs`) · adapter and ingestion state (`ingestion_state`) · operational logs.
**Nothing else.**

### Passes through the server but is not retained

Candidate profiles, resume files, and generated content. The client sends what an operation
needs; the backend computes and returns; the client persists locally.

### What "not persisted" means precisely

Personal data is not *intentionally* persisted by the application as part of normal operation.
Request handling, temporary processing storage, infrastructure logs and error telemetry are
designed and configured to avoid retaining unnecessary personal data. This is a design
commitment about how the application is built and configured — not an absolute guarantee about
every layer of underlying infrastructure.

### `candidate_id` semantics

A **client-generated stable identifier** used to correlate operations and results across
requests. It is *not* a pointer to a server-side record. The client generates it, owns it, and
stores it alongside the profile.

### Resume lifecycle

May exist temporarily in backend memory or temp storage during processing, is deleted after
processing completes **whether it succeeds or fails**, is never persisted as a permanent user
record, and the extracted data is returned to the client which persists it locally.

> **Phase 1 has no frontend.** IndexedDB does not exist yet. This does *not* license
> server-side persistence "just for now." Phase 1 endpoints are stateless with respect to
> personal data; tests supply profiles in request bodies exactly as a client would.

---

## 3. API surface (dossier §11)

All personal-data endpoints are **stateless**. No endpoint creates a permanent server-side
candidate record.

| Method | Path | Personal data |
|---|---|---|
| POST | `/api/v1/candidates/validate` | in body, not retained |
| POST | `/api/v1/candidates/normalize` | in body, not retained |
| POST | `/api/v1/resumes/parse` | file, deleted after processing |
| POST | `/api/v1/jobs/ingest` | none |
| GET | `/api/v1/jobs` | none |
| GET | `/api/v1/jobs/{id}` | none |
| POST | `/api/v1/eligibility/check` | profile in body, not retained |
| POST | `/api/v1/matching/score` | profile in body, not retained |
| POST | `/api/v1/recommendations` | profile in body, not retained |
| POST | `/api/v1/applications/prepare` | profile in body, not retained |
| POST | `/api/v1/applications/export` | tracking records in body, not retained |

**Deliberate absences, each load-bearing:**

- No `GET`/`PATCH` on a candidate resource — they would imply a server-held record.
- No application-status endpoint — status transitions are written to IndexedDB by the client.
- `/recommendations` is `POST`, not `GET`, because the profile travels in the body.

---

## 4. Eligibility architecture (dossier §12.1)

Two ordered stages. The order *is* the architecture.

```
1. Parse and normalize the requirement
2. Evaluate deterministic hard constraints
3. If a VERIFIED hard constraint fails → NOT_ELIGIBLE.
   Evaluation stops. AI is NOT consulted for that requirement.
4. If deterministic rules pass but ambiguity remains → AI reasoning
5. Produce final state with confidence and explanation
```

**Verified** means the required data is present and valid. Missing or unparseable data yields
`UNKNOWN` or `NEEDS_REVIEW` for that requirement — **never a failure**. Absence of evidence is
not evidence of ineligibility.

**States:** `ELIGIBLE` · `LIKELY_ELIGIBLE` · `NEEDS_REVIEW` · `NOT_ELIGIBLE` · `UNKNOWN`

**Confidence is orthogonal to eligibility.** It measures how much the system trusts its own
determination, not how good the news is. A deterministic hard failure is a HIGH-confidence
`NOT_ELIGIBLE`. An AI reading of "or related field" may be a MEDIUM-confidence `ELIGIBLE`.

**Every verdict carries a per-requirement breakdown** with `requirement`, `candidate_value`,
`status`, `confidence`, `method` (`deterministic` | `ai_reasoning`), and an optional `note`.
The `method` field is not cosmetic — it is how a reader knows which stage produced a verdict.

---

## 5. Matching architecture (dossier §12.2)

1. **Skill normalization** — "ReactJS" / "React.js" / "React" all become `React`. Without this,
   scoring is dominated by naming noise rather than real overlap.
2. **Vectorization** — TF-IDF over candidate skills/experience text and job requirement text.
3. **Similarity** — cosine similarity produces 0–100.
4. **Ranking** — eligible jobs ranked by score; borderline jobs in a separate flagged group;
   ineligible jobs excluded from ranking but retrievable with their rejection reason.

TF-IDF rather than embeddings because it needs no training data, costs nothing, runs locally,
and — decisively — is explainable. The system can state which terms drove a score. For a tool
whose value proposition is transparency, an unexplainable score is self-defeating. Embeddings
remain a viable upgrade path.

---

## 6. AI architecture (dossier §9.2)

All AI calls route through one abstract interface (`app/ai/providers/base.py`) with concrete
providers behind it. Prompts live as files under `app/ai/prompts/`, not as inline strings.

**Consequences that must hold:** swapping provider is a config change, not a refactor; no
vendor lock-in; AI is mockable so the suite runs fast and free; cost and usage logging happens
in exactly one place.

AI is called **only** where deterministic code genuinely cannot resolve the question. Spending
an AI call to compare two numbers is slower, costlier, and less reliable than `>=`.

**Phase 1 default provider: Google Gemini Flash** (ADR-013), reached through the official REST
API via httpx rather than a vendor SDK. It is the concrete implementation, not a dependency —
`app/ai/providers/gemini.py` is the only file in the codebase that knows Gemini exists. The
runtime default is `mock`, so an unconfigured checkout cannot make a paid call.

As built:

```
services  ->  ai_service  ->  AIProvider (abstract)  ->  MockAIProvider
                                                     \-> GeminiFlashProvider
```

Provider failures are translated into `app/ai/errors.py` types at the provider boundary, so no
service or router ever sees an httpx or vendor exception.

---

## 7. Job architecture (dossier §9.3, §10.2)

Every source — curated JSON, portal API, future scraper — implements the same interface and
returns the same normalized shape. Adding a source is one new class; nothing else changes.

**Deduplication** uses `content_hash` computed over a *canonicalized* set of stable fields, not
raw posting text: normalized company name, role title, location, apply URL, source job ID,
normalized description and requirements. Normalization means lowercasing, collapsing
whitespace, and stripping punctuation and common suffixes. `source` plus `source_job_id`
remain an exact-match fast path where a source provides stable IDs. Formatting differences
between sources must not create duplicate jobs.

**Freshness** is tracked via `status` (ACTIVE / EXPIRED / CLOSED / UNKNOWN) and
`last_verified_at`.

---

## 8. Application architecture (dossier §12.3, §6)

Preparation generates a **reviewable package** — tailored cover letter and answers. Every
generated claim about a skill, project, duration or achievement is checked against the actual
candidate profile supplied in the request. Untraceable claims are flagged or removed **before
the content is returned**.

Truthfulness validation is a required component, not an optional safeguard. Language models
confidently invent plausible experience; in a job-application context that misrepresents a real
person to a real employer.

Auto-submit is out of scope — see `ADR-008`.

---

## 9. Architectural invariants

**Future sessions must never violate these.** A change that breaks one is a defect even if
every test passes. Breaking one deliberately requires a new ADR and human approval.

| # | Invariant |
|---|---|
| **INV-1** | No server-side persistence of candidate personal data — no `candidates` table, no `evaluations` table, no stored resumes, no application records. **Ruled explicitly in [ADR-011](../artifacts/decisions/ADR-011-no-server-side-candidate-or-application-persistence.md); the dossier §8.2 listing that suggests otherwise is stale.** |
| **INV-2** | A verified deterministic hard-constraint failure is never overridden by AI reasoning. |
| **INV-3** | Missing or invalid data yields `UNKNOWN`/`NEEDS_REVIEW`, never an automatic `NOT_ELIGIBLE`. |
| **INV-4** | Resume contents, candidate payloads, PII, and generated PII-bearing content are never logged — including via stack traces and captured request bodies. |
| **INV-5** | Business logic never imports a vendor AI SDK. All AI access goes through `app/ai/providers/base.py`. |
| **INV-6** | A new job source is one new adapter class. It never requires changes to the eligibility or matching engines. |
| **INV-7** | Routers contain no business logic. Services are importable and testable without FastAPI. |
| **INV-8** | Every eligibility verdict carries a per-requirement breakdown and a human-readable reason. |
| **INV-9** | Generated application content contains no claim untraceable to supplied profile data. |
| **INV-10** | No auto-submit, no browser automation, no CAPTCHA/OTP/anti-bot circumvention, no identity-verification bypass. |
| **INV-11** | Temporary resume files are deleted after processing, on both the success and failure paths. |
| **INV-12** | All endpoints live under `/api/v1/`. |

---

## 10. Folder structure

```
eligicore/
├── app/
│   ├── main.py                  # FastAPI entrypoint
│   ├── config.py                # Environment configuration
│   ├── database.py              # DB engine, session, base
│   ├── models/                  # SQLAlchemy — OPERATIONAL DATA ONLY
│   │   ├── job.py
│   │   └── ingestion_state.py
│   ├── schemas/                 # Pydantic request/response shapes
│   │   ├── candidate.py
│   │   ├── job.py
│   │   └── eligibility.py
│   ├── routers/                 # HTTP endpoints
│   │   ├── candidates.py   resumes.py    jobs.py
│   │   └── eligibility.py  matching.py   applications.py
│   ├── services/                # Business logic
│   │   ├── resume_parser.py     eligibility_engine.py
│   │   ├── matching_engine.py   application_prep.py
│   │   └── truthfulness_validator.py
│   ├── ai/
│   │   ├── ai_service.py
│   │   ├── prompts/             # Prompts as files, not inline strings
│   │   └── providers/           # base.py + concrete providers + mock
│   ├── adapters/
│   │   ├── base_adapter.py
│   │   └── manual_adapter.py
│   └── data/curated_jobs.json
├── alembic/versions/
├── tests/
├── docs/
├── .env                         # never committed
├── .gitignore
├── requirements.txt
└── README.md
```

### Note on `app/models/` — RULED, do not reopen

The dossier's §8.2 listing includes `candidate.py` and `application.py`. Those contradict §10.2
("there is no server-side `candidates` table and no server-side store of evaluations by
default"). This was contradiction **C-1**, and it has been **ruled**:

> **§8.2's model listing is stale. The local-first architecture has authority.**
> `app/models/candidate.py` and `app/models/application.py` **must not exist**, nor any
> `candidates`, `applications` or `evaluations` table, nor any migration creating one.
> Full ruling: [ADR-011](../artifacts/decisions/ADR-011-no-server-side-candidate-or-application-persistence.md).

Pydantic schemas under `app/schemas/` are unaffected and are required — **schemas describe data
in flight, models describe data at rest.** EligiCore has candidate data in flight and never at
rest on the server.

`app/models/ingestion_state.py` **is** correct and is listed above. §8.2 omitted it; §10.2
requires it. This was contradiction **C-2**, ruled: ingestion is server-side operational
functionality, so its state is legitimately server-side operational data — bounded to adapter
identity, run history, timestamps, outcome counts and status, and never holding a
`candidate_id` or any personal data. Full ruling:
[ADR-012](../artifacts/decisions/ADR-012-ingestion-state-operational-model.md).

*(It is not yet implemented — that is Week 3 work.)*
