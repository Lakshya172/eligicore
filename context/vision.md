# Vision — EligiCore

> **Derived from:** `EligiCore_Dossier_update.md` §§1–6, 13, 18. The dossier is authoritative.
> **Update when:** the dossier changes. Not otherwise.

---

## One line

An eligibility-first job application intelligence API: it determines which jobs and internships
a candidate is *genuinely eligible for* — and explains exactly why.

## The problem

Job hunting has three distinct problems. Candidates face all three; tools address one.

| # | Problem | Who solves it today |
|---|---|---|
| 1 | **Discovery** — openings scattered across dozens of portals | Aggregators, partially |
| 2 | **Eligibility** — "am I even allowed to apply?" | **Almost nobody** |
| 3 | **Volume** — can't fill out enough forms | Most tools, aggressively |

Problem 2 is the gap. Every posting carries hard gates — minimum CGPA, permitted branches,
graduation-year windows, backlog limits, work authorization. Checking these by hand across
hundreds of listings is exhausting and error-prone. Candidates burn hours on roles they were
never eligible for, and skip roles they *were* eligible for out of uncertainty.

## The solution

A backend REST API. The candidate uploads a resume once; the system extracts a profile,
compares it against the job catalogue, applies deterministic hard rules first and AI reasoning
only for genuine ambiguity, and returns a ranked, explained list — plus a tracking spreadsheet.

Framed as a person: a knowledgeable senior who has read every posting for you and says *"You
qualify for these fourteen, here's why for each. These three you're borderline on. These you
don't qualify for, and here's the specific reason."* Then hands you a spreadsheet. They do not
apply on your behalf.

## Target user

- **Primary:** students and recent graduates chasing internships and entry-level roles, where
  hard eligibility criteria are strictly enforced and are the main source of confusion.
- **Secondary:** placement cells and career services, checking a whole cohort at once.
- **Explicitly not:** senior professionals. At that level eligibility gates barely exist and
  fit dominates. That is a different product and it already exists.

## Value proposition

Not "apply to more jobs faster." It is **"stop wasting applications, and know why."**
Transparency is the product. An unexplained verdict is a failure, not a result.

## What it deliberately does NOT do

| Not done | Why |
|---|---|
| Auto-submit applications | ToS violations, account bans, brittle automation, and an application in your name should be one you saw. |
| Scrape live portals in Phase 1 | The hardest legal/technical problem is isolated behind the adapter boundary so everything downstream can be built and validated first. |
| Ship a frontend in Phase 1 | API-first by design. Frontend is Phase 2, consuming the same API unmodified. |
| Fabricate anything | Generated content is validated claim-by-claim against real profile data. |

These are design decisions, not missing features. They do not get revisited mid-build.

## Design principles

1. **Universal by default.** Any degree, field, grading system. Narrowing later is easy; widening a hard-coded schema is a rewrite.
2. **Everything pluggable.** Job sources and AI providers sit behind abstract interfaces. New ones are additions, never modifications.
3. **Deterministic before probabilistic.** Rules run first and have final authority.
4. **Explainability is mandatory.** Every verdict, score, and recommendation carries a reason.
5. **Human decides.** The system informs and prepares. It never submits.
6. **Truth over fluency.** Content that cannot be traced to real data does not ship.
7. **Ship the core, then extend.** A complete tested core beats a broad half-finished system.

## Long-term direction

| Phase | Content |
|---|---|
| **1 (current)** | Backend API: resume → profile → jobs → eligibility → matching → export |
| 2 | Frontend dashboard; possibly a browser extension that autofills *within the user's own session* (still no auto-submit) |
| 3 | Live job-source adapters for portals and ATS platforms, within ToS |
| 4 | Multi-user platform: auth, per-user isolation, digests, deadline reminders |
| 5 | Institutional: cohort-level evaluation for placement cells |

Phase 4 is the first phase that would revisit the local-first personal-data decision
(`ADR-001`). Until then, that decision holds.

## Success criteria (abridged — full list in dossier §17)

- 100% accuracy on the maintained deterministic hard-constraint test suite, including boundary, missing, and invalid values
- No AI-reasoned verdict ever overrides a verified deterministic hard failure
- Every verdict carries a per-requirement breakdown and human-readable reason
- A new job source is addable by writing one class
- AI provider swappable by configuration, verified by running the suite against a mock
- A stranger can understand and run the project in under 10 minutes
