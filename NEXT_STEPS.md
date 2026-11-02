# EligiCore — one-week freeze handoff

**Freeze:** 2026-11-03 to 2026-11-10. No implementation work during the freeze.
**State at handoff (verified 2026-11-02):** `main` is `1df4c48`, the PR #83 merge, with post-merge CI
run [41450933519](https://github.com/Lakshya172/eligicore/actions/runs/41450933519) green. Backend:
3030 passed, 1 warning. Frontend: 41 passed. A presentation-only polish is open as PR #84.

EligiCore is a **local, demonstrable** product. It is not deployed and not production-ready.

---

## What you are demonstrating

- **The student web app** in `frontend/`, over the existing FastAPI backend, with no backend change.
- **A synthetic catalogue.** The 40 opportunities come from EligiCore's curated synthetic dataset:
  fictional "Example …" and "Sample …" employers, with placeholder `example.com` links. It is not a
  live job feed and does not cover real employers.
- **A fictional sample student.** "Use sample profile" loads an invented student. Evaluations of it
  are real API results for a fictional person, and the UI labels them as such.
- **Offline résumé parsing.** It uses the mock provider's pattern matching. No live AI provider is
  needed, and none is called.
- **Local only.** Nothing is deployed and no external service is contacted.

## Start the demo

Use a **separate demo database**. Never point these commands at a database that matters to you.

### Backend, from the repository root

Windows PowerShell:

```powershell
$env:ELIGICORE_DATABASE_URL="sqlite:///./demo.db"
alembic upgrade head
python -m app.cli seed-catalogue
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

macOS or Linux:

```bash
export ELIGICORE_DATABASE_URL=sqlite:///./demo.db
alembic upgrade head
python -m app.cli seed-catalogue
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`seed-catalogue` loads the 40 synthetic postings and is safe to re-run; it reports every job
unchanged the second time. Run it before every demo on a new database.

### Frontend, in a second terminal

```bash
cd frontend
npm install
npm run dev
```

| URL | What it is |
|---|---|
| `http://127.0.0.1:5173` | The student web app |
| `http://127.0.0.1:8000/docs` | The API's interactive documentation |
| `http://127.0.0.1:8000/api/v1/health` | Health check: `{"status":"ok", …}` |

The frontend's dev server forwards `/api` to `http://127.0.0.1:8000`. For a backend elsewhere, start
the frontend with `ELIGICORE_API_URL` set, e.g. `ELIGICORE_API_URL=http://127.0.0.1:8001 npm run dev`
(PowerShell: `$env:ELIGICORE_API_URL="http://127.0.0.1:8001"; npm run dev`).

No environment variable is required beyond the database URL above. `ELIGICORE_AI_PROVIDER` defaults to
`mock`; leave it there.

## Demonstration script (about five minutes)

1. **Landing page** (`http://127.0.0.1:5173`). Explain the question EligiCore answers — "am I eligible,
   and why?" — and that it never applies for anyone.
2. **Dashboard.** Before a profile exists it shows only catalogue counts, and says nothing has been
   evaluated.
3. **Load the fictional sample profile.** Go to Profile, then **Use sample profile**. The header pill
   now reads "Sample profile (fictional)".
4. **Opportunities.** Point out the demo-catalogue notice and the verdict on every card.
5. **Apply filters.** Try a search such as "intern" and the Type filter, then clear them and set
   Eligibility to "Needs review".
6. **Open an opportunity.** Choose **Accounting Associate**.
7. **Inspect the requirements.** Each row shows your value, Pass / Fail / Not verified, whether it was
   a rule check or an AI-assisted judgement, where the requirement came from, and *why* a row needs
   attention. Here, the grade uses a different scale (EligiCore never converts scales), and the
   field-of-study check is inconclusive.
8. **Explain the verdicts.**
   - Go back and filter by "Not eligible", then open **Quantitative Analyst**. Its failures are
     verified rule checks on requirements the employer states, and a check skipped after a hard
     failure says so.
   - Then open **How it works** for all five verdicts.
9. **Profile.** Demonstrate manual entry, or upload a **fictional** résumé (PDF or DOCX). The form
   pre-fills, an unstated backlog count stays blank rather than becoming 0, and contact details are
   not kept.
10. **Privacy boundaries and limitations.**
    - The profile lives in this browser tab only. The server stores no profile, résumé or result, and
      deletes an uploaded résumé after reading it.
    - The catalogue is synthetic, search runs in the browser, and résumé parsing is the offline mock.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| "The EligiCore API isn't responding" | Backend not running, or on another port | Start `uvicorn` as above, check the health URL, then press **Try again** |
| Proxy errors in the `npm run dev` terminal (`ECONNREFUSED`) | The frontend cannot reach `127.0.0.1:8000` | Start the backend first, or set `ELIGICORE_API_URL` to where it runs |
| Dashboard says "No open opportunities yet" | The demo database has no catalogue | Run `python -m app.cli seed-catalogue` with the same `ELIGICORE_DATABASE_URL` as the backend |
| `seed-catalogue: the database schema is not at the latest migration` | The demo database is behind | Run `alembic upgrade head` with the same `ELIGICORE_DATABASE_URL`, then seed again |
| `alembic` fails with a migration error | The URL points at an unexpected database | Check `ELIGICORE_DATABASE_URL` in this terminal. Use a new file name such as `sqlite:///./demo2.db` rather than changing an existing database |
| `Port 5173 is in use` or `address already in use` on 8000 | Another dev server is running | Stop the server you started earlier, or run on another port (`uvicorn … --port 8001` with `ELIGICORE_API_URL=http://127.0.0.1:8001`) |
| `vite: command not found` or missing-module errors | Frontend dependencies not installed | Run `npm install` in `frontend/` (Node.js 20.19 or newer) |

## What is verified, and what is not

**Verified on 2026-11-02:**
- the merge and CI results above, and a local re-run on `1df4c48`
- the full journey in a browser against the real API with a seeded demo database
- an API-down error state
- no horizontal overflow at 375–1440 px
- storage limited to one `sessionStorage` key

**Not independently verified:**
- a fresh machine with a freshly installed Python environment (the clean-setup check reused an
  existing virtual environment)
- screen-reader behaviour beyond automated checks

## Known limitations and risks

- The catalogue is synthetic; there is no live job source in the app.
- Search and the verdict filter run in the browser over at most 100 jobs, the API's page limit.
- Résumé upload is click-to-choose only.
- Application preparation and the Excel tracker exist in the API but not in the UI.
- Relevance ("Relevance N/100") is labelled as not an eligibility score, but could still be misread
  as one.
- `npm install` prints an npm `allow-scripts` notice; the install and build succeed regardless.

## Exact next task after the break

**Owner decision gate: decide the proposed ADR-030 OD-16 (D23b) and ADR-028 D8a.** That means
approve, amend or reject each, as a separate documented owner decision.

- **Why:** the approved roadmap is ADR-030's implementation sequence (`context/state.md` § Next
  approved phase). Its next step, **Step 9a-2**, is blocked, and no implementation task is unblocked
  until these decisions exist.
- **No step is skipped by this decision.** Even after approval, Step 9a-2 still requires, before any
  request:
  - ADR-028 D8 resolved for dispatch through its own decision (proposed ADR-028 OD-8)
  - Greenhouse-side and employer-side permission recorded
  - a completed data protection assessment
  - a reviewed script tested on a synthetic payload
  - the board and endpoint approved
  - final execution approval immediately before the request

Extraction stays disabled. No Greenhouse request and no live Gemini call is authorized.

*Correction:* the previous handoff named an "application tracker" as the next task. That was not an
item on the approved roadmap and is withdrawn.

Also pending, not blocking: review of PR #84 (visual polish), and whether the frontend needs its own
ADR.

## Decisions that still require owner approval

- ADR-028 **D8a** and **OD-8** — proposed, not approved, not in force.
- ADR-030 **D23b** and **OD-16** — proposed, not approved, not in force.
- **Final execution approval** for any Greenhouse request — not given.
- The ADR-030 post-8b rulings, ADR-028 OD-1..OD-5 and OD-7, and Week 9B's seven decisions — unchanged.
