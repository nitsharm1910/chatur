---
description: Design phase — design document, ADRs, and threat model from the approved PRD
input:
  - feature
---

Start the **design** phase for: ${input:feature}

1. Run `chatur gate status`. If the requirements gate is not approved (or is stale), stop and tell me.
2. Delegate to **chatur-architect** (`chatur-design-doc` skill, template `docs/templates/design.md`):
   options with trade-offs, a recommendation, and an ADR per significant decision
   (`chatur adr new "<decision>" --phase design`).
3. Delegate to **chatur-security** (`chatur-threat-model` skill) for
   `docs/security/threat-model-<name>.md`, and feed its security requirements back into the design.
4. Summarise: chosen approach, ADRs created (all Proposed), top threats and mitigations, open questions.

End with exactly this instruction for me:
> Review the design, the threat model, and the Proposed ADRs (`chatur adr list --status proposed`).
> Accept the ADRs you agree with, then run in your own terminal: `chatur gate approve design`
