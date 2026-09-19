# ADR-022 — Recommendation orchestration, grouping, ranking and explanation

**Status:** Accepted · **Date:** 2026-09-19 · **Type:** Design ruling (Week 5B design gate, PR 5B)
**Source:** dossier §7 step 6, §11, §12.2 step 4, §13.4 · **Decided by:** project owner, Week 5B design gate
**Enforces:** INV-1, INV-2, INV-4, INV-7, INV-8, INV-12 · **Refines:** ADR-006, ADR-017, ADR-019, ADR-020
**Rules on:** C-19, C-20, C-21, C-22, A-15..A-24

---

## Context

Dossier §12.2 step 4: *"Eligible jobs are ranked by score. Borderline jobs appear in a separate
flagged group. Ineligible jobs are excluded from ranking but remain retrievable with their
rejection reason."* §11 names the endpoint: `POST /api/v1/recommendations`, `POST` because the
profile travels in the body.

Week 4 answers *may I apply?* (`check_eligibility_with_ai`). Week 5A answers *how relevant is this
job?* (`score_jobs`). This ADR fixes how the two are put side by side without either one changing
the other — the eligibility-first principle made structural.

## Decision

### 1. An orchestrator, not a third engine

`app/services/recommendations.py` calls, once per request:

- **`check_eligibility_with_ai(profile, selected, jobs, ai_service)`** — Week 4 unchanged,
  including its AI stage for ambiguous fields of study (ADR-019). No eligibility rule is
  re-implemented, and no AI is called from recommendation code.
- **`score_jobs(candidate_match_input(profile), [job_match_input(j) for j in catalogue], selected)`**
  — Week 5A unchanged apart from §8. No TF-IDF, normalization, scoring, coverage, top-term or
  explanation logic is re-implemented.

It adds only scope, grouping, ranking and explanation composition. Dependency direction is
`router → recommendations → eligibility + matching`; neither engine imports recommendations.

### 2. Corpus is not scope

| | What | Why |
|---|---|---|
| **Corpus** | Every catalogue job, every status, in id order | IDF weights and the fingerprint; closing a job must not change other jobs' scores |
| **Scope** | The jobs actually returned and grouped | What the caller asked about |

The router loads the catalogue in **one** query ordered by id, so the corpus — and its
fingerprint — does not depend on when jobs were last verified.

### 3. Scope and status

- **Default (no `job_ids`):** `ACTIVE` and `UNKNOWN` jobs only (`UNKNOWN` is absence of evidence,
  not closure — ADR-014). At most **50**, taken by `last_verified_at` descending then id
  ascending; the remainder is counted in `jobs_not_considered`, never silently dropped.
- **Explicit `job_ids`:** 1–50 ids, any status. `CLOSED` and `EXPIRED` are retrievable and land
  in `not_open`.
- Status is read as stored. **A deadline never implies `EXPIRED`.** No status value is added.
- `MAX_RECOMMENDATION_JOBS = 50` is its own constant, equal to but independent of the
  eligibility cap. The bound matters because each evaluated job may cost one AI call.

### 4. Unknown ids and duplicates (C-20, C-21)

- The service splits requested ids into found and **`not_found_job_ids`** (request order) *before*
  calling eligibility or matching. `score_jobs` keeps its `ValueError` for an absent id; an
  ordinary unknown id never becomes a 500.
- Duplicates are removed twice: by the request schema, and again defensively by the service. Each
  found job is evaluated, scored and reported exactly once.

### 5. Grouping — exactly one group per found job

```
1. status CLOSED or EXPIRED (explicitly requested)  → not_open
2. ELIGIBLE, LIKELY_ELIGIBLE                        → ranked
3. NEEDS_REVIEW, UNKNOWN                            → needs_review
4. NOT_ELIGIBLE                                     → not_eligible
```

`not_open` takes precedence over every eligibility group (**C-22**): a closed job goes through the
Week 4 path like any other — its verdict is computed, unmodified, and shown — and is then grouped
by status. `not_open` is a grouping, not an eligibility state.

**The recommendation layer never rewrites a verdict.** Each item embeds the `JobEligibility`
object Week 4 returned; tests compare it field for field with `/eligibility/check`.

### 6. Ranking

