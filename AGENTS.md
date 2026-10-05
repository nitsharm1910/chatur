# Chatur — Agent Instructions (for working ON this repo)

> This file is the canonical, assistant-agnostic instruction set for anyone (human or AI)
> developing **Chatur itself**. Claude Code reads it via `CLAUDE.md`; Copilot, Codex,
> Gemini, and Cursor read `AGENTS.md` natively. Do not duplicate rules elsewhere — link here.

## What Chatur is
A portable, multi-assistant **AI harness for the full SDLC**. It ships agents, prompts,
skills, hooks, guardrail policies, and tracking (audit log, ADRs, phase gates) as an
**APM package** plus a **Python core** (`chatur` CLI). It installs into *other* projects.

Read before changing anything:
- [docs/architecture.md](docs/architecture.md) — layers, components, data flow
- [docs/decisions/](docs/decisions/) — every accepted decision (ADRs)
- [docs/roadmap.md](docs/roadmap.md) — phases and current status

## Repository map
| Path | Purpose |
|------|---------|
| `.apm/` | **Distributable primitives** — what target projects receive: `agents/` (9 `chatur-*`), `prompts/` (`/chatur-*` commands), `skills/` (with `assets/` templates), `instructions/`, `hooks/` (ADR-0027) |
| `scripts/` | Dev tools (`sync_primitives.py` copies templates into skill assets; tests enforce sync) |
| `src/chatur/` | Python core: event normalization, guard engine, audit log, gates, ADR tooling, CLI |
| `src/chatur/adapters/` | One module per assistant; translates native hook payloads ⇄ `ChaturEvent` |
| `src/chatur/policies/` | Guardrail policy: `baseline` + profiles `strict`, `standard`, `relaxed` (shipped in the wheel; ADR-0016) |
| `src/chatur/templates/` | Artifact templates shipped in the wheel and installed by `chatur init` (ADR now; PRD, test plan, threat model, release notes in Phase 3) |
| `docs/decisions/` | ADRs for Chatur's own design |
| `docs/journal/` | Dated work journal — what was done, why, what's next |
| `tests/` | pytest suite; adapter tests use recorded real payload fixtures |

## Non-negotiable rules (guardrails for this repo)
1. **Decisions are recorded.** Any change to architecture, public interfaces, policy semantics,
   supported assistants, or dependencies requires a new or superseding ADR in `docs/decisions/`
   (copy `0000-template.md`). Status starts `Proposed`; only the maintainer flips it to `Accepted`.
2. **Journal every working session.** Append to `docs/journal/YYYY-MM-DD.md`: actions taken,
   decisions referenced (ADR ids), open questions, next steps.
3. **Hook path is stdlib-only.** Code reachable from a hook entrypoint must not import
   third-party packages and must finish in < 500 ms. Hooks fail **closed** for `preToolUse`-type
   events and **open** (log + warn) for everything else. See ADR-0012.
4. **Assistant-specific code lives only in `src/chatur/adapters/` and `.apm/hooks/`.**
   The guard engine, audit, and gates only ever see `ChaturEvent`.
5. **Every guard rule has a test** with at least one allow and one deny case, per adapter.
6. **Cross-platform.** Windows (PowerShell) and Linux/macOS (bash) must both work. Use
   `pathlib`, never hardcoded separators; hook configs provide both `bash` and `powershell`.
7. **No secrets, no network in core.** The core never makes network calls; external
   integrations are optional plugins behind explicit config.
8. **Semver.** `apm.yml` and `pyproject.toml` versions move together. Breaking changes to
   `ChaturEvent`, policy schema, or `.chatur/` layout are major bumps.

## Workflow for a change
1. Check [docs/roadmap.md](docs/roadmap.md) for the phase; check existing ADRs.
2. If a decision is needed → write a `Proposed` ADR and ask the maintainer.
3. Implement with tests (`python -m pytest`).
4. Update docs touched by the change (architecture, README, roadmap status).
5. Write the journal entry.
6. Commit with a conventional-commit message referencing ADRs (e.g. `feat(guard): block force-push (ADR-0007)`).

## Conventions
- Python ≥ 3.11, type hints everywhere, `ruff` for lint/format, `pytest` for tests.
- Markdown primitives in `.apm/` use YAML frontmatter with at least `description`.
- File names: kebab-case for docs/primitives, snake_case for Python modules.
