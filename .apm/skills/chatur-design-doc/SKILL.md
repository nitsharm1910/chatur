---
name: chatur-design-doc
description: Use when producing a technical design from an approved PRD — components, interfaces, data, alternatives, rollout — and recording each significant decision as an ADR.
---

# Write a design document

Template: `assets/design.md` (also `docs/templates/design.md`). Save as `docs/design/<kebab-name>.md`.

## Steps
1. Confirm the requirements gate is approved (`chatur gate status`).
2. **Traceability:** list each Must FR/NFR and where the design satisfies it.
3. **Solution:** a short narrative plus a Mermaid diagram of components and data flow.
4. **Interfaces:** exact contracts (request/response or schema examples, error cases, versioning).
5. **Alternatives:** at least two real options per major decision, with pros and cons. Record the chosen
   one with `chatur adr new "<decision>" --phase design` (stays Proposed until a human accepts).
6. **Cross-cutting:** security (link the threat model from chatur-security), performance, observability,
   failure modes and rollback.
7. **Testing strategy** and **rollout plan** (flags, migrations, compatibility).

## Quality bar
- A developer could implement it without guessing; QA could derive tests from it.
- Every new dependency has an ADR.
- Open questions are listed, not hidden.

Finish by telling the human to review the design, threat model, and ADRs, then run `chatur gate approve design`.
