# Security policy

Chatur is a security control: it limits what AI agents can do in your repository. Bypasses of its
guardrails are treated as security vulnerabilities.

## Supported versions
| Version | Supported |
|---|---|
| 0.9.x | ✅ |
| < 0.9 | ❌ |

## Reporting a vulnerability
**Please don't open a public issue for a vulnerability or bypass.** Report it privately through GitHub's
[private vulnerability reporting](https://github.com/nitsharm1910/chatur/security/advisories/new).

Include: the Chatur version, assistant and permission mode, profile, the exact command or tool call (redact
real secrets), and what happened versus what you expected. A minimal reproduction, ideally a failing
`chatur check "<command>"`, helps a lot. You should get an acknowledgement within 7 days. Fixes for
confirmed bypasses ship with a regression test in `tests/test_guard_bypass.py` (ADR-0017).

## What Chatur protects against
- An AI agent committing, pushing, rewriting history, merging PRs, or approving gates.
- Agents writing secrets into files, commands, tool calls, or prompts.
- Agents editing the harness itself (policy, hooks, gate state, audit log, agent definitions).
- Tampering with gate approvals or the audit log going unnoticed (hash chain, approval↔audit cross-check).

## Known limitations (by design; covered by other layers)
- **Local git hooks can be skipped** (`git commit --no-verify`). CI (`chatur ci-check`) is the authoritative layer.
- **Hooks fail open if Chatur isn't installed** or can't start. That's why `chatur hooks install` also writes
  Claude's native `permissions.deny` rules, which work without Chatur.
- **Static analysis limits:** commands hidden inside scripts, Makefiles, repo-level git aliases, or values
  computed at runtime can't be resolved. They still require human approval in-session, and the backstop
  blocks the outcome (e.g. the commit).
- **Secret detection is pattern-based:** unknown token formats can be missed (add project patterns with
  `[redact] extra_patterns`).
- **Agent identity comes from the assistant** (e.g. Claude's `agent_type`); write scopes only apply when the
  assistant reports it.
- **Removing the newest audit records** is detectable only through gate anchors and git history, which is why
  the audit log is committed by default (ADR-0019, ADR-0022).
