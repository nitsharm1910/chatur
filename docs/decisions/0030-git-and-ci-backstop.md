---
id: ADR-0030
title: Git and CI backstop — pre-commit, pre-push, ci-check
status: Accepted
date: 2026-10-12
deciders: Nitin
phase: design
tags: [backstop, git, ci, guardrails]
implements: ADR-0005
refines: [ADR-0006, ADR-0008, ADR-0014, ADR-0019, ADR-0021, ADR-0023, ADR-0029]
---

# ADR-0030: Git and CI backstop

## Context
ADR-0005 requires every critical guardrail to be enforced by at least one layer outside the assistant.
Until now only the in-session hook layer existed: a human or tool committing a secret, a hand-edited
`state.json`, or a commit from an agent shell in an assistant without hooks went unnoticed.

In-session rules can't simply be re-run at commit time because their meaning changes. For example,
`gate.state-protected` stops an *agent* touching `state.json`, but a *human* committing it after
approving a gate is correct. So the backstop has **explicit checks**, each declaring the rules it backs.

## Decision (maintainer choices marked ★)

### Checks
| Check | pre-commit | pre-push | ci-check | Backs |
|---|---|---|---|---|
| ★ **agent-session**: committer env has an agent marker (`CHATUR_AGENT_SESSION`, `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `COPILOT_AGENT_ID`) | block | block | — | `git.no-commit-push` |
| ★ **secrets**: added lines scanned (`find_secrets`, placeholders ignored) | token block / credential warn | same (pushed commits) | same (base…head) | `secrets.known-token`, `secrets.credential-shape` |
| ★ **governance**: audit chain intact; policy valid; every approval in `state.json` has a matching audit `gate` record (approved_at + artifact digest); anchors present | block | block | block | `gate.state-protected`, `harness.read-only` |
| **stale gates** | warn | warn | **block** | ADR-0021 |
| ★ **process** (profile-driven): synthetic events over changed paths evaluated against `test.missing-tests`, `deps.needs-adr`, `gate.design-before-code`, `fs.protected-paths`; deny → block, ask/warn → warn | yes | — | yes | those rules |
| **history-rewrite**: push whose `before` isn't an ancestor of `after` (force push) | — | — | block | `git.no-history-rewrite` |
| **harness tooling committed** (force-added gitignored copies) | warn | — | warn | ADR-0029 |
| ★ **AI trailers**: `Co-Authored-By:` an AI without `Approved-by:` | — | — | **warn** | ADR-0014 |

The process check derives git facts: *missing tests* = code files changed and no test files changed (test
globs = the `chatur-qa` scope); *ADR changed* = a non-template file under `docs/decisions/` changed;
approved gates come from `state.json`.

A coverage test requires every rule marked `critical` with a `git` or `ci` layer to be backed by a check.

### Installation
- ★ `chatur git-hooks install [--force] [--shared]` writes `.git/hooks/pre-commit` and `pre-push` (POSIX sh,
  which Git for Windows also runs) that `exec` this interpreter's `-m chatur git-hook <name>` (or `chatur`
  from PATH with `--shared`). It refuses to overwrite a non-Chatur hook, or to install when `core.hooksPath`
  is set, unless `--force`. `uninstall` removes only Chatur-managed hooks.
- ★ `.pre-commit-hooks.yaml` (repo root) provides `chatur-pre-commit` and `chatur-pre-push` for teams using the pre-commit framework.

### CI
- `chatur ci-check [--base REF] [--head REF] [--before SHA]` runs in any CI: exit 1 on any block. On
  GitHub it also writes `::error`/`::warning` annotations and a `$GITHUB_STEP_SUMMARY` table.
- ★ GitHub: a composite action `action.yml` at the repo root (`uses: nitsharm1910/chatur@<tag>`), with inputs
  passed through environment variables (no expression injection), and `chatur ci install github` to write
  `.github/workflows/chatur.yml` (a human runs it; workflows are protected paths).

## Consequences
- Positive: critical guardrails now hold for any committer and any assistant; CI is the non-bypassable final gate.
- Negative: native hooks can be skipped locally (`git commit --no-verify`); CI is the authoritative layer for that
  reason. Stale gates fail CI until re-approved; that's intended (approvals bind to content), but teams must
  re-approve after changing approved artifacts.

## Guardrails / best practices this implies
- Real-git tests for every check (block and pass cases), hook install/uninstall safety, an end-to-end blocked commit, and critical-rule coverage.
