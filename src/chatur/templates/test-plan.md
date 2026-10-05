---
title: Test plan — <feature>
status: Draft
author: <name>
date: YYYY-MM-DD
prd: docs/requirements/<PRD>.md
design: docs/design/<design>.md
---

# Test plan: <feature>

## 1. Scope
What is tested, what is not (and why).

## 2. Traceability
| Requirement / story | Test cases | Level (unit/integration/e2e) |
|---|---|---|
| FR-1 / US-1 | TC-1, TC-2 | integration |

## 3. Test cases
| ID | Title | Preconditions | Steps | Expected result | Automated (path) |
|---|---|---|---|---|---|
| TC-1 | | | | | tests/... |

## 4. Non-functional tests
Performance, security (from the threat model), accessibility, compatibility.

## 5. Environments and data
Where tests run; test data and how it is created (no production secrets).

## 6. Entry and exit criteria
- Entry: build gate approved, environments ready.
- Exit: all Must tests pass, no open Critical/High defects, coverage target met.
