---
description: Test phase — test plan, integration/e2e tests, and the test report
input:
  - feature
---

Start the **test** phase for: ${input:feature}

1. Run `chatur gate status`. If the build gate is not approved (or is stale), stop and tell me.
2. Delegate to **chatur-qa** (`chatur-test-plan` skill):
   - `docs/test/test-plan-<name>.md` tracing every acceptance criterion and threat-model mitigation to tests;
   - implement missing integration/e2e tests (test paths only);
   - run the suites and write `docs/test/test-report-<name>.md` from `.chatur/templates/test-report.md`.
3. Report failures as defects for chatur-developer; never delete or skip a failing test.
4. Summarise: pass/fail counts, coverage, open defects, recommendation.

End with exactly this instruction for me:
> If the results are acceptable, run in your own terminal: `chatur gate approve test`
