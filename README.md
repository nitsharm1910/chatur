# Chatur

**A governed, auditable AI harness for the whole software lifecycle.**

Chatur turns an AI coding assistant into a disciplined team member. It gives your project
SDLC agents, slash commands, and skills, and it **enforces** the rules around them:

- **Human in the loop:** agents can't commit, push, rewrite history, merge PRs, or approve phase
  gates. Every command and file change asks you first.
- **Guardrails that can't be talked around:** a policy engine checks every tool call. Shell tricks
  (`sh -c`, encoded PowerShell, `$(…)`, quoting games) are analysed, and anything unclear goes to a human.
- **No secrets:** real tokens are blocked in files, commands, tool calls, and commits; the audit log masks them.
- **Phase gates:** requirements → design → build → test → review → release, each approved by a human and
  bound to the exact documents approved.
- **A tamper-evident record:** every action is logged to a hash-chained audit log, and every decision is an ADR.
- **Defense in depth:** the same rules hold at commit time (git hooks) and in CI, for any committer and any assistant.

> **Status: 0.9.0 (beta).** Full support for **Claude Code**. GitHub Copilot support arrives in 1.0;
> Codex, Gemini CLI, and Cursor get the instructions, agents, and skills, with the git/CI backstop
> enforcing the rules. See the [roadmap](https://github.com/nitsharm1910/chatur/blob/main/docs/roadmap.md).

## Quickstart (5 minutes)

Requires Python ≥ 3.11 and git.

```bash
pipx install chatur                 # or: pip install chatur
cd your-project

chatur init --profile standard      # .chatur/ config, docs/ phase folders, templates, .gitignore
chatur hooks install claude         # Claude Code hooks + native deny rules (.claude/settings.json)
chatur primitives install claude    # 9 agents, /chatur-* commands, skills, rules (.claude/)
chatur git-hooks install            # pre-commit / pre-push backstop
chatur ci install github            # .github/workflows/chatur.yml (CI backstop)
```

Open the project in Claude Code and run:

```text
/chatur-status
/chatur-requirements <your feature>
```

When the PRD is ready, approve the gate **in your own terminal** (agents can't):

```bash
chatur gate approve requirements
```

Then continue with `/chatur-design`, `/chatur-build`, `/chatur-test`, `/chatur-review`, `/chatur-release`.

Already use [APM](https://github.com/microsoft/apm)? `apm install nitsharm1910/chatur#v0.9.0` installs the
agents, commands, skills, and hooks instead of `hooks install` + `primitives install`.

## What you get

| | |
|---|---|
| **Agents** | `chatur-orchestrator`, `-product-analyst`, `-architect`, `-security`, `-developer`, `-qa`, `-reviewer`, `-devops`, `-docs`, each limited to its own write scope |
| **Commands** | `/chatur-status`, `-requirements`, `-design`, `-build`, `-test`, `-review`, `-release`, `-adr`, `-check` |
| **Profiles** | `strict` (regulated), `standard` (default), `relaxed` (prototyping); the baseline protections apply in all three and can't be weakened |
| **CLI** | `check` (dry-run any action) · `gate` · `adr` · `audit` · `policy` · `init` · `hooks` · `primitives` · `git-hooks` · `ci-check` |

Ask Chatur before acting: `chatur check "git push --force"` exits 0 (allow), 2 (ask), or 3 (deny) and
explains which rule decided.

## Documentation

- [Getting started](https://github.com/nitsharm1910/chatur/blob/main/docs/guide/getting-started.md): install, set up, first feature
- [Command reference](https://github.com/nitsharm1910/chatur/blob/main/docs/guide/commands.md)
- [Policies and profiles](https://github.com/nitsharm1910/chatur/blob/main/docs/guide/policies.md): what's enforced, and writing local rules
- [Troubleshooting](https://github.com/nitsharm1910/chatur/blob/main/docs/guide/troubleshooting.md)
- [Architecture](https://github.com/nitsharm1910/chatur/blob/main/docs/architecture.md) · [Decisions (ADRs)](https://github.com/nitsharm1910/chatur/tree/main/docs/decisions) · [Changelog](https://github.com/nitsharm1910/chatur/blob/main/CHANGELOG.md)
- [Security policy](https://github.com/nitsharm1910/chatur/blob/main/SECURITY.md) · [Contributing](https://github.com/nitsharm1910/chatur/blob/main/CONTRIBUTING.md)

## License

[Apache-2.0](https://github.com/nitsharm1910/chatur/blob/main/LICENSE)
