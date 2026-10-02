---
id: ADR-0002
title: Multi-assistant support with AGENTS.md as canonical instructions
status: Accepted
date: 2026-10-02
deciders: Nitin
phase: design
tags: [portability, assistants]
---

# ADR-0002: Multi-assistant support with AGENTS.md as canonical instructions

## Context
Chatur must work with Claude Code, GitHub Copilot, OpenAI Codex, Gemini CLI, and others, not
just one vendor. Each reads its own instruction file (CLAUDE.md, copilot-instructions.md,
GEMINI.md), but AGENTS.md is now an open standard (Agentic AI Foundation / Linux Foundation)
that Codex, Copilot, Cursor, and Gemini (via `context.fileName`) read.

## Options considered
1. **Per-assistant hand-written files**: drift and duplication.
2. **AGENTS.md as the single source, with thin per-assistant shims**: one truth, broad support.

## Decision
We will keep all assistant-agnostic instructions in AGENTS.md (and in `.apm/instructions/`
for distributable content). Assistant files only import or point to it: CLAUDE.md uses
`@AGENTS.md`, and Gemini is configured with `context.fileName: ["AGENTS.md"]`. Only genuinely
assistant-specific notes go in a shim.

## Consequences
- Positive: a rule is written once and applies everywhere.
- Negative: we're limited to features every assistant understands; richer features go in adapters.

## Guardrails / best practices this implies
- Lint (CI): shim files must not restate rules that AGENTS.md already contains (duplicate-heading check).
