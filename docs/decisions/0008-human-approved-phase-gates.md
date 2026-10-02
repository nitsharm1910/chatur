---
id: ADR-0008
title: Human-approved SDLC phase gates
status: Accepted
date: 2026-10-02
deciders: Nitin
phase: design
tags: [sdlc, gates]
---

# ADR-0008: Human-approved SDLC phase gates

## Context
We want a strong audit trail and human accountability across requirements → design → build → test → review → release.

## Decision
Each phase produces an exit artifact (see architecture §5). The phase advances only when a
human runs `chatur gate approve <phase>` (or the `/chatur-approve` prompt, which asks the
human to confirm). That records the approver (git identity), a timestamp, and the SHA-256 of
the artifact in `.chatur/state.json`. If the artifact changes after approval, the gate is invalid.

## Consequences
- Positive: clear accountability, so "who approved this design?" is answerable.
- Negative: slower flow. Mitigation: the `relaxed` profile treats unmet gates as warnings, and small changes can use a `fast-track` label (still logged).

## Guardrails / best practices this implies
- AI agents must never approve gates. The hook denies edits to `.chatur/state.json`, and the `gate approve` CLI refuses to run inside an assistant session (detected through hook-set env markers). CI verifies approvals were made in human-authored commits.
