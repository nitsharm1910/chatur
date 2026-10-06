---
name: chatur-write-prd
description: Use when writing or revising a product requirements document (PRD) for a feature, including goals, user stories, and testable Given/When/Then acceptance criteria.
---

# Write a PRD

Template: `assets/prd.md` (also at `.chatur/templates/prd.md`). Save as `docs/requirements/PRD-<kebab-name>.md`.

## Steps
1. **Problem first.** One paragraph: who, what pain, why now, evidence. Confirm it with the human.
2. **Goals and non-goals.** Goals are measurable outcomes, not features. Non-goals prevent scope creep.
3. **Requirements.** Number them (`FR-1`, `NFR-1`) and give each a MoSCoW priority. One testable
   statement each; no "and".
4. **User stories.** `As a <persona>, I want <capability> so that <benefit>`, each with
   Given/When/Then criteria a tester can verify without asking anyone.
5. **Non-functional.** Performance numbers, security/privacy, accessibility, availability, compliance.
6. **Unknowns.** Put anything you'd otherwise guess into the risks/assumptions/questions table, with an owner.
7. **Metrics.** How success is measured and when.

## Quality bar
- Every Must requirement is covered by at least one acceptance criterion.
- No solution design (that belongs to the design phase).
- No secrets or personal data; use placeholders.

Finish by telling the human to review it and run `chatur gate approve requirements`.
