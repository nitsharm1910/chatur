---
id: ADR-0023
title: Secret-detection baseline rules (tiered)
status: Accepted
date: 2026-10-04
deciders: Nitin
phase: design
tags: [guardrails, baseline, secrets, security]
implements: ADR-0007
amends: ADR-0016
---

# ADR-0023: Secret-detection baseline rules (tiered)

## Context
ADR-0007 made "secrets in files/commands → deny" a baseline rule for every profile, but it was never
implemented. `chatur.redact` only masked secrets when writing the audit log (ADR-0015), so an agent
could still write a token into a file or use one in a command. The gap was found during step 1.8.

## Decision (maintainer: scan everywhere, tiered strictness)
1. **New selector `contains_secret = "token" | "credential" | "any"`** (amends ADR-0016). It reuses the
   `chatur.redact` patterns:
   - `token`: known formats (GitHub, AWS, Anthropic, OpenAI, Slack, Google, Stripe, JWT, PEM private key);
   - `credential`: generic shapes (`password=…`, `--token …`, `Bearer …`, `https://user:pass@`).
2. **What is scanned**
   - file writes: every string argument **except** keys starting with `old` (`old_string`, `oldText`), so removing a secret from a file is never blocked;
   - shell: the command and every nested or decoded command text (ADR-0017);
   - MCP / web / agent / other tools: every string argument, recursively;
   - prompts: the prompt text.
3. **Placeholders are ignored**: values containing `${`, `$(`, `{{`, `<…>`, `changeme`, `example`,
   `dummy`, `placeholder`, `redacted`, `your_…`, or with ≤ 3 distinct characters in the secret part
   (`ghp_xxxx…`, `AKIA0000…`).
4. **Baseline rules**

| Rule | Applies to | Selector | Verdict |
|---|---|---|---|
| `secrets.known-token` | file_write, shell, mcp, web, agent, other (pre_tool) | `token` | **deny** |
| `secrets.credential-shape` | same | `credential` | **ask** |
| `secrets.in-prompt` | prompt events | `any` | **warn** |

`secrets.known-token` is `critical` with layers `hook, git, ci`. The git/CI backstop (Phase 5) runs
the same scan over staged changes.

## Consequences
- Positive: an agent can't write a real token into the repo or use one in a command. Humans are warned when they paste one.
- Negative: real-looking fake tokens in test fixtures are denied; use placeholders or low-variety values.
  Unknown token formats are missed (projects can add patterns via `[redact] extra_patterns`; scanning them is a follow-up).

## Guardrails / best practices this implies
- Tests for each scan location, each tier, placeholder exclusions, `old_*` exclusion, nested/encoded shell, and prompt warnings.
