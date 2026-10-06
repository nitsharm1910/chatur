---
description: Review phase — design/ADR/test/security review of a change, saved to docs/review/
input:
  - change
---

Start the **review** phase for: ${input:change}

1. Run `chatur gate status`. If the test gate is not approved (or is stale), stop and tell me.
2. Delegate to **chatur-reviewer** (read-only, `chatur-code-review` skill) to review the change against
   the approved design, accepted ADRs, the test report, and policy. Run `chatur gate verify`.
3. Delegate to **chatur-security** for the security section.
4. The reviewer can't write files: **you** save the combined review to
   `docs/review/review-<kebab-name>.md` using `.chatur/templates/review.md`.
5. Summarise the verdict and blocking findings.

End with exactly this instruction for me:
> Read the review. If you accept it (blocking findings resolved), run in your own terminal:
> `chatur gate approve review`
