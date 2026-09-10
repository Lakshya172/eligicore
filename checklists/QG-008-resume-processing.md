# QG-008 — Resume Processing and Extraction

**Applies:** resume parsing, text extraction, file upload handling, or AI extraction changes
**Reviewers:** architect + ai + security + qa

> A resume is the most sensitive payload this system handles: a real person's name, contact
> details, education record and employment history in one file. This gate exists because the
> ordinary failure modes here — a temp file left behind, a library logging document text, a
> model inventing a qualification — are all silent.

## Entry criteria

QG-001 passed. Resume processing or AI extraction code changed.

## Checklist

### Provider abstraction (ADR-004, ADR-013, INV-5)

| # | Requirement | Evidence |
|---|---|---|
| 1 | No vendor SDK or provider name is imported outside `app/ai/providers/` | Import scan |
| 2 | Services depend on `AIProvider`, never on a concrete provider | file:line |
| 3 | Provider selection is configuration, not a branch in a service | file:line |
| 4 | Importing the AI service does not load provider-specific code | Test |
| 5 | Swapping providers requires no change outside `app/ai/providers/` | Reasoned check |

### Deterministic mockability (ADR-004, `standards/testing.md` §1)

| # | Requirement | Evidence |
|---|---|---|
| 6 | A mock provider covers the change | Mock file:line |
| 7 | The full suite passes with **no network and no API key** | pytest output, credentials unset |
| 8 | The mock returns the same result for the same input | Test |
| 9 | Provider failure modes are injectable and tested without a live provider | Test names |
| 10 | The default provider is the mock, so an unconfigured checkout cannot make a paid call | Test |

### Schema validation (`standards/ai.md` §4)

| # | Requirement | Evidence |
|---|---|---|
| 11 | Provider output is validated against a Pydantic model before reaching a service | file:line |
| 12 | Malformed, truncated and out-of-enum responses are each tested | Test names |
| 13 | A validation failure yields a controlled error — never a silent pass, never a crash | Test |
| 14 | A validation failure does not echo the offending value (Pydantic embeds it) | Test |

### Resume file lifecycle (INV-11)

| # | Requirement | Evidence |
|---|---|---|
| 15 | Temporary files are deleted in a `finally` block | file:line |
| 16 | File handles are closed before unlinking (Windows dev, Linux prod) | file:line |
| 17 | Cleanup is tested on the **failure** path, not only on success | Test name |
| 18 | Cleanup is verified through the full HTTP path, not only the service | Test name |
| 19 | Uploads are never written to the project tree or a predictable path | file:line |

### Privacy (INV-1, INV-4)

| # | Requirement | Evidence |
|---|---|---|
| 20 | Resume text, extracted text and prompts are never logged | Log-call review + test |
| 21 | **Third-party libraries cannot log document content at any root log level** | Test |
| 22 | Error responses never echo submitted file content | Test with marker string |
| 23 | Provider error bodies and transport errors never surface to the caller | Test |
| 24 | No personal-data table exists or is registered after a parse | Test |
| 25 | Extraction metadata carries counts and identifiers only, never content | Schema review |

### Truthfulness (ADR-007, INV-9)

| # | Requirement | Evidence |
|---|---|---|
| 26 | Extracted claims that cannot be traced to the source text are removed or demoted | Test |
| 27 | A claim is never upgraded — "React" does not become "Senior React Engineer" | Test |
| 28 | Absent fields stay absent; nothing is defaulted into existence | Test |
| 29 | A missing grading scale stays `UNKNOWN` and is never assumed | Test |
| 30 | A missing backlog count stays `None` and never becomes `0` (INV-3) | Test |
| 31 | Whatever traceability cannot verify is documented as a limitation, not left implied | Docstring |

### Error handling

| # | Requirement | Evidence |
|---|---|---|
| 32 | Unsupported type, corrupt document, empty document, insufficient text, provider failure and invalid output each have a defined status and a test | Test names |
| 33 | Format is determined by content, not by filename or client-declared type | Test |
| 34 | Size is enforced before extraction and before any AI call | file:line |

### Confidence (ADR-003, `standards/ai.md` §9)

| # | Requirement | Evidence |
|---|---|---|
| 35 | Extraction confidence is never presented as, or convertible to, eligibility | Test |
| 36 | Deterministic rules override the model's self-reported confidence where they disagree | Test |

## Exit decision

- **PASS** — all items evidenced.
- **FAIL** — any of items 1–2, 7, 11, 13, 15, 17, 20–24, 26–30 unmet.
- **PASS WITH WARNINGS** — items 31, 34–36 incomplete; record as debt in `context/state.md`.

## Why items 21 and 30 exist

Both come from real defects rather than theory.

**Item 21** was added after a privacy test caught pdfminer logging the literal resume text at
DEBUG level. No application log statement was involved: raising the root log level would have
been enough to dump candidate data. Any library that touches document content must be checked,
not assumed quiet.

**Item 30** is the same class of error as the eligibility engine's worst failure mode. Coercing
an unstated backlog count to zero invents a passing value, and the candidate is the one who
finds out it was wrong.
