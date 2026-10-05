---
id: ADR-0027
title: SDLC primitives — agents, write scopes, commands, skills, templates
status: Accepted
date: 2026-10-04
deciders: Nitin
phase: design
tags: [agents, primitives, apm, scopes, templates]
refines: [ADR-0003, ADR-0010, ADR-0016, ADR-0022]
---

# ADR-0027: SDLC primitives

## Context
APM copies `.agent.md` files **verbatim** to Claude (`.claude/agents/`) and Copilot
(`.github/agents/`), whose `tools:`/`model:` vocabularies differ. Prompts become slash commands
everywhere (file name = command name); only `description`, `input`, `allowed-tools`, `model`,
`argument-hint` survive. Skills deploy to `.claude/skills/` and `.agents/skills/`.

## Decision (maintainer choices marked ★)

### Agents — ★ least privilege enforced by Chatur, not frontmatter
Nine `.apm/agents/chatur-<role>.agent.md` files with `name` + `description` only (no `tools:`/`model:`
— they inherit, so the same file works in every assistant). Names are prefixed `chatur-` to avoid
colliding with a project's own agents.

Write scopes live in the **baseline policy** `[agents.<name>]` table and are enforced by the guard
using the agent identity the assistant reports (Claude `agent_type`):

| Agent | Writes (globs) | Excludes |
|---|---|---|
| `chatur-orchestrator` | — **read-only** | |
| `chatur-reviewer` | — **read-only** (findings are returned; `/chatur-review` saves them) | |
| `chatur-product-analyst` | `docs/requirements/**` | |
| `chatur-architect` | `docs/design/**`, `docs/decisions/**` | |
| `chatur-security` | `docs/security/**` | |
| `chatur-qa` | `tests/**`, `test/**`, `**/__tests__/**`, `**/*_test.*`, `**/*.test.*`, `**/*.spec.*`, `**/test_*.py`, `docs/test/**` | |
| `chatur-developer` | `**` | `docs/**`, `.github/workflows/**`, `.chatur/**`, `CHANGELOG.md` |
| `chatur-devops` | `.github/workflows/**`, `ci/**`, `deploy/**`, `infra/**`, `Dockerfile*`, `docker-compose*`, `docs/releases/**` | |
| `chatur-docs` | `README.md`, `CHANGELOG.md`, `docs/**` | `docs/{requirements,design,decisions,security,test,review,releases}/**` |

**Policy schema addition** (amends ADR-0016): `[agents.<name>]` with `read_only` (bool), `write`, `exclude`
(glob lists). Baseline defines Chatur's agents; profiles/local may **add** scopes for new agent names but
never modify existing ones (tighten-only). New selectors `read_only_agent` and `outside_agent_scope`
apply to **file_write** events (shell writes can't be attributed to paths reliably — they remain `ask`
under ADR-0014).

★ **Strictness:** baseline `agent.read-only` = **deny** (all profiles); profile `agent.write-scope` =
**deny** in strict, **ask** in standard and relaxed. Events without a known Chatur agent (main session,
a project's own agents) are unaffected.

### Commands — ★ per phase + helpers
`.apm/prompts/`: `chatur-status`, `chatur-requirements`, `chatur-design`, `chatur-build`, `chatur-test`,
`chatur-review`, `chatur-release`, `chatur-adr`, `chatur-check`. Each phase command: checks
`chatur gate status`, delegates to the owning agent(s), writes the exit artifact from the template, and
**ends by telling the human the exact `chatur gate approve <phase>` command** (agents can't run it — ADR-0008/0021).

### Skills
`.apm/skills/chatur-{write-prd,design-doc,threat-model,test-plan,code-review,release-notes,adr}/SKILL.md`,
each with `assets/template.md`.

### Templates — ★ one source, two channels
Source: `src/chatur/templates/{prd,design,threat-model,test-plan,test-report,review,release-notes}.md`
(+ existing `adr.md`). `chatur init` copies them to `docs/templates/`; skills ship the same file in
`assets/`. A drift test keeps copies identical.

### Instructions
`.apm/instructions/chatur-sdlc.instructions.md` (`applyTo: "**"`): the workflow and guardrails every
agent follows (phases, gates, ADRs, no commit/push, no secrets, `chatur check`).

## Consequences
- Positive: one set of primitives for every assistant; privilege enforced uniformly and audited.
- Negative: scope enforcement depends on the assistant reporting agent identity (Claude does; Copilot TBD in
  Phase 4); file-write only.

## Guardrails / best practices this implies
- Primitive lint tests: required frontmatter, only preserved prompt keys, skill name/size rules, every
  agent has a scope entry and vice versa, every phase command names its `chatur gate approve` step,
  template drift.
- Scope tests per agent: an in-scope write passes scope rules; an out-of-scope write asks/denies; read-only agents denied.
