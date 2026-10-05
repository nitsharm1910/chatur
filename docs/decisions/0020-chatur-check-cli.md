---
id: ADR-0020
title: "`chatur check`: evaluate one action from the command line"
status: Accepted
date: 2026-10-04
deciders: Nitin
phase: design
tags: [cli, guard, debugging]
---

# ADR-0020: `chatur check`

## Context
Testing the guard by hand meant writing a Python script. Humans debugging a policy, CI scripts, and
(in Phase 2) people debugging hook behaviour all need a one-line way to ask "what would Chatur do?".

## Decision
```
chatur check [COMMAND] [--write PATH] [--read PATH] [--tool NAME [--category CAT]]
             [--profile P] [--root DIR] [--unattended] [--gate PHASE ...] [--json]
```
- `COMMAND` builds a shell `pre_tool` event. `--write`/`--read` build file events. `--tool` builds a
  tool event (category defaults to `other`). Exactly one of these is required.
- The policy comes from the project (`--root`, `.chatur/config.toml`) unless `--profile` is given.
- Approved gates come from `.chatur/state.json`; `--gate` adds phases for what-if checks.
- **Nothing is written to the audit log.** `check` is a dry run.
- **Exit codes:** `0` allow/log/warn · `2` ask · `3` deny · `1` usage or policy error.

## Consequences
- Positive: scripting (`chatur check "$cmd" || …`), quick policy debugging, documentation examples.
- Negative: none significant. It's read-only and reuses `guard.evaluate`.

## Guardrails / best practices this implies
- Tests for each event type, exit code, `--unattended`, `--gate`, and the JSON shape.
