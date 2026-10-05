---
id: ADR-0024
title: ADR supersede workflow
status: Accepted
date: 2026-10-04
deciders: Nitin
phase: meta
tags: [adr, cli, process]
refines: [ADR-0001, ADR-0022]
---

# ADR-0024: ADR supersede workflow

## Context
ADR-0001 says Accepted ADRs are immutable and change only by being superseded. ADR-0022 added
`chatur adr new|list`; the original Phase 1 plan also included `supersede`. A decision must not be
marked superseded by a replacement that hasn't itself been accepted.

## Decision
Two steps, mirroring the human-acceptance rule:

1. **Draft the replacement:** `chatur adr new "<title>" --supersedes 7[,9]` creates a `Proposed` ADR
   with front matter `supersedes: [ADR-0007]` and a line under the heading:
   `> Supersedes [ADR-0007](0007-….md).` Referenced ADRs must exist.
2. **Finalise after a human accepts it:** `chatur adr supersede 7 --by 25`
   - refuses unless ADR-0025 is `Accepted` (ADR-0001);
   - refuses if ADR-0007 is already superseded, or if old == new;
   - sets ADR-0007 `status: Superseded by ADR-0025`, adds `superseded_by: ADR-0025`, and inserts
     `> **Superseded by [ADR-0025](0025-….md).**` under its heading (the body is otherwise untouched);
   - makes sure ADR-0025's `supersedes` lists ADR-0007.

References accept `7`, `0007`, `ADR-0007`, or `adr-7`.

## Consequences
- Positive: the decision history stays linked in both directions, and nothing is superseded by an unaccepted draft.
- Negative: two commands instead of one (deliberate; the human acceptance happens in between).

## Guardrails / best practices this implies
- Tests: reference parsing, missing ADRs, the Proposed-replacement refusal, double supersede, self-supersede, and front-matter/body updates on both files.
