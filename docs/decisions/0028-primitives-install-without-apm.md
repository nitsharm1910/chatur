---
id: ADR-0028
title: "`chatur primitives install` — a second channel for agents, commands, skills, rules"
status: Proposed
date: 2026-10-05
deciders: Nitin (pending)
phase: design
tags: [install, primitives, apm, claude-code]
refines: [ADR-0003, ADR-0011, ADR-0025, ADR-0027]
---

# ADR-0028: `chatur primitives install`

## Context
ADR-0003 makes APM the distribution channel for `.apm/` primitives, but APM isn't always installed
(it isn't on the maintainer's machine). ADR-0025 already gave hooks a second channel
(`chatur hooks install`). Agents, commands, skills, and rules need the same so that `pip install chatur`
alone can set a project up, and so the Phase 3 primitives can be exercised end-to-end now.

## Decision
1. **Ship the primitives in the wheel:** `.apm/` is force-included as `chatur/_primitives/`. In a source
   checkout (editable install) the repo's `.apm/` is used directly. APM remains the primary channel.
2. **`chatur primitives install|uninstall claude [--root DIR] [--force]`** writes, mirroring APM's Claude target:

| Source | Claude target | Transformation |
|---|---|---|
| `agents/<n>.agent.md` | `.claude/agents/<n>.md` | verbatim |
| `prompts/<n>.prompt.md` | `.claude/commands/<n>.md` | front matter → `description`, `argument-hint` (from `input`), `allowed-tools`, `model`; `${input:x}` → `$ARGUMENTS` (one input) or `$1…$n` |
| `skills/<n>/**` | `.claude/skills/<n>/**` | verbatim (incl. `assets/`) |
| `instructions/<n>.instructions.md` | `.claude/rules/<n>.md` | `applyTo` → `paths: [...]` |

   Hooks stay with `chatur hooks install` (ADR-0025).
3. **Ownership manifest** `.claude/.chatur-primitives.json` records `{path: sha256}` for every file Chatur wrote:
   - re-install updates files that are unmodified since Chatur wrote them, and removes files that are stale (no longer shipped);
   - files **changed by the user** or **not created by Chatur** are never overwritten (reported as skipped) unless `--force`;
   - `uninstall` removes only unmodified files Chatur created.

## Consequences
- Positive: Chatur sets up a project fully without APM; idempotent and safe around user edits.
- Negative: two channels can diverge from APM's own transformation; mitigated by mirroring APM's documented
  mapping and testing it. If both are used in one project, prefer one (APM's sidecar vs Chatur's manifest).

## Guardrails / best practices this implies
- Tests: every mapping row, idempotency, user-modified and foreign files preserved, `--force`, stale removal,
  uninstall precision, and a packaging check that the wheel contains `chatur/_primitives/`.
