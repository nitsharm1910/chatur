---
id: ADR-0017
title: Guard engine matching semantics and shell bypass handling
status: Accepted
date: 2026-10-03
deciders: Nitin
phase: design
tags: [guard, shell, security]
refines: [ADR-0014, ADR-0016]
---

# ADR-0017: Guard engine matching semantics and shell bypass handling

## Context
ADR-0016 defines *what* a rule matches (selectors, conditions). The engine still needs exact
semantics for paths, case, and shell parsing. Shell commands are the main bypass surface:
quoting tricks, nested shells, PowerShell/cmd escape characters, encoded commands.

## Decision

### Paths (`path_globs`)
- Paths are normalised before matching: `\` → `/`; made relative to the project root (or event
  `cwd`); `./` and `..` collapsed (`src/../.chatur/state.json` → `.chatur/state.json`).
- **Case-insensitive** everywhere, because Windows and macOS file systems are, and `.Chatur\State.json` must not slip through.
- Glob syntax: `*` matches within one path segment, `**` matches across segments, `?` matches one character.
  A pattern **without `/`** matches the basename at any depth (gitignore-style: `*.sh`, `pyproject.toml`).
- **Ancestor rule:** a path that is a parent directory of a protected pattern matches it
  (`rm -rf .chatur` hits `.chatur/state.json`). A shell token containing wildcards matches if it
  could expand to a protected path (`rm .chat*/state.json`, `rm -rf .*`). `.` and `/` alone are
  excluded, so `ls .` isn't denied; deleting those is still `ask` (ADR-0014) and caught in git/CI.
- For shell commands, every non-flag argument and every write-redirect target counts as a candidate path.
  The engine can't tell reading from writing in arbitrary commands, so protected paths are protected
  from **any** shell mention (agents read gate state through `chatur gate status`).

### Regexes
`shell_patterns`, `git_patterns`, and `tool_name_patterns` are matched **case-insensitively**
(PowerShell is case-insensitive).

### Shell analysis (conservative)
The analyser looks at the command in three readings and acts on the **union** of what it finds:
1. as written (bash rules);
2. with PowerShell backtick escapes removed (``git com`mit`` → `git commit`);
3. with cmd caret escapes removed (`g^it com^mit` → `git commit`).

For each reading it:
- splits on unquoted `; && || | & ( ) { }` and newlines;
- extracts write redirects (`>`, `>>`, `>|`, `N>`);
- recurses (max depth 5) into `$(…)`, `` `…` ``, `<(…)`, `sh|bash|zsh|… -c`, `cmd /c|/k`,
  `powershell|pwsh -Command`, **`-EncodedCommand`** (base64 UTF-16LE is decoded), `eval`,
  `Invoke-Expression`/`iex`, and `Start-Process … -ArgumentList`;
- strips wrappers and environment assignments (`sudo`, `env`, `nohup`, `time`, `timeout N`, `nice`,
  `xargs`, `command`, `exec`, PowerShell `&`, `X=1 cmd`);
- identifies git by basename (`/usr/bin/git`, `"C:\…\git.exe"`, `GIT.EXE`), skips git's global options
  (`-C`, `-c`, `--git-dir=`, `--no-pager`, …) to find the real subcommand;
- for interpreter one-liners (`python -c`, `node -e`, …) and unparseable text, runs a **heuristic
  git scan** of the raw text.

### What counts as unparseable → `defaults.unparseable_command` (ask)
Unbalanced quotes, recursion beyond depth 5, an undecodable `-EncodedCommand`, a dynamic command name
(`$G commit`, `$(echo git) push`), and git config overrides that redefine behaviour
(`-c alias.*`, `-c core.hooksPath=…`).

### Conditions context
`requires_gate`, `requires_adr`, and `missing_tests` are evaluated against a `GuardContext` supplied by
the caller (gate state from Phase 1.6; git diff facts from the git/CI layers). The engine itself does
no I/O.

### Read-only allowlist
When enabled (baseline only, ADR-0014), it suppresses only the `any` selector for a **simple** command:
one segment, no redirects, no nesting, parseable. Every other rule still applies.

## Known limitations (handled by other layers)
- Repo-level git aliases (`git ci` defined in `.git/config`), commands hidden inside scripts or
  Makefiles, and values computed at runtime can't be resolved statically. These are `ask` in-session
  (every command needs approval), and the **git pre-commit/pre-push backstop and CI** (ADR-0005)
  block the outcome.
- Remote-write CLIs (`gh pr merge`, `gh release create`, `glab`): resolved by ADR-0018 (deny).

## Consequences
- Positive: common bypasses are denied, and anything the analyser doesn't understand falls back to a human.
- Negative: some false positives (e.g. `ls .chatur` is denied by `gate.state-protected`). They're accepted
  as the cost of a protective baseline.

## Guardrails / best practices this implies
- Every bypass technique listed here has a test in `tests/test_guard_bypass.py`; a newly found bypass
  gets a failing test first.
- A coverage test makes sure every rule in every shipped profile is triggered by at least one test (AGENTS.md rule 5).
