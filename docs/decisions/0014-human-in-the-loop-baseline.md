---
id: ADR-0014
title: Human-in-the-loop baseline for git, file changes, and execution
status: Accepted
date: 2026-10-02
deciders: Nitin
phase: design
tags: [guardrails, git, security, baseline]
amends: ADR-0007
---

# ADR-0014: Human-in-the-loop baseline for git, file changes, and execution

## Context
The maintainer requires git to be very protective: AI must not commit or push on any branch,
and must not change or delete files or run executables without human approval. These apply in
**every profile** and become part of the non-weakenable baseline in ADR-0007.

## Decision
We will add these baseline rules (`policies/baseline.toml`):

| Rule id | Matches | Verdict (human present) | Verdict (unattended) |
|---|---|---|---|
| `git.no-commit-push` | `git commit`, `git push`, `git commit-tree`, `git update-ref`, `git merge` (creates commits), `git cherry-pick`, `git revert`, `git am` | **deny** | deny |
| `git.no-history-rewrite` | `git reset --hard`, `git rebase`, `git filter-branch`, `git filter-repo`, `git tag`, `git branch -d/-D/-m`, `git push --force*`, `git stash drop/clear`, `git clean`, `git checkout -- <path>`, `git restore`, `git gc --prune`, `git reflog expire` | **deny** | deny |
| `git.remote-tools` | MCP/integration tools that create commits, push files, merge PRs, or create/delete branches/tags (e.g. GitHub MCP `push_files`, `create_or_update_file`, `merge_pull_request`) | **deny** | deny |
| `fs.change-needs-approval` | Any file create, edit, rename, or delete via file tools **or** shell (`rm`, `del`, `Remove-Item`, `rmdir`, `mv`, `move`, `git rm`, `git mv`, redirects `>`/`>>`, `sed -i`, `Set-Content`, `Out-File`, `tee`) | **ask** | deny |
| `exec.needs-approval` | Any shell/terminal command, script, or binary execution, including interpreters (`python x.py`, `node`, `bash x.sh`, `pwsh -File`) and package managers (`pip`, `npm`, `apt`) | **ask** | deny |
| `exec.no-new-executables` | Creating or modifying executable artifacts: `*.sh *.ps1 *.bat *.cmd *.exe *.dll *.so *.py` with a shebang, `chmod +x`, `.git/hooks/*` | **ask** (reason labels it as executable) | deny |

"Unattended" means the adapter knows no human can answer a prompt: Copilot cloud agent, CI, or the SDK runner without a TTY.

Read-only file tools (view/read/grep/glob) are **allowed + logged**. Read-only shell commands are still **ask** by default.
An opt-in allowlist (`exec.readonly_allowlist`, e.g. `git status|log|diff|show`, `ls`, `dir`) may be enabled only by a superseding ADR.

## Detection rules (anti-bypass)
- Shell commands are matched **conservatively** across the whole command string. A `git` token anywhere followed by a denied subcommand denies, including `git -C path commit`, `sh -c "…git push…"`, `cmd /c`, `&&`/`;`/`|` chains, and `$(…)`.
- Unknown or unparseable commands → **ask**, never allow.
- Running any script (`bash x.sh`, `./x`, `python x.py`) → ask, because a script can hide a commit. The git backstop below catches it if the human approves blindly.
- The adapter crashing → deny (fail closed).

## Backstop (ADR-0005)
- **git `pre-commit` / `pre-push` hooks** (`chatur git-hook`) reject commits and pushes when they detect an AI session environment: `CLAUDECODE`, Copilot agent markers, or `CHATUR_AGENT_SESSION` exported by Chatur's session-start hook into tool shells where supported.
- **CI** flags commits whose trailers or authors indicate AI authorship without a human `Approved-by:` trailer.
- Humans commit and push themselves. `chatur` never runs `git commit` or `git push`.

## Consequences
- Positive: an AI can never change history or the remote, and every change and command passes in front of a human.
- Negative: a prompt for every edit and command (high friction), and unattended agents become read-only proposers (they output patches or diffs for a human to apply).
- Follow-up: measure prompt volume in dogfooding (Phase 6). If friction is too high, consider the read-only allowlist via a new ADR.

## Guardrails / best practices this implies
- These rules are `baseline = true`. Policy validation fails if any profile or `policy.local.toml` sets them weaker.
- Tests: for each rule, at least one deny/ask case and one bypass-attempt case (chained, nested shell, `-C`), per adapter.
