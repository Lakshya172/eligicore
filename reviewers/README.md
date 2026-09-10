# Reviewers — EligiCore

> **These are review lenses, not runtime agents.** Nothing here ships in the product.
> **The goal is useful review, not bureaucracy.** Do not run every reviewer on every change.

---

## How this works

A reviewer is a checklist of questions applied to a change, from one perspective. In this solo
project the same session applies them — the value is in *switching perspective deliberately*,
not in delegation.

Each reviewer returns **PASS**, **CONDITIONAL PASS** (issues found, none blocking) or **FAIL**,
with **specific evidence** — file and line. "Looks fine" is not a review result.

**A FAIL from any reviewer blocks the change.** Disagreement with a FAIL goes to the human, not
around the reviewer.

---

## Trigger map — select by change impact

| Change touches | Reviewers |
|---|---|
| Eligibility engine | **architect + ai + qa** |
| AI provider, prompts, AI service | **ai + security + qa** |
| API endpoint (new or modified) | **api + qa** |
| Database model or migration | **architect + security + qa** |
| Job adapter or ingestion | **architect + qa** |
| Matching engine | **architect + qa** |
| Application prep / truthfulness validator | **ai + security + qa** |
| Resume parsing / file upload | **security + qa** |
| Anything touching personal data | **security** (always, non-negotiable) |
| Deployment or infrastructure | **security + release** |
| Performance-sensitive path (batch eligibility, ingestion, matching at scale) | **performance + qa** |
| README, docs, OpenAPI descriptions | **documentation** |
| Release / version tag | **release + documentation** |

**Defaults:** `qa` reviews anything with logic. `security` reviews anything touching personal
data, files, secrets or external input — no exceptions and no judgment call. `architect` reviews
anything that changes structure, boundaries or contracts.

**Trivial changes** — a typo, a comment, a docstring — need no reviewer. Do not manufacture
process for them.

---

## Roster

| Reviewer | Question it answers |
|---|---|
| [architect](architect.md) | Does this preserve the layering, boundaries and invariants? |
| [api](api.md) | Is the contract correct, consistent and stateless? |
| [security](security.md) | Does this leak, persist or expose anything it must not? |
| [ai](ai.md) | Is AI used correctly, bounded, mockable, and unable to override rules? |
| [qa](qa.md) | Is it actually tested, including the cases that matter? |
| [performance](performance.md) | Will this hold up at realistic scale and cost? |
| [documentation](documentation.md) | Can a stranger understand this? Is context updated? |
| [release](release.md) | Is this safe to deploy? |

---

## Escalation

There is no reviewer hierarchy and no escalation ladder. When reviewers conflict, or when a FAIL
is disputed, **the human decides.** That is the whole escalation model, and at this scale it is
the correct one.
