---
name: chatur-code-review
description: Use when reviewing a change before release against the approved design, accepted ADRs, tests, security requirements, and Chatur policy.
---

# Code review

Template: `assets/review.md` (also `.chatur/templates/review.md`). The reviewer is read-only; the
`/chatur-review` command saves the result to `docs/review/review-<name>.md`.

## Steps
1. Get the change set (`git diff <range>`, `git log`, `git show`; read-only commands that still need approval).
2. Read the approved design, the relevant accepted ADRs (`chatur adr list --status accepted`), and the test report.
3. Run `chatur gate verify`; earlier gates must be approved and not stale.
4. Review in this order: design conformance → decisions (new ones need an ADR) → correctness and edge
   cases → tests (meaningful? cover the acceptance criteria?) → security (with chatur-security) →
   maintainability.
5. Findings: severity (Critical/High/Medium/Low/Nit), `file:line`, what's wrong, a concrete fix.
   Separate blocking findings from nits.
6. Verdict: Approve / Approve with follow-ups / Changes required.

## Tone
Specific, kind, actionable. Explain *why*. Don't restyle code that follows the project's conventions.
