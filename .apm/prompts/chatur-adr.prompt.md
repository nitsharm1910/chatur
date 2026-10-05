---
description: Record an architecture decision as a Proposed ADR
input:
  - decision
---

Record this decision as an ADR: ${input:decision}

1. Check existing decisions with `chatur adr list`. If this replaces one, note its number.
2. Create the file: `chatur adr new "<concise title>" --phase <phase>` (add `--supersedes <n>` when it
   replaces an existing ADR).
3. Use the **chatur-architect** agent (`chatur-adr` skill) to fill in Context, Options considered (at
   least two, with pros and cons), Decision, Consequences, and **Guardrails / best practices**: the
   concrete rules that follow from the decision and where they're enforced.
4. Leave the status **Proposed**.

End with:
> Review the ADR. To accept it, change `status: Proposed` to `status: Accepted` yourself.
> If it supersedes ADR-<n>, then run `chatur adr supersede <n> --by <new>`.