- `ranked` and `needs_review`: the matching engine's order — `match_score` descending, null
  scores last, `job_id` ascending. `rank` is 1-based within the group.
- `not_eligible` and `not_open`: not ranked, `rank = null`, ordered by `job_id`.
- Similarity only orders jobs **within** a group. A high score never moves a job between groups.

### 7. Scores

- `match_score` is exactly the Week 5A value (ADR-020): cosine × 100, one decimal, or null with
  its `score_basis`. Null is not zero, and it is not an eligibility score.
- **A `NOT_ELIGIBLE` verdict never carries a score**, in whichever group the job lands (so also a
  closed, ineligible job in `not_open`): `match_score = null`,
  `score_basis = WITHHELD_NOT_ELIGIBLE`, no top terms. Skill coverage is still shown. No
  similarity number sits beside a verdict saying the candidate may not apply.
- There is no combined, overall or eligibility-weighted score, and no second recommendation score.

### 8. Corpus fingerprint (C-19) — amends ADR-020 §5

`MatchingResult.corpus_fingerprint`, computed inside `score_jobs`: SHA-256 of a canonical JSON array
of `[job_id, job_terms(job)]` for each catalogue job, in catalogue order. Job-side matching data
only; candidate-free; deterministic across processes; not persisted. Same catalogue in the same
order → same value; changed matching content, membership or order → different value. Exposed as
`corpus_fingerprint` beside `corpus_size`.

### 9. Explanations

Composed, not generated: the Week 4 `summary` followed by the Week 5A `JobMatch.explanation`. Fixed
connecting sentences only — for a withheld score, *"Similarity is not reported for a job the
profile is not eligible for."*; for `not_open`, a leading *"This posting is CLOSED and is listed
for reference, not ranked."* No LLM, and no judgement ("perfect fit", "you should apply" …) —
enforced by a denylist test.

### 10. Contract and versioning

`POST /api/v1/recommendations`, request `{profile, job_ids?}` with `extra="forbid"`. Response:
`candidate_id`, `engine_version` (from the eligibility result, `"2"`), `matching_version` (from the
matching result, `"1"`), `evaluated_at`, `corpus_size`, `corpus_fingerprint`, `jobs_considered`,
`jobs_not_considered`, `ranked`, `needs_review`, `not_eligible`, `not_open`, `not_found_job_ids`.
Items: `rank`, `eligibility`, `match`, `explanation`. **No third version constant.** Errors use
the existing envelope and sanitized 422. No `GET`; `/matching/score` is not implemented.

### 11. Privacy and persistence

Stateless: no table, migration, cache, file or stored result. One counts-only log line (jobs
considered and not considered, not found, group sizes, null scores, corpus size, duration); never
`candidate_id`, skills, experience, terms or per-job scores. The only candidate identifier in the
response is the client's `candidate_id`. No new AI capability: AI runs only where Week 4 already
runs it.

## Rejected alternatives

- **One combined ranked list** or an eligibility-weighted score — conflates *may I* with *should I*.
- **Fitting TF-IDF on the returned jobs** — scores would depend on scope.
- **Skipping eligibility for closed jobs** (C-22 option b) — would leave an item without the Week 4
  verdict the contract promises.
- **Inferring `EXPIRED` from `deadline`** — a status decision hidden inside recommendations.
- **Pre-ranking by similarity to choose which 50 jobs get eligibility** — relevance would decide
  what is evaluated.
- **A recommendation version constant** — the two existing versions describe the output fully.

## Consequences

- `/recommendations` inherits Week 4's AI cost and latency for ambiguous fields, bounded by the cap.
- The whole catalogue is loaded per request; measured locally at ~32 ms for 50 jobs and ~0.2 s for
  500 (mock AI). Re-measure before the catalogue grows by an order of magnitude.
- A stored score is comparable to a new one only under the same `matching_version` and
  `corpus_fingerprint`.

## Enforcement

`app/services/recommendations.py` · `app/schemas/matching.py` · `app/routers/matching.py` ·
`app/services/matching_engine.py` (`corpus_fingerprint`) · `tests/test_recommendations.py` ·
`tests/test_recommendations_endpoint.py` · 38-mutation run · QG-001, QG-004, QG-005
