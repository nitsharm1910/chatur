# Command reference

Every command accepts `--help`. Commands that act on a project take `--root DIR` (default: the current
directory). This page is checked by a test: every CLI command must be listed here.

## Everyday

### `chatur check`
Dry-run one action against the project policy; nothing executes and nothing is logged (ADR-0020).
```bash
chatur check "git push --force"            # shell command
chatur check --write src/app.py            # file write
chatur check --read .env                   # file read
chatur check --tool WebFetch --category web
chatur check "git status" --unattended     # as if no human could answer (ask -> deny)
chatur check --write src/x.py --profile strict --gate design   # what-if
```
Exit codes: `0` allow/log/warn · `2` ask · `3` deny · `1` error. `--json` prints every matching rule.

### `chatur gate status | approve | revoke | verify`
SDLC gates (ADR-0021). `status` shows approved / stale / pending per phase. `approve <phase>` and
`revoke <phase>` are **human-only**: they need an interactive terminal, refuse inside agent or CI sessions,
show what will change, and ask you to type the phase name. `revoke` also removes every later gate.
`verify` exits 1 on stale gates, out-of-order approvals, or missing audit anchors (for CI).

### `chatur adr new | list | supersede`
Architecture Decision Records (ADR-0022, ADR-0024).
```bash
chatur adr new "Use PostgreSQL for orders" --phase design --tags db
chatur adr new "Use CockroachDB" --supersedes 7       # draft a replacement
chatur adr list --status proposed
chatur adr supersede 7 --by 12                        # after a human accepted ADR-0012
```

### `chatur audit verify | tail`
`verify` checks the hash chain and exits 1 on tampering; `tail [-n N] [--json]` shows recent records.

### `chatur policy validate | show`
`validate` checks policy files and exits 1 on any problem; `show [--profile P] [--json]` prints the
composed policy (baseline → profile → local).

## Setup

### `chatur init`
`chatur init [--profile strict|standard|relaxed] [--assistants claude,copilot,...] [--force]`.
Creates `.chatur/`, the phase folders, templates, and the `.gitignore` block; never overwrites existing
files (`--force` rewrites only `.chatur/config.toml`).

### `chatur hooks install | uninstall | print`
`chatur hooks install claude [--local]` merges Chatur's hooks and native `permissions.deny` rules into
`.claude/settings.json` (or `settings.local.json` with `--local`, which uses this machine's interpreter
path). `uninstall` removes only Chatur's entries. `print [--apm]` shows the hook JSON.

### `chatur primitives install | uninstall`
`chatur primitives install claude [--force]` copies Chatur's agents, commands, skills, and rules into
`.claude/` (ADR-0028). Files you edited, or files Chatur didn't create, are never overwritten without
`--force`. `uninstall` removes only unmodified files Chatur installed.

### `chatur git-hooks install | uninstall`
Writes `.git/hooks/pre-commit` and `pre-push` (ADR-0030). It won't replace another tool's hooks or work
under a custom `core.hooksPath` without `--force`; use the pre-commit framework entries instead
(`chatur-pre-commit`, `chatur-pre-push`). `--shared` calls `chatur` from PATH instead of this interpreter.

### `chatur ci install github`
Writes `.github/workflows/chatur.yml`, which runs the reusable action on pushes and PRs.

## Called by tools (you rarely run these)

### `chatur hook <adapter> [EVENT]`
The assistant hook entrypoint. Reads the native payload on stdin and answers in the assistant's format.
Fails closed on pre-tool events (ADR-0025).

### `chatur git-hook pre-commit | pre-push`
The backstop entrypoint called by `.git/hooks/*`. Exit 1 blocks the commit or push.

### `chatur ci-check`
`chatur ci-check [--base REF] [--head REF] [--before SHA]`. The CI backstop: governance, stale gates
(blocking), secrets and process rules over `base...head`, history rewrites, and AI trailers. On GitHub
it adds annotations and a step summary.
