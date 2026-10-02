---
id: ADR-0010
title: SDLC agent roster
status: Accepted
date: 2026-10-02
deciders: Nitin
phase: design
tags: [agents, sdlc]
---

# ADR-0010: SDLC agent roster

## Decision
Chatur ships nine agents as `.apm/agents/*.agent.md`:

| Agent | Responsibility | Writes |
|---|---|---|
| `orchestrator` | Reads phase state, routes work to the right agent, reports status; never writes code | status only |
| `product-analyst` | Requirements, user stories, acceptance criteria | `docs/requirements/` |
| `architect` | Design docs, ADRs, interfaces | `docs/design/`, `docs/decisions/` |
| `security` | Threat model (design), security review (review), dependency/secret checks | `docs/security/` |
| `developer` | Implementation + unit tests within approved design | `src/`, `tests/` |
| `qa` | Test plan, integration/e2e tests, test report | `tests/`, `docs/test/` |
| `reviewer` | Code review against design, ADRs, and policy | review reports |
| `devops` | CI/CD, packaging, release notes, versioning | `.github/workflows/` (via ask), `docs/releases/` |
| `docs` | README, user docs, CHANGELOG upkeep | `docs/`, `README.md` |

## Guardrails / best practices this implies
- Each agent declares a **write scope**. The guard engine can enforce it when the assistant
  exposes the active agent (Claude subagents and Copilot custom agents do).
- Least privilege: read-only agents (orchestrator, reviewer) get no write or shell tools in their frontmatter.
