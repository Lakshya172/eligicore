# ADR-020 — Match scoring: TF-IDF over the whole catalogue, cosine, explicit nulls

**Status:** Accepted · **Date:** 2026-09-17 · **Type:** Design ruling (Week 5 design gate, PR 5A)
**Source:** dossier §7 step 6, §9, §10.2, §12.2, §13.4 · **Decided by:** project owner, Week 5 design gate
**Enforces:** INV-1, INV-4, INV-7 · **Refines:** ADR-006

---

## Context

Dossier §12.2 fixes the pipeline — skill normalization, TF-IDF, cosine similarity, a 0–100
score — and the reason for it: the system must be able to say which terms drove a score. It does
not fix which data forms a document, what the TF-IDF corpus is, how prose is tokenized, or what
a score means when one side has nothing to compare. Each of those changes the numbers a candidate
sees, so each is decided here rather than left to implementation.

Matching is **not** eligibility. Nothing in this ADR reads or writes an eligibility state, and no
score can make a job eligible or ineligible. Combining the two is PR 5B (ADR-022).

## Decision

### 1. Inputs are narrowed before scoring

| Side | Used | Never used |
|---|---|---|
| Candidate | `skills`; `experience[].title`; `experience[].description` | identity and contact fields, `candidate_id`, experience company and duration, education, grades, graduation year, backlogs, location, languages, preferences, projects, certifications, `resume_raw_text` |
| Job | `required_skills`; `role_title`; `description` | `requirements` JSON, `allowed_fields`, `min_cgpa`, grad-year window, `max_backlogs`, `min_degree_level`, company, location, job type, deadline, apply link, eligibility state |

`candidate_match_input(profile)` is the only function that receives a `CandidateProfile`; every
scoring function takes the narrowed `CandidateMatchInput`. Eligibility data is not matching data.
Projects and certifications are deliberately out of Week 5.

### 2. Documents and two term namespaces

- **Job document:** one `skill:<comparison key>` term per distinct required skill (ADR-021), then
  text tokens of the role title and the description.
- **Candidate query:** one `skill:<comparison key>` term per distinct candidate skill, then text
  tokens of each experience title and description.
- A skill term and a prose token never collide: text tokens are built from `[\w+#]` and cannot
  contain the colon. Prose "go" is not the Go skill; prose "rust" is not the Rust skill.
- Skill terms are de-duplicated (a repeated skill is one term); text tokens keep their frequency.

### 3. Text tokenizer

Case-fold, then take maximal runs of `[\w+#]`. Trim leading `+`, `#` and `_`. Drop a token that
has no letter (pure numbers), a single-character token, and any token in scikit-learn's
`ENGLISH_STOP_WORDS`. No stemming and no skill aliasing, so a reported term is a literal word.

scikit-learn's default token pattern `\b\w\w+\b` is **not** used: it deletes "c", "r", "c++" and
"c#" (memory D-3, D-12). Short technical skills survive in the skill namespace regardless.
Stop words apply to text tokens only; they never remove a skill term ("go" is a stop word, `skill:go`
is not).

### 4. TF-IDF configuration

`TfidfVectorizer(analyzer=<pre-built terms>, lowercase=False, token_pattern=None,
ngram_range=(1, 1), min_df=1, max_df=1.0, use_idf=True, smooth_idf=True, sublinear_tf=False,
norm="l2", dtype=float64)`.

With these settings `idf(t) = ln((1 + N) / (1 + df(t))) + 1`, where N is the number of catalogue
documents, and each vector is raw term frequency × IDF, L2-normalized. Unigrams only: multi-word
skills are already single terms, and bigrams are too sparse for a 5–50 job catalogue. `min_df=1`
because a higher floor would drop exactly the distinctive terms TF-IDF exists to weight.

scikit-learn is pinned exactly (`scikit-learn==1.7.2`). Its stop-word list is part of this
definition, so a different version could change scores; a test asserts the installed version
equals the pin.

### 5. Corpus — the whole catalogue, fitted per call, never the candidate

- The vectorizer is fitted on **every catalogue job** supplied to the call, not on the jobs a
  request happens to select. A job's score is therefore the same whichever subset is asked for,
  and a single-job request does not degenerate to uniform weights.
- The candidate is **transformed**, never fitted: candidate data cannot change any IDF. Candidate
  terms absent from the catalogue vocabulary are ignored.
- Fitted once per call and discarded. No vocabulary, IDF values, vectorizer, vectors or scores are
  persisted or cached, and nothing is shared between calls.

Consequence: a score can change when the catalogue changes (ingestion adds, edits or removes a
job). A catalogue fingerprint for clients to detect that belongs to the response contract, PR 5B.

**Amended 2026-09-19 (ADR-022, ruling C-19):** `MatchingResult.corpus_fingerprint` is that
fingerprint, computed inside `score_jobs`: SHA-256 of a canonical JSON array of `[job_id,
job_terms(job)]` for each catalogue job in the order given. Job-side matching data only — no
candidate field — deterministic, and never persisted. Changed matching content, membership or
order changes it; formatting that leaves the terms unchanged does not. No score changes.

**Partially superseded 2026-09-23 (ADR-026, ruling W8-A) — Week 8 Slice 8B.** The third bullet
above says *"Fitted once per call and discarded. No vocabulary, IDF values, vectorizer, vectors or
scores are persisted or cached, and nothing is shared between calls."* **Only its caching and
sharing clause is superseded**, and only for the Week 8 exception ADR-026 defines. The original
wording is kept above as the historical record of the Week 5 decision.

