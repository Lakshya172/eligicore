# EligiCore — status at the one-week freeze (2026-11-02)

Branch `feat/student-ui-mvp`, based on `main` at `a993440`. The PR is open for review and not merged.

## What is implemented

- **Student web app** in `frontend/` (React 19 + TypeScript + Vite, no UI or router library). It has
  six screens: landing, dashboard, opportunity explorer, job details with eligibility explanation,
  profile with résumé pre-fill, and "How it works".
- It uses only existing API endpoints: `GET /health`, `GET /jobs`, `GET /jobs/{id}`,
  `POST /recommendations`, `POST /resumes/parse` and `POST /candidates/validate`.
- **No backend code changed.** The dev server proxies `/api` to the backend, so no CORS change was
  needed.
- A separate `frontend` CI job runs lint, type-check, build and tests. `node_modules/` is now
  git-ignored.

## What works end to end (verified in a browser against the real API)

| Journey | Result |
|---|---|
| Landing → Dashboard | Catalogue counts from `GET /jobs`: 40 open, 21 internships, 19 full-time, 0 closed |
| Profile → sample profile → Dashboard | Real `POST /recommendations` result for the fictional sample: 19 eligible, 12 need review, 9 not eligible, with top matches |
| Explorer | 40 cards with verdict badges; search, type, status and verdict filters; the verdict filter showed 9 "Not eligible" jobs, matching the dashboard |
| Job details | Full breakdown for `NEEDS_REVIEW` (a scale mismatch and an inconclusive AI-assisted check) and for `NOT_ELIGIBLE` (two verified source-stated failures) |
| Résumé upload | A generated fictional PDF was parsed by the mock provider (`PARTIAL`). The form was pre-filled, and backlogs stayed blank rather than becoming 0 |
| API down | A clear error state appears, and "Try again" recovers once the API is back |
| Mobile (375 px) | Collapsing menu, single-column cards, no horizontal overflow |

No browser console errors were logged during these runs.

## What is only a demo

- **The catalogue is EligiCore's curated synthetic dataset** (40 postings, fictional "Example …" and
  "Sample …" employers, placeholder `example.com` links). Every listing page says so.
- **"Use sample profile"** loads a fictional student. It produces real evaluations of that fictional
  profile, and every result computed from it is labelled as such.
- Résumé parsing runs on the offline **mock** provider, which uses pattern matching.
- The landing-page verdict card is a static illustration, labelled "Illustration, not a real
  evaluation".

## What remains incomplete

- Text search and the verdict filter run in the browser, because the API has no search parameter.
  The explorer loads at most 100 jobs, the API's page limit.
- Application preparation (`/applications/prepare`) and the Excel tracker (`/applications/export`)
  are not in the UI yet.
- There is no saved application tracking in the browser yet. The dossier's IndexedDB store isn't
  built; the profile lives only in `sessionStorage`.
- Résumé upload is click-to-choose only, with no drag-and-drop.
- There are no end-to-end browser tests in CI; frontend tests mock the API.
- The frontend has no ADR of its own. The README lists a frontend under "Future phases (Phase 2)",
  and this sprint delivered one early on the owner's instruction.

## Commands

From the repository root, after `pip install -r requirements.txt`:

```bash
# Use a separate demo database, never a developer database.
export ELIGICORE_DATABASE_URL=sqlite:///./demo.db     # PowerShell: $env:ELIGICORE_DATABASE_URL="sqlite:///./demo.db"
alembic upgrade head
python -m app.cli seed-catalogue
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev            # http://127.0.0.1:5173
```

Environment variables: none are required.
- `ELIGICORE_DATABASE_URL` selects the database, and the default is `./eligicore.db`.
- `ELIGICORE_AI_PROVIDER` defaults to `mock`. Leave it there; no live provider is used.
- `ELIGICORE_API_URL` is an optional setting for the frontend dev server, if the API isn't on
  `http://127.0.0.1:8000`.

### Five-minute demo script

1. Open `http://127.0.0.1:5173`. On the landing page, explain what the product proposes, then point
   to the three steps and "never applies for you".
2. **Opportunities**: there are 40 synthetic roles. Point out the demo-catalogue notice, then search
   for "intern" and filter by type.
3. **Profile**: click **Use sample profile** and note the "fictional" label in the header.
4. **Dashboard**: show the real eligibility totals and the top matches, and explain that relevance
   ranks only within the eligible group.
5. **Opportunities**: filter by "Needs review" and open **Accounting Associate**. Show the scale
   mismatch ("never converts between scales") and the AI-assisted check that verified nothing.
6. Filter by "Not eligible" and open **Quantitative Analyst**. Show the verified, employer-stated
   failures and the check that was skipped after a hard failure.
7. **How it works**: cover the five verdicts, data handling and limitations.

## Tests actually executed (2026-11-02)

| Suite | Command | Result |
|---|---|---|
| Frontend unit and component tests | `npm test` (Vitest) | **39 passed** |
| Frontend lint | `npm run lint` | Clean |
| Frontend type-check and build | `npm run build` | Clean; 84.6 kB gzipped JS |
| Backend full suite | `pytest -q` from the feature worktree | **3030 passed, 1 warning** (a Starlette `BlockingPortal` deprecation notice) in 211 s |
| Browser journey | Manual, against `uvicorn` and a seeded demo DB | See "What works end to end" |

The developer database (`E:/EligiCore/eligicore.db`) kept md5 `9ee7d979e041d5346bfab68e96216fd0`
before and after.

## Known bugs and risks

- The first CI run of the new `frontend` job hasn't happened yet. The lockfile was generated on
  Windows with npm 11; it does contain the Linux native packages, but this is unverified on CI.
- In development, React StrictMode issues each request twice, and the first is aborted. This is
  expected; production builds don't do it.
- `match_score` (relevance) is shown as "Relevance N/100" and labelled as not an eligibility score.
  Students may still read it as one.
- One catalogue record is titled "Other" with no location. This is catalogue data, not a UI bug.

## Exact next task after the break

Review and merge this PR. Then add the **application tracker** to the UI: keep chosen jobs and their
status in browser storage (IndexedDB, per dossier §10), and export them through the existing
`POST /api/v1/applications/export`. It needs no backend change.

## Decisions that still require owner approval

- **ADR-028 D8a** (proposed): D8 resolution required before any Greenhouse dispatch.
- **ADR-028 OD-8** (proposed): element-by-element D8 resolution for Greenhouse.
- **ADR-030 D23b / OD-16** (proposed): scope of Step 9a-2.
- **Final execution approval** for any Greenhouse request: not given.
- Whether the frontend warrants its own ADR, and whether it should ever be served by the API.
- The ADR-030 post-8b rulings, ADR-028 OD-1..OD-5 and OD-7, and Week 9B's seven decisions, all
  unchanged.
