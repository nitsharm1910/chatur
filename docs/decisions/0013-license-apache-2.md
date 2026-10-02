---
id: ADR-0013
title: License under Apache-2.0
status: Accepted
date: 2026-10-02
deciders: Nitin
phase: meta
tags: [legal, distribution]
---

# ADR-0013: License under Apache-2.0

## Context
Chatur is distributed into other projects (ADR-0011) and may receive contributions.

## Options considered
1. **MIT**: the simplest permissive license, with no patent grant.
2. **Apache-2.0**: permissive, with an explicit patent grant and a contribution clause.
3. **Proprietary**: limits adoption.

## Decision
We will license Chatur under Apache-2.0 (`LICENSE` at the repo root).

## Guardrails / best practices this implies
- New dependencies must have a license compatible with Apache-2.0 (checked in CI via a license scan in Phase 5).
