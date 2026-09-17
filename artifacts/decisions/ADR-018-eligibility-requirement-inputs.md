# ADR-018 — Eligibility requirement inputs: grades, qualification selection, degree level, fields

**Status:** Accepted · **Date:** 2026-09-17 · **Type:** Ruling (resolves **C-10**, **C-12**, **A-1**, **A-2**, **A-4**)
**Source:** dossier §10.1, §10.2, §12.1, §17 · **Decided by:** project owner, Week 4 design gate
**Enforces:** INV-3 · **Refines:** ADR-003, `standards/eligibility.md` §§2–4

---

## Supported requirement types

| Type | Candidate field | Job field |
|---|---|---|
| `MIN_CGPA` | selected qualification `cgpa` + `scale` | `min_cgpa` + `min_cgpa_scale` |
| `GRAD_YEAR_WINDOW` | selected qualification `grad_year` | `min_grad_year`, `max_grad_year` |
| `MAX_BACKLOGS` | profile `backlogs` | `max_backlogs` |
| `MIN_DEGREE_LEVEL` | selected qualification `level` | `min_degree_level` (new — C-10) |
| `ALLOWED_FIELDS` | selected qualification `field_of_study` | `allowed_fields` |

**Not eligibility requirements:** required skills (dossier §10.2 assigns them to match scoring),
location, job type and work mode (candidate preferences), experience and work authorization (no
field on either side). Matching is Week 5 (C-11).

## C-10 — Degree level needs a job field

Dossier §12.1 and §17 name degree level as a deterministic hard constraint, but §10.2's `jobs`
table had no field for a posting to state one.

**Decision:** a typed, nullable `jobs.min_degree_level` column using the existing `DegreeLevel`
enum, carried through `RawJob`, `NormalizedJob` and `JobRead`. Added by the additive migration
`b3e8d2c61a47` with a CHECK constraint; the merged migrations `54a85d64881e` and `7c2f1a9b4d30`
are untouched. Null means the posting states no level requirement.

Ordering: `HIGH_SCHOOL < DIPLOMA < BACHELORS < MASTERS < DOCTORATE`. `OTHER` and `UNKNOWN` are
unorderable: on the candidate side they yield `UNKNOWN`; as a job requirement they are invalid
and also yield `UNKNOWN`. A level is never guessed from a degree name.

## C-12 — Grades are compared on the same scale only

The Week 1 `NormalizedGrade` docstring claimed that a linear `cgpa / scale_maximum` fraction made
cross-system comparison possible. It does not. Conversions between 4-point, 10-point and
percentage systems are institution-specific and non-linear; 3.28/4 and 8.2/10 share a fraction
but are not equivalent grades.

**Decision:** compare only when both scales are known and identical. `UNKNOWN` when the candidate
scale is unknown, the job scale is missing or unrecognised, the scales differ, or either value
exceeds its scale's maximum. No conversion is performed or assumed. The docstring is corrected.

A job scale string is read trimmed and case-insensitively (`" scale_10 "` is `SCALE_10`) —
reading what the source stated, not inferring what it meant.

## A-1 — Which qualification a requirement applies to

A profile may hold several education entries; CGPA, graduation year, level and field are
properties of one qualification.

**Decision:**

1. Exactly one entry → use it, whatever its level.
2. Several entries → the single entry at the highest *known* orderable level.
3. A tie at that level, or no entry with an orderable level → `QUALIFICATION_NOT_DETERMINABLE`.
4. No entries → `NO_QUALIFICATION`.

The selection is made **once** per evaluation and shared by all four per-qualification rules.
Values from different entries are never combined: a CGPA from a school record never stands in
for a missing degree grade.

**Accepted cost.** `DegreeLevel` defaults to `UNKNOWN`, so a multi-entry profile whose levels
were never set resolves these requirements to `UNKNOWN`. That is honest, and the remedy — setting
the level — is in the candidate's hands.

## A-2 — Permitted fields have no ontology

**Decision:** trim, collapse whitespace and casefold both sides; an exact match is a
deterministic `PASS`. Anything else is **ambiguous** — `UNKNOWN` with `FIELD_NOT_EXACT_MATCH` —
and **never** a deterministic `FAIL`. A missing field is `UNKNOWN`; an empty `allowed_fields`
list omits the requirement. No stemming, abbreviation expansion or synonym table.

The ambiguous case is exactly the one the approved AI stage (PR 4B) may assess.

## A-4 — Batch size

`job_ids` holds 1–50 entries, validated on the raw list; duplicates are removed keeping first-seen
order. Unknown ids are returned in `not_found_job_ids` rather than failing the request.

## Rejected alternatives

- **Linear scale conversion.** Produces confident, wrong comparisons.
- **"Any qualification passes."** Lets a school percentage satisfy a degree CGPA cutoff.
- **Degree level inside the free-form `requirements` JSON.** Untyped, unvalidated at the adapter
  boundary, and inconsistent with every other criterion being a typed column.
- **A field synonym table.** An ontology in disguise, and a source of silent false passes.

## Enforcement

`app/services/eligibility_engine.py` · `tests/test_eligibility_engine.py` ·
`tests/test_job_degree_level.py` · QG-002, QG-006
