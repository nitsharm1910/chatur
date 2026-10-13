# Policies and profiles

Chatur's policy is three layers, applied in order, where **each later layer can only tighten**:

```
baseline.toml  →  <profile>.toml  →  .chatur/policy.local.toml
(always on)       strict | standard | relaxed     (your project's additions)
```
Inspect the result with `chatur policy show`, and check it with `chatur policy validate`.

## Decisions
`allow < log < warn < ask < deny`. When several rules match, the **strictest wins**. When nobody can
answer a prompt (`dontAsk` mode, CI), **ask becomes deny**.

## The baseline (every profile, can't be weakened)
| Rule | Verdict | What it stops |
|---|---|---|
| `git.no-commit-push`, `git.no-history-rewrite` | deny | commit, push, merge, rebase, reset --hard, tag, branch -D, clean… (including via `sh -c`, encoded PowerShell, wrappers) |
| `git.remote-tools`, `git.remote-cli` | deny | MCP tools and `gh`/`glab`/`hub` commands that write to the remote |
| `gate.state-protected`, `gate.no-agent-approval` | deny | agents touching gate state/audit, or running `chatur gate approve` |
| `harness.read-only` | deny | agents editing `.chatur/**`, `.claude/settings*.json`, `chatur-*` agents/commands/skills/rules |
| `secrets.known-token` | deny | real tokens in files, commands, tool args |
| `secrets.credential-shape` | ask | `password=…`, `--token …`, `Bearer …` values |
| `secrets.in-prompt` | warn | a secret pasted into a prompt |
| `agent.read-only` | deny | writes by the orchestrator/reviewer agents |
| `fs.change-needs-approval`, `exec.needs-approval`, `exec.no-new-executables` | ask | any file change, any command, creating executables |

## Profiles
| Rule | strict | standard | relaxed |
|---|---|---|---|
| `fs.protected-paths` (workflows, hook dirs, `apm.yml`) | deny | ask | warn |
| `gate.design-before-code` | deny | warn | — |
| `test.missing-tests` | deny | warn | — |
| `deps.needs-adr` | deny | warn | — |
| `agent.write-scope` (agent writes outside its scope) | deny | ask | ask |
| `net.web-tools` | ask | log | log |
| unknown tools | deny | ask | ask |

## Writing local rules (`.chatur/policy.local.toml`)
Only humans edit this file (agents are denied). Examples:

```toml
schema = "chatur.policy/v1"
kind = "local"

# Add a rule
[[rule]]
id = "local.no-prod-config"
applies_to = { tool_category = ["file_write", "shell"] }
match.path_globs = ["config/prod/**"]
verdict = "deny"
reason = "Production config is changed by the platform team."

# Tighten an existing rule (loosening is a load error)
[tighten."net.web-tools"]
verdict = "ask"

# Mask project-specific identifiers in the audit log
[redact]
extra_patterns = ['\bACME-[0-9]{8}\b']

# Give your own agent a write scope
[agents.data-engineer]
write = ["pipelines/**"]
```

Match keys: `path_globs`, `shell_patterns`, `argv_patterns`, `git_subcommands`, `git_patterns`,
`tool_name_patterns`, `any`, `file_write`, `shebang`, `contains_secret`, and conditions `requires_gate`,
`requires_adr`, `missing_tests`. Selectors are OR-ed; conditions are AND-ed. Unknown keys are errors, so a
typo can't silently weaken a rule. Paths are case-insensitive; patterns without `/` match the file name at
any depth. Full semantics: ADR-0016, ADR-0017.

## Where each rule is enforced
In-session by the assistant hook, at commit/push by `chatur git-hook`, and in CI by `chatur ci-check`.
Rules marked *critical* always have a git or CI layer (ADR-0005, ADR-0030).
