# Technology Stack — EligiCore

> **Derived from:** dossier §9. Approved and fixed.
> **Rule:** technologies are not replaced without an ADR and human approval. "I prefer X" is
> not a justification. Nor is "X is more modern."

---

## Core runtime

| Technology | What it does | Why this choice |
|---|---|---|
| **Python 3.11+** | Core language | Best ecosystem for text processing, NLP and AI integration. The parsing and matching libraries required here are Python-native. *(Local env: 3.12.10.)* |
| **FastAPI** | Web framework | Generates interactive Swagger docs from the code itself, so a backend-only project is demoable in a browser with zero frontend work. Type hints double as request validation. Async-capable. |
| **Uvicorn** | ASGI server | The server that actually runs FastAPI. Standard pairing, minimal configuration. |
| **Pydantic** | Data validation | Defines the exact shape of every request and response. Invalid data is rejected at the boundary with clear errors rather than failing deep in the logic. |

### Why FastAPI specifically

1. **Self-documenting.** `/docs` gives a complete interactive API explorer. For a backend-only
   portfolio project this is decisive — it makes an invisible system visible.
2. **Type-driven validation.** Type hints *are* the validation rules. Less code, fewer bugs.
3. **Async-ready.** AI calls are slow and I/O-bound. Async support means concurrency is handled
   without an architectural change later.

---

## Server-side data

| Technology | What it does | Why this choice |
|---|---|---|
| **SQLAlchemy** | ORM | Database access in Python objects rather than raw SQL, and it abstracts the engine — the same model code targets SQLite in development and PostgreSQL in production. |
| **SQLite → PostgreSQL** | Operational database | Holds **operational data only**: job catalogue, adapter state, logs. SQLite needs zero setup and is a single file — ideal for solo development. ⚠️ SQLAlchemy minimizes but does not eliminate engine differences; **Alembic migrations and PostgreSQL compatibility must be validated before production deployment, not assumed.** |
| **Alembic** | Migrations | Versions schema changes as explicit reviewable scripts rather than relying on table recreation. Necessary because the schema will evolve and because dev and prod engines differ. |

---

## Client-side data (Phase 2 — no frontend exists in Phase 1)

| Technology | What it does | Why this choice |
|---|---|---|
| **IndexedDB** | Primary client store | Holds *all* user data on the user's device: profile, resume and extracted data, cached jobs, eligibility and matching results, tracking, notes, chat history, AI context. Handles structured records and sizeable payloads, supports indexed queries. |
| **localStorage** | Small preferences only | Strictly settings and UI state. **Not** used for profile, resume, results or any substantial user data — it is size-limited and synchronous, which makes it unsuitable as a primary store. |

---

## Processing libraries

| Technology | What it does | Why this choice |
|---|---|---|
| **pdfplumber** | PDF text extraction | More reliable layout handling than most alternatives, which matters because resumes are layout-heavy documents. |
| **python-docx** | DOCX text extraction | The standard library for Word documents. |
| **spaCy** | NLP fallback | Deterministic extraction of predictable fields (emails, phone numbers, dates) with no AI call. A fallback and a cost-saver — consistent with "deterministic before probabilistic." |
| **scikit-learn** | Similarity scoring | TF-IDF vectorization and cosine similarity out of the box. No model training, and the results are **explainable** — essential, because every score must come with a reason. |
| **openpyxl** | Excel generation | Direct, well-documented Excel file creation for the tracker export. |

---

## Integration and operations

| Technology | What it does | Why this choice |
|---|---|---|
| **httpx** | HTTP client | Async-capable, needed for calling AI provider APIs efficiently alongside FastAPI's async model. |
| **python-dotenv** | Configuration | Keeps API keys and database URLs out of source code and out of version control. |
| **pytest** | Testing | Standard Python testing framework. Tests are written alongside features, not at the end. |
| **Git + GitHub** | Version control | The commit history is itself portfolio evidence of consistent incremental work. ⚠️ **Not yet initialized — see `context/state.md` Blocker 1.** |
| **Render / Railway** | Deployment | Free tiers sufficient for this scale. Produces a live public URL, which is a stated success criterion. |

---

## AI providers

The dossier names OpenAI, OpenRouter, Anthropic and local models as interchangeable behind the
provider abstraction (§9.2), while the §8.2 folder listing shows only `openai_provider.py`.

**Which provider is the Phase 1 default is an open decision** — tracked as contradiction C-4 in
`context/state.md` and as a deferred decision in `ADR-004`. It must be settled before Week 2.

Whatever is chosen, the abstraction is what matters: a **mock provider is mandatory** so the
test suite runs fast and free, and swapping the real provider stays a configuration change.

---

## Not in the stack, deliberately

No Celery or message broker. No Redis. No Docker orchestration or Kubernetes. No microservices.
No vector database. No embeddings model. No auth provider. No frontend framework. No browser
automation library.

Each of these has been considered and excluded for Phase 1. Introducing any of them requires an
ADR justifying why the simpler approach failed — not merely that the tool exists.
