---
title: Code review — <change>
status: Draft            # gate: review
reviewers: [chatur-reviewer, chatur-security]
date: YYYY-MM-DD
scope: <commit range / PR / paths>
---

# Code review: <change>

## 1. Verdict
Approve / Approve with follow-ups / Changes required — one paragraph why.

## 2. Conformance
| Check | Result | Notes |
|---|---|---|
| Matches approved design (docs/design) | | |
| Follows accepted ADRs | | |
| Tests cover new behaviour (docs/test) | | |
| Security requirements met (threat model) | | |
| No secrets, no debug leftovers | | |
| `chatur gate verify` clean | | |

## 3. Findings
| ID | Severity (Critical/High/Medium/Low/Nit) | File:line | Finding | Recommendation |
|---|---|---|---|---|

## 4. Security review
Summary from chatur-security (dependency changes, authn/z, input handling, data exposure).

## 5. Follow-ups
Items that don't block release, each with an owner.
