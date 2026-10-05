---
description: Ask Chatur whether an action would be allowed, and explain why
input:
  - action
---

Check with Chatur whether this action is allowed: ${input:action}

1. Choose the right form:
   - a shell command → `chatur check "<command>"`
   - writing a file → `chatur check --write <path>`
   - a tool call → `chatur check --tool <name> --category <category>`
   Add `--json` for full rule details.
2. Run it. It's a dry run: nothing executes and nothing is logged.
3. Explain the result in plain language: the decision (allow / ask / deny), each rule that matched and
   its ADR, and, if denied, the legitimate way to achieve the goal (usually a human performs the action,
   or a decision is recorded first). Never suggest a way around a guardrail.
