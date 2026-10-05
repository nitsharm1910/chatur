---
id: ADR-0019
title: Audit log format, hash chain, and concurrency
status: Accepted
date: 2026-10-04
deciders: Nitin
phase: design
tags: [audit, integrity]
refines: [ADR-0006, ADR-0015]
---

# ADR-0019: Audit log format, hash chain, and concurrency

## Context
ADR-0006 requires an append-only JSONL audit log with a hash chain; ADR-0015 says what gets masked.
Several hook processes can fire at the same moment (parallel tool calls), and the log has to work
the same way on Windows and POSIX with the standard library only (ADR-0012).

## Decision

### Files
`.chatur/audit/YYYY-MM-DD.jsonl`, one file per **UTC** day. Lines are UTF-8 canonical JSON
(`sort_keys`, compact separators) terminated by `\n`. Other files in the directory are ignored.

### Record (`chatur.audit/v1`)
| Field | Meaning |
|---|---|
| `schema` | `chatur.audit/v1` |
| `seq` | global sequence number, +1 per record, continuous across days |
| `ts` | write time (UTC); the event keeps its own `ts` |
| `chatur_version` | writer version |
| `event` | `ChaturEvent.to_dict()` |
| `verdict` | `Verdict.to_dict()` or `null` (post-tool, session events) |
| `prev` | `hash` of the previous record; 64 zeros for the very first record |
| `hash` | SHA-256 of the canonical JSON of the record **without** `hash` |

The **whole record** is passed through `redact` (built-in patterns plus the project's `extra_patterns`)
before hashing, because verdict reasons can quote commands.

### Chain
One chain across all daily files: a day's first record has `prev` = the last record of the most
recent earlier file. `chatur audit verify` detects edited, deleted, inserted, reordered, and
corrupt lines, and a missing earlier file (the next file's first `prev` doesn't link).

### Concurrency
Appends are serialised with an exclusive OS lock on `.chatur/audit/.lock` (`fcntl.flock` on POSIX,
`msvcrt.locking` on Windows), held for read-last-record → compute → append → fsync. Lock wait
times out after 2 s with `AuditError`.

### Failure behaviour
If the last record is corrupt or the lock times out, `append` raises `AuditError` and writes nothing.
It never chains from a record it can't verify. The hook layer (Phase 2) decides what to do with that
(fail closed on pre-tool events, per ADR-0012).

## Known limitation
A hash chain alone can't detect **removal of the newest records** (truncating the tail, or deleting
the latest file). Mitigations: committing the audit log (default under `strict`, ADR-0006) makes
truncation visible in git history, and a future anchor (the last hash recorded in `.chatur/state.json`
at each gate approval) is noted for Phase 1.6.

## Guardrails / best practices this implies
- Tests for each tamper type, cross-day chaining, the missing-file case, and concurrent writers from separate processes.
- Agents can't write `.chatur/audit/**` (baseline `gate.state-protected`); only the `chatur` process does.
