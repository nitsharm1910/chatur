---
id: ADR-0005
title: Defense-in-depth enforcement (assistant hooks + git hooks + CI)
status: Accepted
date: 2026-10-02
deciders: Nitin
phase: design
tags: [guardrails, security]
---

# ADR-0005: Defense-in-depth enforcement

## Context
Not every assistant can block actions (some have no hooks, or only partial events), and
instructions are advisory: a model can ignore them. Guardrails that rely only on the assistant
cannot be trusted.

## Decision
We will enforce each guardrail at the strongest available layer, and every critical rule
must have at least one layer outside the assistant:
1. **Instructions** (AGENTS.md / agents): guide behavior, with no enforcement.
2. **Assistant hooks** (Claude, Copilot): block in-session, before damage.
3. **git hooks** (`chatur git-hook pre-commit|pre-push`): block bad commits from any assistant or a human.
4. **CI** (`chatur ci-check`): final gate on PRs; it cannot be bypassed locally.

## Consequences
- Positive: assistants without hook support (Codex/Gemini before their adapters land) are still governed at commit and CI.
- Negative: some checks run twice (cheap; they're idempotent).

## Guardrails / best practices this implies
- Each policy rule declares `layers: [hook, git, ci]`; a rule marked `critical` without `git` or `ci` fails policy validation.
