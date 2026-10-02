---
id: ADR-0001
title: Record architecture decisions as ADRs in the repo
status: Accepted
date: 2026-10-02
deciders: Nitin
phase: meta
tags: [process, tracking]
---

# ADR-0001: Record architecture decisions as ADRs in the repo

## Context
Chatur's core promise is tracking every action, design, and decision with guardrails. Chatur
itself has to work the same way (dogfooding), and the ADR format it ships to targets has to be
proven on its own repo first.

## Options considered
1. **MADR-style markdown ADRs in `docs/decisions/`**: git-versioned, reviewable in PRs, readable by every AI assistant.
2. **Wiki or external tool**: not versioned with the code, and assistants can't read it.

## Decision
We will record each significant decision as a numbered markdown ADR with YAML frontmatter in
`docs/decisions/`, using `0000-template.md`. ADRs are immutable once Accepted; changes are made
by superseding.

## Consequences
- Positive: decisions sit beside the code, and both AI and humans can read them.
- Negative: authors have to write them.
- Follow-up: the `chatur adr new|list|supersede` CLI (Phase 1).

## Guardrails / best practices this implies
- Only humans move an ADR to `Accepted` (enforced in CI later: ADR status changes need a human-authored commit).
- Every ADR includes a "Guardrails" section, which turns each decision into enforceable rules.
