---
id: ADR-0012
title: Python ≥3.11 (tested through latest), TOML policies, stdlib-only hook path
status: Accepted
date: 2026-10-02
deciders: Nitin
phase: design
tags: [core, performance, dependencies]
---

# ADR-0012: Python ≥3.11 (tested through latest), TOML policies, stdlib-only hook path

## Context
Hooks run on every tool call, so they must be fast, must not break when the target's environment
differs, and must not crash (Copilot `preToolUse` fails closed). Third-party imports slow startup
and can fail to resolve.

## Options considered
1. **YAML policies (PyYAML)**: familiar, but adds a dependency on the hot path.
2. **TOML policies (`tomllib`, stdlib since 3.11)**: zero dependencies, typed, and comment-friendly.
3. **JSON policies**: zero dependencies, but no comments, so they're worse for humans.

Minimum Python version:
- **3.14 floor** (maintainer's dev version): newest features, but it excludes Ubuntu 24.04 (3.12), Debian 12 (3.11), and lagging corporate/CI images, which conflicts with "deployable anywhere". Chatur needs no 3.12+ feature.
- **3.11 floor**: the first release with `tomllib`, so it gives the widest reach.

## Decision
- Minimum Python **3.11** (`requires-python = ">=3.11"`, **no upper cap**).
- Developed on the latest stable release (currently 3.14).
- CI matrix: **every supported version from 3.11 to the latest stable**, plus the **next pre-release** (`3.x-dev`) as allowed-to-fail, so new versions are tested as soon as they appear. When a new stable version ships, it's added to the matrix; when a version reaches end-of-life, raising the floor needs a new ADR.
- Policies and config in **TOML**.
- Everything reachable from `chatur hook …` and `chatur git-hook …` uses the **standard library only**, with a **500 ms** budget.
- Optional extras (`chatur[dev]`, exporters) may use dependencies outside the hook path.

## Consequences
- Positive: fast, robust hooks; `pipx install chatur` works with no compiler; forward-compatible with new Python releases.
- Negative: no Python 3.10 support; code can't use 3.12+ syntax (enforced by ruff `target-version = "py311"`).

## Guardrails / best practices this implies
- ruff `target-version = "py311"` flags newer syntax.
- Test that imports `chatur.hook` in a clean venv with no extras installed.
- Benchmark test that fails if the p95 hook latency exceeds 500 ms.
