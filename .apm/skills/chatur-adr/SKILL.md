---
name: chatur-adr
description: Use when a technical or process decision with lasting consequences is made, to record it as an Architecture Decision Record with options, consequences, and guardrails.
---

# Architecture Decision Record

Template: `assets/adr.md`. Create the file with the CLI so numbering stays consistent:
`chatur adr new "<concise decision title>" --phase <phase> [--supersedes <n>]`.

## Write it well
1. **Context:** the forces at play: requirements, constraints, earlier ADRs. Link them.
2. **Options considered:** at least two real options, each with pros and cons. "Do nothing" counts.
3. **Decision:** one sentence starting "We will …".
4. **Consequences:** positive, negative, and follow-ups with owners. Be honest about the costs.
5. **Guardrails / best practices:** the concrete rules that follow from the decision and **where each is
   enforced** (instructions, Chatur hook, git hook, CI). This is what turns a decision into practice.

## Rules
- Status starts **Proposed**; only a human sets **Accepted** (ADR-0001).
- Accepted ADRs are immutable. Change a decision by superseding it: draft the replacement with
  `--supersedes <n>`; after a human accepts it, run `chatur adr supersede <n> --by <new>`.
- One decision per ADR; keep it short enough to read in two minutes.
