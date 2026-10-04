---
id: ADR-0018
title: Deny remote-write CLIs (gh, glab, hub) and add the argv_patterns selector
status: Accepted
date: 2026-10-04
deciders: Nitin
phase: design
tags: [guardrails, baseline, git, policy]
amends: [ADR-0014, ADR-0016]
---

# ADR-0018: Deny remote-write CLIs and add the `argv_patterns` selector

## Context
ADR-0014 reserves remote repository writes for humans, but it only covered `git` and MCP tools.
The GitHub CLI (`gh`), GitLab CLI (`glab`), and `hub` can merge PRs, publish releases, delete
repos, set secrets, and call write APIs. Under ADR-0014 they were only `ask`. The maintainer decided
these must be **denied** like `git push`.

Matching them with raw-text `shell_patterns` would wrongly deny harmless text such as
`echo "gh pr merge"`. The engine already extracts each real command's argv (ADR-0017), so rules
should be able to match on that.

## Decision
1. **New selector `argv_patterns`** (amends ADR-0016): regexes searched case-insensitively against each
   analysed command, rendered as `<basename> <args…>` after wrappers are stripped and nested shells
   are expanded (`sudo gh pr merge 1` → `gh pr merge 1`). It's additive: schema stays `chatur.policy/v1`.
   Interpreter one-liners and unparseable text are covered by the heuristic scan, extended from
   `git` to `gh`/`glab`/`hub`.
2. **`hub` is treated as git** for subcommand detection (`hub push` → `push`).
3. **New baseline rule `git.remote-cli`** (deny in all profiles, unattended deny). It covers:

| CLI | Denied operations |
|---|---|
| `gh` | `pr create/merge/close/reopen/edit/ready/review/comment/lock/unlock`; `issue create/close/reopen/edit/delete/comment/transfer/lock/unlock/pin/unpin`; `release create/delete/edit/upload/delete-asset`; `repo create/delete/edit/rename/archive/unarchive/sync/fork`; `secret set/delete`; `variable set/delete`; `workflow run/enable/disable`; `run cancel/rerun/delete`; `label create/edit/delete/clone`; `gist create/edit/delete`; `cache delete`; `api` with `-X/--method POST|PUT|PATCH|DELETE` or with body flags (`-f/-F/--field/--raw-field/--input`, which make gh use POST) |
| `glab` | `mr create/merge/close/reopen/update/approve/note`; `issue create/close/reopen/update/delete/note`; `release create/delete/upload`; `repo create/delete/fork/archive`; `variable set/update/delete`; `ci run/retry/delete/cancel`; `api` with a write method or body flags |
| `hub` | `pull-request`, `merge`, `release create/edit/delete`, `create`, `delete`, `fork`, `api` with write method (plus `push` etc. via git detection) |

Read operations (`gh pr view`, `gh issue list`, `gh run view`, `glab mr list`, `gh api` GETs) stay at `ask` (ADR-0014 exec rule).

## Consequences
- Positive: an agent can't change the remote through any supported git-hosting CLI.
- Negative: agents can't open PRs or comment on issues; they draft the PR body and a human runs `gh pr create`.
- Layers: hook only. git hooks and CI can't see CLI calls; GitHub branch protection and required reviews remain the server-side backstop.

## Guardrails / best practices this implies
- Bypass tests for each CLI (wrappers, nested shells, encoded commands, interpreter one-liners) plus no-false-deny tests for read operations and quoted text.
