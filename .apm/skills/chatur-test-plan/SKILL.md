---
name: chatur-test-plan
description: Use when planning and reporting testing for a feature — tracing acceptance criteria and threat mitigations to test cases, then writing the test report.
---

# Test plan and test report

Templates: `assets/test-plan.md` and `assets/test-report.md` (also in `.chatur/templates/`).
Save as `docs/test/test-plan-<name>.md` and `docs/test/test-report-<name>.md`.

## Plan
1. Pull every acceptance criterion from the PRD and every mitigation from the threat model.
2. Traceability table: each one maps to one or more test cases at the lowest useful level
   (unit < integration < e2e).
3. Test cases: preconditions, steps, expected result, and the automated test path.
4. Non-functional tests with numeric targets (latency, throughput, security checks).
5. Entry/exit criteria (exit: all Must tests pass, no open Critical/High defects, coverage target met).

## Execute and report
- Run the suites (commands need human approval) and record exact commands and the commit tested.
- Report counts, coverage, failures as defects with severity, and deviations from the plan.
- Never delete, skip, or weaken a failing test to make the report green; flaky tests are defects.
- Test data is synthetic; use placeholders for anything secret-shaped.

Finish by telling the human to run `chatur gate approve test` if the results are acceptable.
