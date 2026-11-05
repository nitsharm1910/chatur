---
id: ADR-0033
title: Context, memory, checkpoints, and cost management
status: Proposed
date: 2026-11-04
deciders: Nitin (pending)
phase: design
tags: [context, memory, checkpoints, cost, prompt-caching, hooks]
refines: [ADR-0006, ADR-0012, ADR-0025, ADR-0027, ADR-0028, ADR-0029]
---

# ADR-0033: Context, memory, checkpoints, and cost management

## Context
The maintainer wants Chatur's agents to manage memory, context, compression, and trimming to save cost,
to checkpoint so important information isn't lost, and to use caching.

**What the assistant owns, and Chatur can't replace** (Claude Code docs, checked 2026-11-04):
- **Prompt caching is automatic and server-side.** Chatur can't "use a cache" directly; it can only avoid breaking it.
- **Compaction belongs to Claude Code.** `PreCompact` can only block it and receives `custom_instructions` read-only;
  `PostCompact` receives `compact_summary` and has no decision control. No hook can edit the summary or the conversation.
- **Token counts reach hooks only in special cases** (`context_tokens` and `estimated_cache_write_usd` on
  `SessionStart` with `source` resume/fork, and on `PreModelSwitch`). The status line and `/usage` have the full figures.

**What hooks do expose:**
- `SessionStart` with source `compact` runs after compaction and its output is added to the compacted context
  (`additionalContext` is capped at 10,000 characters; beyond that Claude gets a path and a 2,000-character preview).
- `PostToolUse` `updatedToolOutput` replaces what Claude sees. The value must match the tool's output shape
  (for `Bash`: `stdout`, `stderr`, `interrupted`, `isImage`); a mismatch is ignored and the original is used.

**A defect this review found** (fixed separately in ADR-0034): `chatur primitives install` turned our core rule's
`applyTo: "**"` into `paths: ["**"]`. Path-scoped rules enter message history and are summarised away by compaction;
unscoped rules are re-injected from disk and sit in the cached project-context layer.

## Decision

**Maintainer's answers so far:** trimming on by default; project notes committed and shared; both opt-in cost settings
offered; built after 0.9.0 is tagged, as 0.10.0. The rest of this ADR is still awaiting acceptance.

Chatur manages what it can see deterministically, and works with the assistant's caching and compaction.
**Non-goal:** Chatur doesn't build its own summariser, conversation compressor, or cache. The core makes no LLM or
network calls (AGENTS.md rule 7). A future SDK runner could own more of this.

### 1. Checkpoints (don't lose important information)
`.chatur/checkpoints/` holds deterministic snapshots, gitignored (working state; durable decisions belong in ADRs
and phase docs). Last 20 are kept.
- **Contents:** current phase and gate states, active change (ADR-0032, when built), Proposed ADRs, changed files
  (`git status`), recent denied actions from the audit log, project notes, and any `--note` text.
- **Written on:** `PreCompact` (manual and auto), `SessionEnd`, `chatur gate approve`, and on demand with
  `chatur checkpoint save --note "<what's in flight>"` (also the `/chatur-checkpoint` command, where the agent
  writes the note: goal, next step, open questions).
- **`PostCompact`:** stores the redacted `compact_summary` beside the latest checkpoint, so the summary is recoverable.
- **Restored by `SessionStart`:**

| Source | Injected |
|---|---|
| `compact` | the full checkpoint, capped at 8,000 characters (under the 10,000 limit) |
| `startup`, `clear` | the existing short Chatur context plus one line pointing to `chatur checkpoint show`; `/clear` stays cheap for unrelated work |
| `resume`, `fork` | the short context; if `prompt_cache_likely_expired`, a `systemMessage` with `context_tokens` and `estimated_cache_write_usd` so the human sees the cost of resuming |

- **Never blocks compaction.** Blocking can fail a request recovering from a context-limit error; checkpoint failures fail open (ADR-0012).
- `chatur checkpoint save|show|list`. Masked by `chatur.redact` before writing.

### 2. Memory tiers
| Tier | Where | Lifetime | Written by |
|---|---|---|---|
| **Decisions and artifacts** | ADRs, phase docs, `docs/baseline/` | permanent, committed | agents propose, humans accept |
| **Project notes** | `.chatur/memory.jsonl` via `chatur memory add "<fact>" --kind constraint\|gotcha\|convention` | until removed | agents (with approval) and humans |
| **Checkpoints** | `.chatur/checkpoints/` | last 20, local | hooks and the CLI |
| **Assistant memory** | e.g. Claude auto memory | assistant-specific | the assistant; Chatur doesn't manage it |

Notes are portable across assistants, capped (50 notes, 4,000 characters total; `add` refuses beyond that and asks
for pruning), and rejected if `find_secrets` matches. **Re-injected text can carry prompt injection across sessions**,
so notes are labelled as data and not instructions, record who added them, and `chatur memory list|remove` lets a human review them.
Agents add notes only through the CLI (`harness.read-only` still denies direct edits); `remove` is human-only.

