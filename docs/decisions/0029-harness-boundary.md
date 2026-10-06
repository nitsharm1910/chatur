---
id: ADR-0029
title: Harness boundary — Chatur files are read-only for agents; installed tooling is gitignored
status: Accepted
date: 2026-10-05
deciders: Nitin
phase: design
tags: [guardrails, baseline, gitignore, separation]
amends: [ADR-0007, ADR-0022, ADR-0027, ADR-0028]
---

# ADR-0029: Harness boundary

## Context
In a target project, Chatur's files (its config, gate state, audit log, installed agents, commands,
skills, rules, templates, and hook settings) are the **harness**, not the product being built. The
maintainer wants them read-only for agents and kept out of the product's git history where possible.
Agents editing harness files could weaken the guardrails themselves, for example by changing hooks or
editing an agent definition to widen its own scope.

## Decision (maintainer choices marked ★)

### 1. Read-only for agents — new baseline rule `harness.read-only` (deny, all profiles, critical)
File writes **and** shell commands that touch any of:
```
.chatur/**                                  (config, local policy, state, audit, templates)
.claude/settings.json  .claude/settings.local.json   (hooks + native deny rules)
.claude/agents/chatur-*      .claude/commands/chatur-*
.claude/skills/chatur-*/**   .claude/rules/chatur-*
.claude/.chatur-primitives.json
```
are denied. As with all path rules (ADR-0017), any shell mention counts, including parent
directories (`rm -rf .claude` is denied). Reading through the assistant's Read tool stays allowed, so
skills and templates still work. Only humans change the harness (and `chatur` CLI commands a human approves).
This **replaces** the `ask`/`warn` treatment of `.chatur/config.toml`, `.chatur/policy.local.toml`, and
`.claude/settings*.json` in the profiles' `fs.protected-paths` (now baseline deny).
A project's **own** agents and commands (without the `chatur-` prefix) are unaffected.

### 2. ★ Gitignore — tooling only
The managed `.gitignore` block (written by `chatur init`, `chatur primitives install`, and
`chatur hooks install --local`) ignores the regenerable copies:
```
.claude/agents/chatur-*   .claude/commands/chatur-*   .claude/skills/chatur-*/   .claude/rules/chatur-*
.claude/.chatur-primitives.json   .claude/settings.local.json   .chatur/templates/
.chatur/audit/.lock   .chatur/state.json.tmp
```
**Governance records stay committed:** `.chatur/config.toml`, `.chatur/policy.local.toml`,
`.chatur/state.json`, `.chatur/audit/` (unless `audit.commit = false`), ADRs, and phase artifacts.
CI gate verification (Phase 5) and tamper evidence (ADR-0019) depend on them. Each clone runs
`chatur primitives install claude` once.

### 3. ★ Templates are harness-owned → moved to `.chatur/templates/`
`chatur init` installs templates to `.chatur/templates/` (gitignored, agent-read-only) instead of
`docs/templates/` (amends ADR-0022/0027). Rationale for the location: protecting `docs/templates/`
would make `docs` a protected parent and deny ordinary commands like `ls docs`. Primitives reference
`.chatur/templates/<name>.md`. Project-specific template overrides are a follow-up (human-maintained,
committed; not yet built).

## Consequences
- Positive: agents can't tamper with their own guardrails or definitions; product history stays clean of regenerable tooling.
- Negative: a fresh clone needs `chatur primitives install` before the agents and commands appear; shell commands that merely mention harness paths are denied (use the Read tool, or `chatur` commands).

## Guardrails / best practices this implies
- Tests: deny for each harness path (write and shell, including parent directories); no false denial for
  `ls docs`, project-owned agents, or phase artifacts; gitignore block contents; init writes templates to `.chatur/templates/`.
