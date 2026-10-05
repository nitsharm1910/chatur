---
id: ADR-0022
title: "`chatur init` project layout and `chatur adr` CLI"
status: Accepted
date: 2026-10-04
deciders: Nitin
phase: design
tags: [cli, init, adr, tracking]
refines: [ADR-0001, ADR-0006, ADR-0011, ADR-0021]
---

# ADR-0022: `chatur init` project layout and `chatur adr` CLI

## Context
ADR-0011 says `chatur init` prepares a target project; ADR-0001 says decisions are ADRs. Both need
an exact, repeatable layout. Roadmap open question 5 (should `standard` commit the audit log?)
also has to be settled here, because `init` writes `.gitignore`.

## Decision

### `chatur init [--root DIR] [--profile P] [--assistants a,b] [--force]`
Creates only what's missing and reports `created` / `skipped` for each path:

```
.chatur/config.toml          # profile, assistants, audit commit policy, gate artifact overrides (commented)
.chatur/policy.local.toml    # valid, empty local policy with commented examples (tighten-only)
docs/decisions/0000-template.md
docs/{requirements,design,decisions,security,test,review,releases}/README.md   # one-line purpose
.gitignore                   # managed block (see below)
```

- **Never overwrites** existing files. `--force` rewrites only `config.toml` and never touches
  `state.json`, the audit log, or docs.
- Validates the composed policy after writing (`load_project_policy`), so a bad profile name fails immediately.
- `--assistants` accepts `claude, copilot` (full support, ADR-0009) and `codex, gemini, cursor`
  (instructions-only until their adapters exist). Default: `claude,copilot`.
- Installing git hooks and CI arrives in Phase 5. Installing primitives is APM's job (`apm install`).

### `config.toml` (`chatur.config/v1`)
```toml
schema = "chatur.config/v1"
[policy]
profile = "standard"
[assistants]
enabled = ["claude", "copilot"]
[audit]
commit = true
```

### Audit log in git (closes roadmap open question 5)
Default `audit.commit`: **`true` for `strict` and `standard`**, `false` for `relaxed`.
The managed `.gitignore` block always ignores `.chatur/audit/.lock` and `.chatur/state.json.tmp`,
and also ignores `.chatur/audit/` when `commit = false`. Rationale: a committed log makes deleting
recent records visible in git history (ADR-0019's limitation).

### `chatur adr new "<title>" [--phase P] [--tags a,b] [--root DIR]`
- Next number = highest `NNNN-*.md` + 1 (the `0000` template is ignored). Filename `NNNN-<slug>.md`,
  slug lower-kebab ASCII ≤ 60 characters.
- Uses the project's `docs/decisions/0000-template.md` if present, else the packaged template.
  Front-matter `id/title/status/date/deciders/phase/tags` and the first `# ADR-…` heading are filled in.
- **Status is always `Proposed`.** Only humans set `Accepted` (ADR-0001); CI enforcement comes in Phase 5.
- `deciders` defaults to the git identity.

### `chatur adr list [--status S] [--json] [--root DIR]`
Parses front matter (a simple `key: value` subset; `# comments` stripped) and prints id, status, title.

## Consequences
- Positive: one command gives any repo the Chatur layout; ADR numbering and format stay consistent.
- Negative: committed audit logs add noise to git history (one file per day; acceptable for traceability).

## Guardrails / best practices this implies
- Tests: idempotent re-run, never-overwrite, `--force` scope, `.gitignore` block per profile, invalid
  profile/assistant rejected, ADR numbering with gaps, slugging, template override, list filters.
