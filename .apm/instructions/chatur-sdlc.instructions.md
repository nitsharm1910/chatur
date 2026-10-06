---
description: Chatur SDLC workflow and guardrails that every agent in this project follows
applyTo: "**"
---

# Chatur SDLC rules

This project is governed by **Chatur**. Its hooks enforce these rules; the git/CI backstop re-checks
them. Work with them, never around them.

## Lifecycle
`requirements → design → build → test → review → release`. Each phase ends with an artifact and a
**human-approved gate**. Check where things stand with `chatur gate status`. Don't start a phase whose
previous gate is not approved; under the strict profile Chatur blocks it.

| Phase | Agent | Artifact | Command |
|---|---|---|---|
| requirements | chatur-product-analyst | `docs/requirements/PRD-*.md` | `/chatur-requirements` |
| design | chatur-architect + chatur-security | `docs/design/`, ADRs, threat model | `/chatur-design` |
| build | chatur-developer | code + unit tests | `/chatur-build` |
| test | chatur-qa | `docs/test/` plan + report | `/chatur-test` |
| review | chatur-reviewer + chatur-security | `docs/review/` | `/chatur-review` |
| release | chatur-devops + chatur-docs | `docs/releases/`, `CHANGELOG.md` | `/chatur-release` |

Templates live in `.chatur/templates/`.

## Always
- Record significant decisions as ADRs: `chatur adr new "<title>"` (Proposed; humans accept).
- Unsure whether an action is allowed? Dry-run it: `chatur check "<command>"` or `chatur check --write <path>`.
- Finish work with a summary and a **suggested commit message**; the human commits.

## Never (Chatur enforces)
- `git commit`, `push`, `merge`, `rebase`, `reset --hard`, `tag`, or any history rewrite; `gh`/`glab`
  PR/release/repo writes. Humans do these.
- Approve or revoke gates (`chatur gate approve|revoke`), or edit `.chatur/state.json` / `.chatur/audit/`.
- Write secrets into files, commands, tool calls, or prompts. Use environment variables.
- Write outside your agent's scope (see each agent's description).

Every command and file change asks the human for approval. When Chatur denies something, explain why you
needed it and propose an alternative; never try to bypass the guardrail.
