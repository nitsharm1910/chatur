---
id: ADR-0011
title: Distribute as one GitHub repo = APM package + pip-installable core
status: Accepted
date: 2026-10-02
deciders: Nitin
phase: design
tags: [distribution, release]
---

# ADR-0011: Distribution

## Decision
A single GitHub repository is both:
- the **APM package** (`apm.yml` + `.apm/`), installed with `apm install <owner>/chatur#vX.Y.Z`, and
- the **Python core** (`pyproject.toml`, `src/chatur`), installed with `pipx install chatur` (or from git).

Both share one semver version and git tag. `chatur init` in a target writes `.chatur/config.toml`,
installs git hooks, and adds the CI workflow.

## Guardrails / best practices this implies
- CI fails if `apm.yml` and `pyproject.toml` versions differ.
- Releases are tagged from `main` only, and each has a CHANGELOG entry.
