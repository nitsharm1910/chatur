---
id: ADR-0021
title: Phase gate state, approval rules, and audit anchoring
status: Accepted
date: 2026-10-04
deciders: Nitin
phase: design
tags: [gates, sdlc, audit]
refines: [ADR-0008, ADR-0019]
---

# ADR-0021: Phase gate state, approval rules, and audit anchoring

## Context
ADR-0008 requires human-approved gates with the approver, timestamp, and artifact hash, and requires
that agents can never approve. ADR-0019 noted that tail truncation of the audit log needs an anchor.

## Decision

### State file `.chatur/state.json` (`chatur.state/v1`)
```json
{
  "schema": "chatur.state/v1",
  "gates": {
    "design": {
      "approved_by": "Nitin <n@example.com>",
      "approved_at": "2026-10-04T10:00:00.000Z",
      "os_user": "nitin",
      "artifacts": { "digest": "<sha256>", "file_count": 3, "files": ["docs/design/api.md", "..."] },
      "audit_anchor": { "seq": 41, "hash": "<sha256>" },
      "note": "optional"
    }
  }
}
```
Written atomically (temp file + rename) and only by the `chatur` CLI. The current phase is the first
phase that isn't approved.

### Phases and artifacts
Order: `requirements → design → build → test → review → release`. Artifact globs per phase can be
overridden in `.chatur/config.toml` `[gates.<phase>] artifacts = [...]`. Defaults:

| Phase | Default artifact globs |
|---|---|
| requirements | `docs/requirements/**/*.md` |
| design | `docs/design/**/*.md`, `docs/security/threat-model*.md` |
| build | `src/**`, `tests/**` |
| test | `docs/test/**/*.md` |
| review | `docs/review/**/*.md` |
| release | `docs/releases/**/*.md`, `CHANGELOG.md` |

The digest is SHA-256 over the sorted `(path, sha256(file))` list. `files` is stored only when there
are ≤ 100 files. Walks skip `.git`, `.chatur`, `.venv`, `venv`, `node_modules`, `__pycache__`, `dist`, `build`.

### `chatur gate approve <phase>` refuses unless all of these hold
1. **Human at a terminal:** stdin and stdout are TTYs, **and** the human types the phase name to
   confirm. There's no `--yes` flag, so nothing scriptable can approve.
2. **Not inside an agent or CI session:** none of `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`,
   `CHATUR_AGENT_SESSION`, `COPILOT_AGENT_ID`, `GITHUB_ACTIONS`, `CI` is set.
3. **Sequential:** every earlier phase is approved and not stale.
4. **Artifacts exist:** at least one file matches the phase's globs.
5. **Audit log intact:** `audit verify` passes. The anchor is the last audit record; the approval itself
   is then appended to the audit log (`kind = "gate"`).

`chatur gate revoke <phase>` (same human checks) removes that gate **and every later gate**.

### Staleness and verification
- A gate is **stale** when its artifact digest no longer matches.
- `chatur gate status` shows approved / stale / pending per phase.
- `chatur gate verify` (for CI and pre-commit) exits 1 if any gate is stale, or if an anchor
  `(seq, hash)` isn't in the audit chain (detects audit tail truncation, closing ADR-0019's gap).
- In-session hooks use the **recorded** approvals (`approved_gates()`, no hashing) to stay inside the
  500 ms budget (ADR-0012). Staleness is enforced by `gate verify` in git/CI (ADR-0005).

### Agents can't approve (baseline)
New baseline rule `gate.no-agent-approval` (deny) matches `chatur gate approve|revoke` and
`python -m chatur gate approve|revoke` (ADR-0008).

## Consequences
- Positive: approvals are tied to exact artifact content and to a point in the audit log.
- Negative: approving needs an interactive terminal; editing an approved artifact invalidates the gate (by design).

## Guardrails / best practices this implies
- Tests: each refusal condition, staleness, sequential order, revoke cascade, anchor verification, atomic write, and the baseline deny rule.
