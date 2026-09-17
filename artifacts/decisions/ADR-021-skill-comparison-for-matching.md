# ADR-021 — Skill comparison for matching

**Status:** Accepted · **Date:** 2026-09-17 · **Type:** Design ruling (Week 5 design gate, PR 5A)
**Source:** dossier §10.1, §10.2, §12.2 step 1 · **Decided by:** project owner, Week 5 design gate
**Refines:** ADR-020 · **Corrects:** Week 1 `normalize_skill` (".NET" defect)

---

## Context

Dossier §12.2: "Variants map to canonical forms … Without this step, scoring is dominated by naming
noise rather than actual overlap." Week 1 built a reviewed alias seed and a lookup key in
`app/services/candidate_normalizer.py`. Week 3 deliberately left job-side skills un-aliased so that
matching, not ingestion, would own cross-side comparison. Candidate skills may also reach matching
without `/candidates/normalize` having been called. This ADR fixes how two skills are compared.

## Decision

### 1. The comparison key

`skill_comparison_key(skill) = lookup_key(normalize_skill(skill))`:

1. `normalize_skill` collapses whitespace, trims outer punctuation (§6), and maps the result
   through the reviewed alias table.
2. The lookup key lower-cases and removes every character except `a–z`, `0–9`, `+` and `#`.

So every alias of a skill shares one key ("JS", "javascript" → `javascript`); comparison is
case-, whitespace- and separator-insensitive ("Spring Boot", "spring-boot", "SpringBoot" →
`springboot`); and `+` and `#` survive, so **C, C++ and C# are three skills** (`c`, `c++`, `c#`).
R stays `r`.

### 2. Both sides, at comparison time

Candidate and job skill lists are both passed through the key when matching runs. Nothing is
rewritten in storage and ingestion is unchanged.

### 3. The alias table is the only source of equivalence

Only entries in the reviewed `_SKILL_ALIASES` table make two differently spelled skills equal:
for example JS → JavaScript, NodeJS / "node js" → Node.js, cpp → C++, Postgres → PostgreSQL. A new
equivalence needs a table entry, a test and a note here. No AI, no fuzzy matching, no runtime
configuration.

**Weak seed aliases, kept knowingly.** `node` → Node.js, `rest` → REST APIs, `express` → Express.js
and `vue` → Vue.js are defensible inside a *skill list*, where "Node" means the runtime. They would
be wrong in prose, which is why §4 exists.

### 4. Aliases apply to skill lists only — never to free text

Titles, descriptions and experience text are tokenized literally (ADR-020 §3). A description saying
"rest" or "express" or "js" produces the text tokens `rest`, `express`, `js`, never a skill term,
and never counts toward skill coverage.

### 5. No splitting; duplicates by key; blanks ignored

- A composite entry is one skill: "CI/CD", "TCP/IP", "PL/SQL" and "Node.js/Express" are never split,
  because splitting changes meaning. "CI" plus "CD" does not cover "CI/CD".
- Duplicates are removed by comparison key, first occurrence wins, keeping its display name. A
  skill listed three ways counts once toward coverage and is one TF-IDF term.
- An entry that is empty after trimming is ignored.

### 6. The ".NET" correction

`normalize_skill` trimmed `.` from both ends of a skill, so ".NET" became "NET" — an unrecognised,
wrongly spelled skill. **Corrected:** a dot is now trimmed from the **end only** ("Python." →
"Python"); a leading dot is part of the name. Two aliases, `net` → ".NET" and `dotnet` → ".NET",
make ".NET", ".net", "NET" and "dotnet" canonicalize to ".NET". "ASP.NET" and ".NET Core" remain
distinct skills.

This is an approved compatibility correction: `POST /api/v1/candidates/normalize` now returns
".NET" where it returned "NET". Only skills written with a leading dot change. Regression tests cover
.NET, NET, casing and punctuation variants, and C vs C++ vs C#.

## Rejected alternatives

- **Casefold-only comparison.** "JS" would not match "JavaScript", and "Spring Boot" would not match
  "SpringBoot".
- **Strip all punctuation.** Merges C, C++ and C# (memory D-3).
- **Split on `/`, `,` or `|`.** Breaks CI/CD, TCP/IP and PL/SQL.
- **Alias job skills at ingestion.** Buries a matching decision inside ingestion (Week 3 ruling).
- **AI or fuzzy skill matching.** Unreviewable equivalences and silent false matches.

## Enforcement

`app/services/candidate_normalizer.py` (`normalize_skill`, `skill_comparison_key`) ·
`app/services/matching_engine.py` (`skill_entries`, `skill_coverage`) ·
`tests/test_candidate_schema.py` · `tests/test_matching_engine.py` · PR 5A mutation run
