# Chatur

**A portable, multi-assistant AI harness for the full software development lifecycle.**

Chatur gives any project a governed, auditable AI workflow: SDLC agents, prompts, skills,
guardrail hooks, human-approved phase gates, and an append-only record of every action and
decision. It works with Claude Code and GitHub Copilot (v1), and supports Codex, Gemini CLI, and
Cursor at the instruction level.

> Status: **Phase 0 — Foundation.** Not yet usable. See [docs/roadmap.md](docs/roadmap.md).

## How it works
1. **Primitives** (`.apm/`): agents, prompts, skills, and instructions, authored once and deployed to each assistant via [APM](https://github.com/microsoft/apm).
2. **Core** (`chatur` CLI, Python): a guard engine, audit log, phase gates, and ADR tooling.
3. **Adapters**: translate each assistant's hook events into one normalized event.
4. **Backstop**: git hooks and CI enforce the same policies regardless of assistant.

Details: [docs/architecture.md](docs/architecture.md) · Decisions: [docs/decisions/](docs/decisions/)

## Planned usage (target project)
```bash
pipx install chatur
apm install <owner>/chatur
chatur init --profile standard --assistants claude,copilot
```
