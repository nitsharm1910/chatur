---
id: ADR-0034
title: Keep the core rule unscoped, and allow read-only git tag and reflog
status: Accepted
date: 2026-11-04
deciders: Nitin
phase: build
tags: [primitives, guardrails, git, compaction]
amends: [ADR-0014, ADR-0025, ADR-0028]
---

# ADR-0034: Keep the core rule unscoped, and allow read-only git tag and reflog

## Context
Two defects found on 2026-11-04, fixed before tagging 0.9.0 (maintainer's choice):
1. `chatur primitives install` turned the core rule's `applyTo: "**"` into `paths: ["**"]`. Claude Code loads path-scoped
   rules into message history, and compaction summarises them away. Unscoped rules are re-injected from disk.
2. `git.no-history-rewrite` denied every `git tag` and `git reflog`, including read-only forms such as `git tag --list`.
   The native rule `Bash(git tag *)` denied them too, and native rules can't tell reading from writing.

## Decision
1. **Rule conversion:** when every `applyTo` pattern is `**`, the Claude rule has no `paths:`. Narrower patterns still become
   `paths:`. The source keeps `applyTo: "**"`, because Copilot receives that file unchanged.
2. **Read-only git forms go to `ask`, like any other command (ADR-0014):**
   - `git tag` is denied **unless** its arguments match a known read-only shape: no arguments, list/format flags, or
     `-l`/`--list` with name patterns. Anything else stays denied, so unrecognised forms fail safe.
   - `git reflog` is denied only for `expire`, `delete`, and `drop`. Other forms only read.
3. **Native deny rules:** the broad `git tag` rule is replaced by its write flags (`-a`, `-d`, `-f`, `-s` and long forms).

## Consequences
- Positive: core rules survive compaction and stay in the cached project context; agents can inspect tags and the reflog with approval.
- Negative: **if Chatur isn't running**, native rules no longer stop a plain `git tag v1`. That tag stays local because
  `git push` is still denied natively, and the hook denies it whenever Chatur runs.
- The APM channel may still produce `paths: ["**"]`. To check when APM is available (roadmap 2.7).
- Existing installs need `chatur primitives install` and `chatur hooks install` again.

## Guardrails / best practices this implies
- Tests: rule conversion with `**` and with narrower patterns; bypass suite cases for each read-only form (ask) and each write form (deny), including nested shells and chained commands.
