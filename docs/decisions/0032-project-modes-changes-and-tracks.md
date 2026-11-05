---
id: ADR-0032
title: Project modes (greenfield/brownfield), baseline onboarding, per-change gates, and tracks
status: Proposed
date: 2026-10-13
deciders: Nitin (pending)
phase: design
tags: [gates, sdlc, brownfield, workflow, state]
refines: [ADR-0008, ADR-0021, ADR-0022, ADR-0027, ADR-0029, ADR-0030]
---

# ADR-0032: Project modes, baseline onboarding, per-change gates, and tracks

## Context
Chatur's installation is brownfield-safe, but its workflow is greenfield-only:
- **one set of gates per repository** (`state.json` keyed by phase), so concurrent changes are impossible
  and every change after the first release makes the approved gates stale;
- **every change takes all six phases**, so a one-line bug fix needs a PRD and a design;
- **`gate.design-before-code` covers all of `src/**`**, so in `strict` no existing code can be fixed until a
  project-wide design is approved;
- **no onboarding**: nothing captures the existing system, so agents start without context;
- `chatur init` doesn't recognise an existing codebase.

The maintainer also wants a brownfield option that **duplicates the existing app** so agents refactor a
copy while the original stays untouched as the reference.

## Decision (maintainer choices marked ★)

### 1. Project mode
`.chatur/config.toml`:
```toml
[project]
mode = "brownfield"            # "greenfield" | "brownfield"
source = "C:/work/legacy-app"  # brownfield: the original (read-only for agents)
strategy = "worktree"          # worktree | clone | copy | in-place
source_ref = "<commit sha>"    # the original's HEAD when duplicated (git strategies)
```
`chatur init` suggests the mode: existing commits or source files → brownfield, otherwise greenfield.

### 2. ★ Brownfield duplication: `chatur init --brownfield --source <dir> [--target <dir>] [--strategy …]`
| Strategy | What happens | Use when |
|---|---|---|
| **worktree** (default when the source is a git repo) | `git worktree add -b chatur/<name> <target>`: same repository, new branch, separate folder; history kept, diff/merge back is ordinary git | the source is a git repo |
| **clone** | `git clone --no-hardlinks <source> <target>`: an independent repository with full history | you want a fully separate repository |
| **copy** | copies files (skipping `.git`, `node_modules`, `.venv`, build output), then `git init` in the target | legacy code without git |
| **in-place** | no duplicate; Chatur is set up in the source itself | you want to govern the existing repo directly |

Then `init` sets up `.chatur/` in the **target**. Chatur never commits: for `copy`, the human makes the
first commit of the snapshot. Default target: a sibling `<source>-chatur`.
New baseline rule **`project.source-read-only`** (deny): agent file writes and shell commands touching the
recorded `source` path. The original is the untouched reference. (`in-place` has no separate source.)

### 3. ★ Baseline onboarding gate (brownfield, project-level, once)
`/chatur-baseline` → artifacts in `docs/baseline/`, approved with `chatur gate approve baseline`.
No change can start until it's approved.
| Artifact | Agent |
|---|---|
| `architecture.md`: system overview, components, data flow, entry points, build/run | chatur-architect |
| Retroactive ADRs (front matter `retroactive: true`) for decisions already embedded in the code | chatur-architect |
| `risks.md`: current threat model, security issues, tech debt, fragile areas | chatur-security |
| `test-inventory.md`: what's covered by tests and what isn't, and how to run them | chatur-qa |
| `dependencies.md`: dependencies, versions, licences | chatur-devops |

Agent write scopes gain these exact paths.

### 4. ★ Changes: the unit with its own gates
- A **human** runs `chatur change start <name> --track <track>`. This creates `docs/changes/<id>/`
  (`<id>` = `NNNN-<slug>`), records the **current branch**, and marks the change active for that branch.
  Agents can't start, switch, close, or approve changes (baseline deny, like `gate.no-agent-approval`).
- `chatur change list|status|close <id>`; `chatur gate approve <phase> [--change <id>]` (defaults to the
  change bound to the current branch; `baseline` is project-level).
- Artifacts per change: `docs/changes/<id>/{prd|bug-report,design,threat-model,test-plan,test-report,review,release-notes}.md`.
- **The build and test gates bind to a commit** (the branch HEAD sha at approval) plus the change's docs,
  instead of a digest of all of `src/**`. A gate is stale only if the change's own docs change, or if its
  branch gets new code commits after approval. **Closed changes aren't re-checked**, so later work no
  longer invalidates earlier approvals.
- CI (`ci-check`) finds the change from the PR branch (`GITHUB_HEAD_REF`) and verifies that change's gates.
- **Greenfield uses changes too.** The first is a `feature` change named `initial`. Existing v1 state
  migrates automatically: v1 gates become the `initial` change (state schema `chatur.state/v2`).

### 5. ★ Tracks
| Track | Phases | Notes |
|---|---|---|
| **feature** | requirements → design → build → test → review → release | today's lifecycle |
| **bugfix** | requirements (bug report + reproduction) → build → test → review | `bug-report.md` replaces the PRD |
| **refactor** | design → build → test → review | behaviour must not change: the test report must show the same suite passing before and after |
| **hotfix** | build → review | `chatur change close` refuses until a follow-up `bugfix` change links to it; **denied in strict** |

Profiles decide which tracks are allowed (`[tracks] allowed = [...]`): strict = feature, bugfix,
refactor; standard and relaxed = all four. Tighten-only (ADR-0016): local policy can remove tracks, never add them.

### 6. Scoped design rule
`gate.design-before-code` becomes **"code changes need the active change's pre-build gates"**:
- the active change (bound to the current branch) has all phases **before build** in its track approved →
  code writes allowed (subject to the other rules, e.g. ADR-0014 asks);
- otherwise → the profile's verdict (strict deny, standard warn);
- **no active change** on a brownfield project → strict deny, standard warn ("start a change first").

The hook finds the current branch by reading `.git/HEAD` directly (worktree-aware; no subprocess; stays in
the ADR-0012 budget).

## Consequences
- Positive: real projects with concurrent work, small fixes, refactors, and legacy code can follow Chatur
  without fighting it; the original app stays pristine; approvals stop going stale for unrelated work.
- Negative: **breaking** changes to the state schema (v1 → v2, migrated automatically), gate CLI defaults, and
  CI gate checks: released as **0.10.0** (allowed in 0.x by ADR-0031). More concepts for users (mode, change, track).

## Open questions (to settle before or during implementation)
1. Should merging a change's branch close the change automatically (detected in CI on `main`), or is closing always manual?
2. `copy` strategy: is the default exclusion list right, and should `.gitignore`d files be skipped too?
3. Can a greenfield project skip the `initial` feature change, e.g. for a prototype under `relaxed`?

## Guardrails / best practices this implies
- Tests: mode detection; every duplication strategy (including refusal when the target exists and source
  untouched afterwards); the source-read-only rule (writes and shell, absolute and relative); the baseline gate
  blocking `change start`; each track's phase order; strict denying hotfix; the scoped design rule (active
  change approved / not approved / none); build gates bound to commits (stale only on new code commits); v1 → v2
  migration; CI finding the change by branch; agents denied every `chatur change` mutation.
