# Contributing to Chatur

Thanks for helping! Chatur is developed the way it asks other projects to work: decisions are recorded,
changes are tested, and AI assistants work under Chatur's own guardrails.

## Ground rules
The canonical rules live in [AGENTS.md](AGENTS.md) (for humans and AI alike). The essentials:
1. **Decisions are ADRs.** Changes to architecture, public interfaces, policy semantics, supported
   assistants, or dependencies need a new or superseding ADR in `docs/decisions/`
   (`chatur adr new "<title>"`, status `Proposed`). The maintainer accepts.
2. **Tests with every change.** Every guard rule has allow and deny cases; every bypass fix comes with a
   failing test first (`tests/test_guard_bypass.py`).
3. **Stdlib-only runtime** and the < 500 ms hook budget (ADR-0012); enforced by `tests/test_hook_budget.py`.
4. **Assistant-specific code only in `src/chatur/adapters/`** (and `.apm/hooks/`).
5. **Cross-platform:** Windows (PowerShell) and Linux/macOS must both work.
6. **Journal:** append to `docs/journal/YYYY-MM-DD.md` for each working session.

## Development setup
```bash
git clone https://github.com/nitsharm1910/chatur && cd chatur
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest                                      # ~1000 tests
ruff check . && ruff format --check .
```

Dogfooding (recommended): `chatur hooks install claude --local` guards your AI assistant while you work
on Chatur, and `chatur git-hooks install` guards your commits.

## Changing primitives
Agents, commands, skills, and instructions live in `.apm/`. Templates live in `src/chatur/templates/`;
after editing a template run `python scripts/sync_primitives.py` (tests fail on drift). After changing a
hook definition, regenerate `.apm/hooks/chatur-claude.json` from the adapter (tests compare them).

## Pull requests
- Conventional-commit titles that reference ADRs, e.g. `feat(guard): block X (ADR-00NN)`.
- CI must be green: tests on Linux/Windows/macOS × Python 3.11–3.14, lint, and the `backstop` job.
- Update docs touched by the change (architecture, guide, README, CHANGELOG under `[Unreleased]`).

## Security issues
Please report vulnerabilities and guardrail bypasses privately; see [SECURITY.md](SECURITY.md).
