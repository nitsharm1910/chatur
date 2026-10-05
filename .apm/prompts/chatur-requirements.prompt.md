---
description: Requirements phase — turn an idea into a PRD with testable acceptance criteria
input:
  - feature
---

Start the **requirements** phase for: ${input:feature}

1. Run `chatur gate status`. If requirements is already approved, say so and ask whether this is a new
   feature (new PRD) or a change to the approved one (which will make the gate stale).
2. Delegate to the **chatur-product-analyst** agent, using the `chatur-write-prd` skill and the template
   `docs/templates/prd.md`. Clarify unknowns with me before writing; don't invent facts.
3. Save to `docs/requirements/PRD-<kebab-name>.md`.
4. Summarise the PRD (goals, Must requirements, open questions).

End with exactly this instruction for me:
> Review `docs/requirements/PRD-<name>.md`. When you're satisfied, run in your own terminal:
> `chatur gate approve requirements`
