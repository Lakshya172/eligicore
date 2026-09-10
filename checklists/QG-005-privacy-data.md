# QG-005 — Privacy and Data Ownership

**Applies:** anything touching personal data — profiles, resumes, evaluations, generated
content, logging, file handling · **Reviewers:** security

> **This gate is non-negotiable and applies regardless of change size.** Local-first personal
> data is EligiCore's architectural differentiator (ADR-001). Differentiators erode quietly,
> one convenient shortcut at a time.

## Entry criteria

The change touches personal data in any way.

## Checklist

### Persistence (INV-1)

| # | Requirement | Evidence |
|---|---|---|
| 1 | No SQLAlchemy model represents a candidate, profile, evaluation, or application | Model files |
| 2 | No migration creates a table holding personal data | Migration diff |
| 3 | No profile, resume, or generated content is written to disk beyond temporary processing | file:line |
| 4 | No server-side cache stores a profile or evaluation keyed by `candidate_id` | file:line |
| 5 | A test asserts no personal-data row exists after a full request | Test name |
| 6 | `candidate_id` is treated as a client-generated correlation ID, never a server lookup key | Code review |

### Logging (INV-4)

| # | Requirement | Evidence |
|---|---|---|
| 7 | No resume content, profile payload, or PII in any log statement | Log-call review |
| 8 | Exception handlers are sanitized — no stack trace can carry resume text or profile data | file:line |
| 9 | FastAPI's default 422 handler does not echo candidate values back | Test name |
| 10 | No request body is attached to error logs or error telemetry | Config review |
| 11 | Prompts populated with profile data are not logged | file:line |
| 12 | A test asserts logs contain no PII for a request carrying a realistic profile | Test name |

### Resume lifecycle (INV-11)

| # | Requirement | Evidence |
|---|---|---|
| 13 | Temporary files are deleted in a `finally` block — not only on success | file:line |
| 14 | File handles are closed before unlinking (Windows dev, Linux prod) | file:line |
| 15 | A test asserts cleanup on the **exception** path | Test name |
| 16 | Uploads are never written to the project tree or a predictable path | file:line |

### Input safety

| # | Requirement | Evidence |
|---|---|---|
| 17 | File uploads validate actual content type and enforce a size cap before reading into memory | file:line |
| 18 | Every request body is a validated Pydantic model | file:line |
| 19 | Test fixtures contain no real personal data | Fixture review |

## Exit decision

- **PASS** — every item evidenced.
- **FAIL** — any item unmet.

**There is no warning tier on this gate.** A privacy item is either satisfied or the change does
not ship.
