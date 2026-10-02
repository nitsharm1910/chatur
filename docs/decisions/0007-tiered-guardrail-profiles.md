---
id: ADR-0007
title: Tiered guardrail profiles (strict / standard / relaxed)
status: Accepted
date: 2026-10-02
deciders: Nitin
phase: design
tags: [guardrails, policy]
amended_by: [ADR-0014]
---

> **Amended by [ADR-0014](0014-human-in-the-loop-baseline.md):** git commit/push/history-rewrite (deny),
> file changes and command execution (ask) are now baseline in all profiles.

# ADR-0007: Tiered guardrail profiles

## Context
A prototype and a regulated production service need different friction levels, but a few rules must never be relaxed.

## Decision
We will ship three profiles in `policies/`, selected in `.chatur/config.toml`:

| Rule class | strict | standard | relaxed |
|---|---|---|---|
| Secrets in files/commands | deny | deny | deny |
| Destructive shell (`rm -rf /`, `git push --force` to protected, `DROP DATABASE`…) | deny | deny | deny |
| Edits to protected paths (`.chatur/state.json`, `.github/workflows`, policies) | deny | ask | warn |
| Code change without approved Design gate | deny | warn | off |
| Missing tests for changed source | deny | warn | off |
| Dependency added without ADR | deny | warn | off |
| Network/web tools | ask | allow+log | allow+log |

The **baseline** rows (secrets, destructive) cannot be weakened by any profile or local override.
Projects can add rules or tighten them in `.chatur/policy.local.toml`.

## Guardrails / best practices this implies
- Policy loader rejects any override that lowers a baseline rule.
- Every verdict records which rule and profile produced it (in the audit log).
