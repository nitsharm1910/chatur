---
id: ADR-0006
title: Track actions, decisions, and state as files in the target repo
status: Accepted
date: 2026-10-02
deciders: Nitin
phase: design
tags: [tracking, audit]
---

# ADR-0006: In-repo tracking

## Context
Every action, design, and decision must be traceable without extra infrastructure, and it has to work offline and in CI.

## Options considered
1. **Files in the repo**: git-versioned, zero infrastructure.
2. **SQLite + markdown**: queryable, but binary diffs.
3. **External system** (Jira/Notion): needs credentials and network; deferred as optional exporters.

## Decision
We will store, in the target repo:
- `.chatur/audit/YYYY-MM-DD.jsonl`: an append-only log with one ChaturEvent + Verdict per line, secrets redacted.
- `.chatur/state.json`: current SDLC phase, gate approvals (who, when, artifact hash).
- `docs/decisions/*.md`: ADRs (ADR-0001 format).
- Phase artifacts under `docs/{requirements,design,test,security,releases}/`.

## Consequences
- Positive: auditable in PRs, portable, greppable.
- Negative: the audit log grows. Mitigation: daily files, and `.chatur/audit/` is configurable as committed or gitignored (default: committed for strict, ignored for relaxed).

## Guardrails / best practices this implies
- The audit writer redacts known secret patterns before writing and never logs file contents, only paths and hashes.
- Audit lines are append-only. CI fails if past lines are modified (hash chain: each line stores the previous line's hash).
