---
id: ADR-0026
title: Claude Code permission modes vs Chatur "ask" (observed)
status: Accepted
date: 2026-10-04
deciders: Nitin
phase: build
tags: [adapter, claude-code, attended]
refines: [ADR-0014, ADR-0025]
---

# ADR-0026: Claude Code permission modes vs Chatur "ask" (observed)

## Context
ADR-0025 deferred the question of which Claude Code permission modes still show the user a prompt
when a PreToolUse hook returns `permissionDecision: "ask"`. Where no prompt appears, `ask` must
become `deny` (ADR-0014).

## Evidence (dogfooding, 2026-10-04)
Chatur hooks were installed locally on this repo (`chatur hooks install claude --local`). In a session
running in **`auto`** mode, Chatur returned `ask` for `chatur audit verify` (audit record with
`permission_mode: "auto"`, decision `ask`), and **the maintainer saw and approved a prompt**.

## Decision
| Mode | Treated as | Basis |
|---|---|---|
| `default`, `plan` | attended | Claude's normal prompting |
| `auto` | **attended** | observed: hook `ask` prompts the user |
| `acceptEdits`, `bypassPermissions` | attended (**unverified**) | to be observed; revisit with a superseding ADR if no prompt appears |
| `dontAsk` | unattended (ask → deny) | the mode suppresses prompts |
| any mode with `CI` / `GITHUB_ACTIONS` set | unattended | no human |

## Consequences
- Auto mode stays usable under Chatur: the agent works autonomously between prompts, and every command and edit still reaches the human.
- `acceptEdits` and `bypassPermissions` need the same observation before v1.0 (Phase 6 checklist).

## Guardrails / best practices this implies
- Adapter tests pin this table (`is_attended`).
