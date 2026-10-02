---
id: ADR-0004
title: Python core with a normalized ChaturEvent and per-assistant adapters
status: Accepted
date: 2026-10-02
deciders: Nitin
phase: design
tags: [core, hooks, adapters]
---

# ADR-0004: Python core with a normalized ChaturEvent and per-assistant adapters

## Context
Hooks are the least portable primitive. Claude uses `PreToolUse` with
`hookSpecificOutput.permissionDecision`, while Copilot uses `preToolUse` with
camelCase `toolName`/`toolArgs` and top-level `permissionDecision`. Codex and Gemini each
differ again. Guard logic must not be duplicated per assistant.

## Options considered
1. **Separate hook scripts per assistant**: logic is duplicated, and bugs diverge.
2. **One core engine behind thin adapters that translate payloads in and verdicts out**.

## Decision
We will implement guards, audit, gates, and ADR tooling once in a Python package `chatur`
that only consumes a normalized `ChaturEvent` (see architecture §3). Each assistant gets an
adapter module with `parse(native) -> ChaturEvent` and `render(Verdict) -> (stdout, exit_code)`.
Every native hook calls `chatur hook <assistant> <event>`. Python was chosen for cross-platform
support and alignment with the Python Agent SDK (the future runner).

## Consequences
- Positive: adding an assistant means writing one adapter plus fixtures.
- Negative: target machines need Python ≥ 3.11 (pipx-installed `chatur`).

## Guardrails / best practices this implies
- Assistant-specific code lives only in `src/chatur/adapters/` (enforced by an import-lint test).
- Each adapter ships recorded real payload fixtures and round-trip tests.