### 3. Trimming large shell output
`PostToolUse` on shell tools only, when combined output exceeds **8,000 characters**: `updatedToolOutput` carries the
first 40 lines, the last 80 lines, up to 40 lines matching error patterns (`error`, `fail`, `exception`, `traceback`,
`panic`), and a marker stating how much was removed and where the full output is. The full output is saved redacted to
`.chatur/outputs/<tool_use_id>.txt` (gitignored; last 50 kept), readable with the Read tool.
- **Fails open:** any error, or an unknown output shape, returns nothing and Claude sees the original.
- **Never trims** failed commands (`PostToolUseFailure` has no rewrite), file reads, search results, or MCP output.
- `Bash`'s shape is documented; `PowerShell`'s must be verified by capture before enabling it there.
- Configurable: `[context] trim_output_chars` in `config.toml`; `0` disables.

### 4. Protecting the prompt cache (guardrails on Chatur itself)
| Rule | Why (documented behaviour) | Enforced by |
|---|---|---|
| Core rule is **unscoped**: `"**"` emits no `paths:` (the source keeps `applyTo` for Copilot; ADR-0034) | stays in the cached project-context layer and survives compaction | adapter test (done) |
| No `model:` in Chatur commands or skills | a command naming another model is a model switch and a full cache miss | primitive test |
| Native deny rules stay **scoped** (`Bash(git push *)`), never a bare tool name | scoped rules leave the prefix intact | adapter test |
| Hooks add no per-turn context | hook text is appended to the conversation and costs tokens every later turn | code review + test |
| Always-loaded text has a budget: core rule ≤ 2,500 characters, each description ≤ 300 | CLAUDE.md-style content is sent with every request | primitive test |

Compaction guidance is added to the core rule (`# Compact instructions`: keep phase, active change, gate states, open
decisions, file paths, failing tests, denied actions). Claude Code documents this heading for CLAUDE.md; whether it
works from an unscoped rule **must be verified**, and if not, `chatur init` offers a managed block in CLAUDE.md.

### 5. Opt-in cost settings
- **Cache lifetime:** `chatur hooks install claude --cache-ttl 1h` writes `promptCacheTtl` and `subagentPromptCacheTtl`.
  Default lifetime is 5 minutes for API-key billing and for subagents. Chatur asks a human before every command and edit,
  so *our inference* is that a slow approval can let the cache expire and cost a full re-read on the next request.
  1h has a higher cache-write rate, so it's opt-in, not default.
- **Per-agent model:** `.chatur/config.toml` `[models] chatur-docs = "haiku"`. Applied only by `chatur primitives install`
  (APM copies agent files verbatim, ADR-0027). Subagents have their own conversation, so this doesn't disturb the parent's cache.

### 6. Workflow guidance (in the core rule and phase commands)
- At a gate approval, suggest a natural break: `/clear` is free and phase docs hold the knowledge; `/compact` only when
  continuity matters. `chatur gate approve` prints this.
- Delegate verbose work (test runs, log reading, broad exploration) to subagents so only a summary returns.
- Put the most important instructions first in `SKILL.md`: after compaction, skill bodies are capped at 5,000 tokens each, keeping the start.

### 7. Visibility
`chatur context` reports Chatur's always-loaded size against the budget, plus from the audit log: compactions, trims and
characters removed, checkpoints written. It doesn't claim token or dollar totals, which hooks don't receive; it points to
`/usage` and `/context`. A status-line integration is a possible follow-up.

### 8. Portability
New additive `EventKind`s `pre_compact` and `post_compact`, with `PreCompact` and `PostCompact` added to the Claude hook
set. Trimming and restore go through adapter functions; other adapters may no-op. Copilot's `preCompact` and
`postToolUse` `modifiedResult` are the expected Phase 4 mappings (to verify then).

## Consequences
- Positive: work survives compaction and new sessions; large outputs cost less; Chatur stops weakening its own rules and can't quietly break the cache.
- Negative: more `.chatur/` files; re-injected notes are a persistence channel (mitigated above); trimming can hide a useful line (mitigated by error-line
  retention and the saved full output); savings aren't measurable from hooks alone.

## Open questions
1. Is 8,000 characters the right threshold? To tune while dogfooding.
2. Should checkpoints record the `git status` file list when it's very long (cap vs summarise)?

## Guardrails / best practices this implies
- Tests: checkpoint contents, redaction, retention, and the 8,000-character cap; restore per `source`; compaction never blocked and failures fail open;
  trim boundaries, error-line retention, Bash shape, unknown shape returning nothing, full output redacted; note caps, secret rejection, and data labelling;
  every row of the cache table; event mappings and APM hook drift; hook budget still under 500 ms.
