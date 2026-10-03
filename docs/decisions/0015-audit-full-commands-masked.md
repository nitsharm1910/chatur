---
id: ADR-0015
title: Audit log stores full commands with known secret patterns masked
status: Accepted
date: 2026-10-03
deciders: Nitin
phase: design
tags: [audit, privacy, security]
refines: ADR-0006
---

# ADR-0015: Audit log stores full commands with known secret patterns masked

## Context
ADR-0006 requires every action to be logged with secrets redacted, but it didn't say how much
of a command to keep. A full command is the most useful thing to review; a truncated command
plus a hash is safer but often useless in an investigation.

## Options considered
1. **Full command, secrets masked**: reviewable. The risk is a secret format we don't recognise.
2. **Truncated command + SHA-256**: safe, but hard to review.
3. **Hash only**: proves integrity, but tells a reviewer nothing.

## Decision
We will log full shell commands and tool arguments, after passing them through
`chatur.redact`, which masks:
- **Known token formats** (AWS, GitHub, Anthropic, OpenAI, Slack, Google, Stripe, JWT, PEM private keys).
- **Credential-shaped values** (`password=…`, `--token …`, `Authorization: Bearer …`, `https://user:pass@host`).
- **Values under sensitive keys** in structured args (`password`, `secret`, `token`, `api_key`, …).

Masked values become `[REDACTED:<kind>]`. File *contents* are never logged (ADR-0006), only paths.

Redaction happens **only when an event is serialised** for the audit log. The guard engine sees
unmasked values so it can detect secrets in the first place.

## Consequences
- Positive: full, readable audit trail.
- Negative: an unknown secret format can leak into the log. Mitigations: patterns are
  extendable via `.chatur/policy.local.toml` (Phase 1.3), and the `strict` profile can opt out of
  committing the audit log.

## Guardrails / best practices this implies
- Every redaction pattern has a positive test and a false-positive test (e.g. `git status`, normal paths).
- Code outside `chatur.redact` never serialises a `ChaturEvent` for persistence without `redact=True`.
