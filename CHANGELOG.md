# Changelog

All notable changes to Chatur are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). In 0.x, a minor release may change public interfaces;
every such change is recorded in an ADR and listed under **Changed/Breaking** (ADR-0031).

## [Unreleased]

## [0.9.0] - 2026-10-12

First public release. Full support for **Claude Code**; GitHub Copilot follows in 1.0.

### Added
- **Policy engine** with a non-weakenable baseline and three profiles (`strict`, `standard`, `relaxed`);
  tighten-only project overrides in `.chatur/policy.local.toml` (ADR-0007, ADR-0014, ADR-0016).
- **Shell analysis** that sees through nested shells, encoded PowerShell, substitutions, wrappers, and
  quoting/escape tricks; ~140 bypass tests (ADR-0017).
- **Human-in-the-loop baseline:** agents can't commit, push, rewrite history, or use `gh`/`glab`/`hub`
  remote writes; every command and file change needs approval (ADR-0014, ADR-0018).
- **Secret detection** in file writes, commands, tool arguments, and prompts: tokens denied, credential
  shapes asked, prompts warned (ADR-0023).
- **Hash-chained, redacted audit log** with `chatur audit verify|tail` (ADR-0006, ADR-0015, ADR-0019).
- **Human-approved phase gates** bound to artifact digests and audit anchors: `chatur gate
  status|approve|revoke|verify` (ADR-0008, ADR-0021).
- **Claude Code adapter:** fail-closed hooks, native `permissions.deny` backstop, `chatur hooks install`
  (ADR-0025, ADR-0026).
- **SDLC primitives:** 9 agents with enforced write scopes, 9 `/chatur-*` commands, 7 skills, 8 templates
  (ADR-0027); `chatur primitives install` without APM (ADR-0028).
- **Harness boundary:** Chatur's files are read-only for agents; regenerable tooling is gitignored (ADR-0029).
- **Git and CI backstop:** `chatur git-hook`, `chatur git-hooks install`, `chatur ci-check`, a reusable
  GitHub Action, `chatur ci install github`, and pre-commit framework hooks (ADR-0030).
- CLI helpers: `chatur check` (ADR-0020), `chatur init` and `chatur adr new|list|supersede` (ADR-0022, ADR-0024).

### Known limitations
- Local git hooks can be skipped with `--no-verify`; CI is the authoritative layer.
- Commands hidden inside scripts or repo-level git aliases can't be resolved statically. They're `ask`
  in-session, and the git/CI backstop blocks the outcome.
- `acceptEdits` and `bypassPermissions` behaviour with hook `ask` is not yet verified (ADR-0026).

[Unreleased]: https://github.com/nitsharm1910/chatur/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/nitsharm1910/chatur/releases/tag/v0.9.0
