---
description: Build phase — implement the approved design with unit tests, in small steps
input:
  - scope
---

Start the **build** phase for: ${input:scope}

1. Run `chatur gate status`. If the design gate is not approved (or is stale), stop and tell me.
2. Delegate to **chatur-developer**. Implement the approved design and ADRs only; if the design is
   wrong or incomplete, stop and say what the architect needs to decide.
3. Work in small steps. Each step: code + unit tests, run the tests, then report changed files, test
   results, and a suggested conventional-commit message. I commit; never commit or push yourself.
4. New dependency? Create an ADR first (`chatur adr new`).
5. When the scope is complete, ask **chatur-docs** whether user docs need updating.

End with exactly this instruction for me:
> When the implementation is complete and committed, run in your own terminal: `chatur gate approve build`
