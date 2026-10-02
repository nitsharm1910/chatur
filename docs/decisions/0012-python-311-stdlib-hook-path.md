---
id: ADR-0012
title: Python ≥3.11, TOML policies, stdlib-only hook path
status: Proposed
date: 2026-10-02
deciders: Nitin (pending)
phase: design
tags: [core, performance, dependencies]
---

# ADR-0012: Python ≥3.11, TOML policies, stdlib-only hook path

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
- **3.11 floor**: the first release with `tomllib`, so it gives the widest reach. Develop on 3.14, and CI tests 3.11, 3.12, 3.13, and 3.14.

## Decision
- Minimum Python **3.11**; develop on 3.14; CI matrix 3.11–3.14.
- Policies and config in **TOML**.
- Everything reachable from `chatur hook …` and `chatur git-hook …` uses the **standard library only**, with a **500 ms** budget.
- Optional extras (`chatur[dev]`, exporters) may use dependencies outside the hook path.

## Consequences
- Positive: fast, robust hooks; `pipx install chatur` works with no compiler.
- Negative: no Python 3.10 support.

## Guardrails / best practices this implies
- Test that imports `chatur.hook` in a clean venv with no extras installed.
- Benchmark test that fails if the p95 hook latency exceeds 500 ms.
