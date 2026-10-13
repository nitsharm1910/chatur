# Getting started

This guide takes a project from zero to a governed AI workflow, then walks one feature through the
first two phases. Commands work the same in bash and PowerShell.

## 1. Install
Requires **Python ≥ 3.11** and **git**.

```bash
pipx install chatur        # recommended: puts `chatur` on PATH in its own environment
chatur --version
```

## 2. Set up a project
Run these from the project root:

```bash
chatur init --profile standard
```
This creates:
- `.chatur/config.toml`: your profile (`strict`, `standard`, `relaxed`) and audit setting. **Commit it.**
- `.chatur/policy.local.toml`: project rules that can only *tighten* the profile. **Commit it.**
- `.chatur/templates/`: PRD, design, threat model, test, review, release templates (gitignored; regenerated).
- `docs/{requirements,design,decisions,security,test,review,releases}/`: where phase artifacts go.
- A managed block in `.gitignore`.

Then connect your assistant and the backstop:

```bash
chatur hooks install claude         # .claude/settings.json: hooks + native deny rules (commit it)
chatur primitives install claude    # .claude/agents|commands|skills|rules/chatur-* (gitignored)
chatur git-hooks install            # .git/hooks/pre-commit and pre-push
chatur ci install github            # .github/workflows/chatur.yml (commit it)
```

Teammates cloning the repo run `chatur primitives install claude` and `chatur git-hooks install` once.

> Prefer APM? `apm install nitsharm1910/chatur#v0.9.0` installs agents, commands, skills, and hooks.
> Still run `chatur hooks install claude` for the native deny rules.

## 3. Check it works
```bash
chatur policy validate                 # policy OK: profile=standard ...
chatur check "git push"                # deny: [git.no-commit-push] ...   (exit 3)
chatur check --write src/app.py        # ask: [fs.change-needs-approval] ... (exit 2)
chatur gate status                     # current phase: requirements
```
Open the project in Claude Code. The session starts with a Chatur context message, and from now on
every command and edit asks you first.

## 4. First feature: requirements
In Claude Code:
```text
/chatur-requirements tasks CLI
```
The `chatur-product-analyst` agent asks clarifying questions, then writes
`docs/requirements/PRD-<name>.md` from the template. Review it, then approve **in your own terminal**:

```bash
chatur gate approve requirements
```
You'll see the files being approved and your identity, then type the phase name (`requirements`) to
confirm. The approval records your git identity, a digest of the PRD, and an anchor in the audit log.
If the PRD changes later, the gate becomes **stale** and has to be approved again.

## 5. Design
```text
/chatur-design tasks CLI
```
`chatur-architect` writes `docs/design/<name>.md` and Proposed ADRs; `chatur-security` writes the threat
model. Accept the ADRs you agree with (edit `status: Accepted`), then `chatur gate approve design`.

## 6. Keep going
`/chatur-build` → `chatur gate approve build` → `/chatur-test` → `/chatur-review` → `/chatur-release`.
Agents never commit: each step ends with a suggested commit message for **you** to commit.

## What happens when Chatur says no
- **deny:** the action is blocked. The reason names the rule and its ADR; ask the agent for the legitimate
  route (usually a human does it).
- **ask:** Claude shows you an approval prompt. Read the reason before approving.
- Unsure? `chatur check "<command>"` is a dry run, and `chatur audit tail` shows what happened.

Next: [command reference](commands.md) · [policies](policies.md) · [troubleshooting](troubleshooting.md).
