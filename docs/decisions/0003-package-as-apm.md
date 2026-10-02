---
id: ADR-0003
title: Package distributable primitives as an APM package
status: Accepted
date: 2026-10-02
deciders: Nitin
phase: design
tags: [packaging, distribution]
---

# ADR-0003: Package distributable primitives as an APM package

## Context
Chatur has to be deployable into other projects. Microsoft's Agent Package Manager (APM)
packages instructions, prompts, agents, skills, hooks, and MCP servers from a `.apm/` source
tree and deploys them per target: Claude → `.claude/…`, Copilot → `.github/…`, Codex →
`.codex/…`, Gemini → `.gemini/…`, Cursor → `.cursor/…`. It has a lockfile (`apm.lock.yaml`),
policy (`apm-policy.yml`), and `apm audit`.

## Options considered
1. **Custom installer script**: full control, but we'd rebuild per-target layout logic ourselves.
2. **Claude Code plugin only**: locks us into one vendor.
3. **APM package**: one manifest with multi-target compilation and governance built in.

## Decision
We will author distributable primitives under `.apm/` (instructions, agents, prompts, skills,
hooks) with an `apm.yml` manifest, so `apm install <owner>/chatur` deploys Chatur into a target.

## Consequences
- Positive: we get multi-target deployment, version pinning, and integrity hashes for free.
- Negative: we depend on APM's release cadence. APM's hook JSON is translated per target, and
  we must verify its output against each assistant's native schema (adapter tests).
- Follow-up: pin a minimum APM version once we validate compile output (Phase 2).

## Guardrails / best practices this implies
- CI runs `apm compile` for every v1 target and diffs the output against golden fixtures.
- `apm audit` runs in CI.
