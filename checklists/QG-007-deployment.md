# QG-007 — Deployment

**Applies:** deploying to a public environment · **Reviewers:** security + release

> Relevant from Week 9. This is the point at which the API becomes publicly reachable and the
> owner's API budget becomes publicly spendable.

## Entry criteria

The full test suite passes on the release commit. All prior gates passed for included work.

## Checklist

### Secrets

| # | Requirement | Evidence |
|---|---|---|
| 1 | All secrets supplied via host environment variables | Host config |
| 2 | No secret in the repository, in git history, or in a deployed image | Scan output |
| 3 | `.gitignore` covers `.env`, and `.env.example` holds names with dummy values only | File review |

### Database (ADR-009)

| # | Requirement | Evidence |
|---|---|---|
| 4 | **Migrations applied and verified against PostgreSQL** — not assumed from SQLite | Command output |
| 5 | The production database holds operational data only, with no personal-data table (INV-1) | Schema dump |
| 6 | A rollback path exists — previous deploy and migration downgrade | Documented |

### Privacy in production (INV-4)

| # | Requirement | Evidence |
|---|---|---|
| 7 | Production logging configured so PII cannot be captured | Config |
| 8 | Error telemetry configured not to capture request bodies | Config |
| 9 | Debug mode and verbose tracebacks disabled | Config |

### Cost and abuse

| # | Requirement | Evidence |
|---|---|---|
| 10 | Rate limiting active on AI-cost-exposed endpoints | Config + a manual check |
| 11 | Batch sizes capped on `/eligibility/check` and `/recommendations` | file:line |
| 12 | AI spend is bounded — a provider-side limit or an application-side cap exists | Config |
| 13 | `/docs` public or closed by deliberate decision, not by default | Config |

### Verification

| # | Requirement | Evidence |
|---|---|---|
| 14 | The full suite passes against the release commit | pytest output |
| 15 | The deployed API answers a real request end to end | Response |
| 16 | `/docs` renders and the documented endpoints work as described | Manual check |
| 17 | `context/state.md` reflects what is actually deployed | Diff |

## Exit decision

- **PASS** — all items evidenced.
- **FAIL** — any item unmet.

**No warning tier.** A public deployment with an unbounded AI cost surface or a leaking log is
not a warning; it is an incident waiting on someone finding the URL.