**What may now be cached:** the candidate-free fitted corpus artifacts — the fitted vectorizer, the
job matrix, the feature names and the catalogue row mapping — each derived from the catalogue
alone. They may be held in a **process-local, bounded, in-memory** cache keyed by
`corpus_fingerprint`, which stays the cache identity. Nothing is written to the database, to disk,
or to any external cache service.

**What is unchanged.** The candidate is still **transformed, never fitted**, and the candidate
vector and its transform remain **request-local and uncached** — the fit is cached, the candidate's
transform never is. The vectorizer is still fitted on **every catalogue job** supplied to the call,
so a job's score is still independent of which subset a request selects. **No candidate-derived
value may enter the cache**, in the key or the value. Matching outputs and ordering must be
identical cold, warm and after invalidation; a catalogue change yields a different fingerprint and
therefore a different entry, which is what preserves the "discarded" guarantee this bullet existed
to give.

**Every other ADR-020 decision stands unchanged**, including the 2026-09-19 amendment above.
ADR-026 is the authoritative record of the Week 8 exception and its limits.

### 6. Cosine and the score

Both vectors are unit length, so `cosine = candidate_vector · job_vector`, in [0, 1] because TF-IDF
weights are non-negative.

`match_score = round(clamp(100 × cosine, 0, 100), 1)` — Python `round`, one decimal place. The clamp
absorbs float error above 1. Ordering uses this rounded value, so any order a caller shows is
explainable from the numbers it shows.

### 7. Null is not zero

| Situation | `match_score` | `score_basis` |
|---|---|---|
| Both vectors non-zero | 0.0–100.0 | `SCORED` |
| Catalogue has no usable terms at all (the empty-vocabulary case is caught, never raised) | `null` | `NO_JOB_TERMS` |
| This job's document has no usable terms | `null` | `NO_JOB_TERMS` |
| The candidate contributes no term found in the catalogue vocabulary | `null` | `NO_CANDIDATE_TERMS` |

A genuine `0.0` means both sides have terms and share none. `null` means there was nothing to
compare: absence of evidence is not evidence of a mismatch — the matching counterpart of INV-3.
When a job and the candidate are both empty, the job-specific fact (`NO_JOB_TERMS`) is reported.

### 8. Signals stay separate

Skill coverage — `matched_required_skills`, `missing_required_skills` (job display names, job order)
and `required_skill_count` — is computed independently and is **explanation, not score**. There is
no percentage, no coverage score, no weighted formula and no combined or overall score. A job listing
no required skills is "none listed", never 0% or 100%. Required skills still influence
`match_score` through their skill terms, which is the dossier's own pipeline.

### 9. Evidence and explanations

- **Top terms:** up to 5 terms with positive `candidate_component × job_component`, ordered by
  contribution descending then term name ascending. Every reported term is present in both
  vectors. A skill term is shown under the job's display name; a text term as its literal token.
- **Explanations** are fixed templates filled from coverage, score, basis and top terms, e.g.
  *"Matches 2 of 3 required skills listed (Python, SQL); missing: Git. Similarity 41.3 of 100, from
  shared terms: python, sql, pipelines."* No model writes them, and they make no judgement about the
  candidate ("great fit", "strong candidate" and similar are absent by construction and by test).
  Eligibility is not mentioned; that is PR 5B.

### 10. Ordering foundation

`score descending → null scores last → job_id ascending`. Nothing else: no skill count, no
eligibility, no weights. PR 5A exposes the key; grouping by eligibility is PR 5B.

### 11. Boundary and privacy

`app/services/matching_engine.py` imports no FastAPI, SQLAlchemy, database, model, router, AI or
eligibility module, performs no file I/O and does not log — enforced by AST and fresh-interpreter
import tests. Eligibility never imports matching. The future dependency direction is
`recommendations → eligibility + matching`.

### 12. Version

`MATCHING_VERSION = "1"`. Any change to §§2–9 that can change a score or an explanation bumps it.

## Rejected alternatives

- **Fit on the request's jobs.** Scores would depend on which other jobs were requested.
- **Fit the candidate into the corpus.** Candidate data would alter every job's term weights.
- **scikit-learn's default tokenizer.** Loses C, R, C++ and C#.
- **One namespace.** Prose words would match skills they merely spell.
- **Aliasing prose.** "rest", "express", "node" and "go" are ordinary English.
- **A weighted skill/text score.** An arbitrary weighting is opaque, which ADR-006 forbids.
- **Zero for no data.** Reports "no overlap" where nothing was compared.
- **Bigrams, stemming, sublinear tf.** More knobs than a 5–50 job catalogue supports, and stems
  make reported terms non-literal.
- **Embeddings.** Unexplainable; the dossier keeps them as a later upgrade path.
- **Hand-rolled TF-IDF.** scikit-learn is the approved stack (§9); replacing it would need its
  own ADR.

## Known limitations

- The IDF of a 5-job catalogue is coarse; distinctions sharpen as the catalogue grows.
- English stop words only; no stemming, so "pipeline" and "pipelines" are different terms.
- A candidate whose terms all fall outside the catalogue vocabulary gets `null`, not `0.0`.
- Scores move when the catalogue changes (§5).
- Fitting per call is O(total catalogue tokens); trivial at Phase 1 scale, to be measured before
  the catalogue grows by orders of magnitude.

## Enforcement

`app/services/matching_engine.py` · `tests/test_matching_engine.py` (hand-computed IDF and weights,
subset independence, null semantics, AST boundaries, privacy) · 36-mutation run · QG-001, QG-005
