# Chatur Architecture

Status: **Draft v0.1** — 2026-10-02. Decisions referenced as ADR-NNNN in [decisions/](decisions/).

## 1. Goal
One baseline harness that any project can install to get a governed, auditable, full-SDLC
AI workflow — regardless of which AI coding assistant the team uses.

## 2. Layers

```
┌───────────────────────────────────────────────────────────────────────┐
│ L1  Canonical primitives  (.apm/)                     ADR-0002, 0003   │
│     instructions · agents · prompts · skills · hook declarations       │
│     authored ONCE, compiled per assistant by APM                       │
├───────────────────────────────────────────────────────────────────────┤
│ L2  Python core  (src/chatur, `chatur` CLI)           ADR-0004, 0012   │
│     events ─► guard engine ─► decision (allow / deny / ask / warn)     │
│              │                                                         │
│              ├─► audit log   (.chatur/audit/*.jsonl)   ADR-0006        │
│              ├─► phase gates (.chatur/state.json)      ADR-0008        │
│              └─► ADR tooling (docs/decisions/)                         │
├───────────────────────────────────────────────────────────────────────┤
│ L3  Adapters                                          ADR-0004, 0009   │
│     claude_code  · copilot   (v1)                                      │
│     codex · gemini · cursor  (instructions-only until built)           │
│     sdk_runner               (later: CI / headless)                    │
├───────────────────────────────────────────────────────────────────────┤
│ L4  Backstop enforcement  (assistant-independent)     ADR-0005         │
│     git pre-commit / pre-push hooks · CI workflow (`chatur ci-check`)  │
└───────────────────────────────────────────────────────────────────────┘
```

**Principle:** a guardrail only counts as *enforced* if at least one layer outside the
assistant's own goodwill can block it. Instructions (L1) guide; hooks (L3) enforce in-session;
git/CI (L4) enforce regardless of assistant.

## 3. Event flow (in-session hook)

```
assistant hook fires ──stdin JSON──► chatur hook <assistant> <event>
                                        │
                        adapters/<assistant>.parse()  → ChaturEvent
                                        │
                        guard.evaluate(event, policy)  → Verdict
                                        │
                        audit.append(event, verdict)
                                        │
                        adapters/<assistant>.render(verdict) ──stdout/exit code──► assistant
```

### ChaturEvent (normalized; implemented in [`src/chatur/events.py`](../src/chatur/events.py))
| Field | Type | Notes |
|-------|------|-------|
| `schema` | str | `chatur.event/v1` |
| `id`, `ts` | str | time-ordered id (12 hex ms + 16 hex random), ISO-8601 UTC with `Z` |
| `kind` | enum | `session_start`, `prompt`, `pre_tool`, `post_tool`, `tool_failure`, `stop`, `subagent_start`, `subagent_stop`, `session_end`, `error` |
| `assistant` | str | adapter id: `claude_code`, `copilot`, … |
| `session_id`, `cwd` | str | from assistant |
| `tool` | ToolCall? | `{category: shell\|file_read\|file_write\|search\|web\|agent\|mcp\|other, name, args, command, paths}` |
| `prompt` | str? | user prompt text (`prompt` events) |
| `agent` | str? | active subagent/custom agent when exposed (ADR-0010 write scopes) |
| `phase` | str? | current SDLC phase from `.chatur/state.json` |
| `attended` | bool | `false` only when no human can answer → `ask` becomes `deny` (ADR-0014) |
| `raw` | obj | original native payload |

Events are immutable. `to_dict()` masks secrets by default (ADR-0015); the guard engine always sees unmasked values.

### Verdict ([`src/chatur/verdict.py`](../src/chatur/verdict.py))
`Decision`: `allow < log < warn < ask < deny`. A `Verdict` combines all matching `RuleHit`s;
the **strictest wins**, and every hit is kept for the audit log.

### Native event mapping (v1)
| ChaturEvent.kind | Claude Code | Copilot |
|---|---|---|
| session_start | `SessionStart` | `sessionStart` |
| prompt | `UserPromptSubmit` | `userPromptSubmitted` |
| pre_tool | `PreToolUse` | `preToolUse` |
| post_tool | `PostToolUse` | `postToolUse` |
| tool_failure | `PostToolUseFailure` | `postToolUseFailure` |
| stop | `Stop` | `agentStop` |
| subagent_start/stop | `SubagentStart`/`SubagentStop` | `subagentStart`/`subagentStop` |
| session_end | `SessionEnd` | `sessionEnd` |
| error | — | `errorOccurred` |

Deny rendering: Claude → JSON `hookSpecificOutput.permissionDecision: "deny"` (or exit 2);
Copilot → JSON `permissionDecision: "deny"` + `permissionDecisionReason` (or exit 2).

### Policy composition ([`src/chatur/policy.py`](../src/chatur/policy.py), ADR-0016)
```
baseline.toml  ──►  <profile>.toml  ──►  .chatur/policy.local.toml
 (always; can't     (strict|standard|      (optional; add rules,
  be weakened)       relaxed|custom)        tighten, extra redaction)
```
Each later layer can **add** rules and **tighten** existing ones, never loosen. Unknown keys,
weaker verdicts, and redefined rules are load errors, and every problem is reported in one
`PolicyError`. Inspect the result with `chatur policy show` and check it with `chatur policy validate`.

### Guard engine ([`guard.py`](../src/chatur/guard.py), [`shell.py`](../src/chatur/shell.py), ADR-0017)
`evaluate(event, policy, ctx) -> Verdict` is pure (no I/O). For shell tools, `shell.analyze()` reads
the command as written, with PowerShell backtick escapes removed, and with cmd caret escapes removed.
It recurses into nested shells, substitutions, `-EncodedCommand`, `eval`/`iex`, and `Start-Process`,
and extracts argv lists, git invocations (after global options), candidate paths, and problems.
Problems → `defaults.unparseable_command` (ask). `GuardContext` carries facts from other layers
(approved gates, ADR changed, missing tests). Secret detection (ADR-0023) reuses the `redact`
patterns via the `contains_secret` selector over file-write content (not `old_*` args), shell texts,
tool args, and prompts; placeholders and env/secret-store references are ignored.
Measured (step 1.8): fresh-process hook path p95 ~194 ms incl. interpreter startup; in-process
load+evaluate p95 ~4 ms.

### Audit log ([`audit.py`](../src/chatur/audit.py), ADR-0019)
`AuditLog(root).append(event, verdict)` takes an OS file lock, reads and hash-checks the last
record, then appends one redacted canonical-JSON line to `.chatur/audit/YYYY-MM-DD.jsonl` (UTC) and
fsyncs. Each record carries `seq`, `prev` (the previous record's hash), and `hash`, forming one chain
across days. `chatur audit verify` reports edits, deletions, insertions, reordering, truncated lines,
and missing earlier files. Removal of the newest records isn't detectable from the chain alone
(mitigated by committing the log, plus a planned gate-approval anchor).

### Phase gates ([`gates.py`](../src/chatur/gates.py), ADR-0021)
`.chatur/state.json` records each approved phase: approver, time, artifact digest, and an audit anchor
`(seq, hash)`. `approve` needs a TTY, a typed confirmation, no agent/CI env markers, earlier gates
approved and fresh, at least one artifact, and an intact audit log. `revoke` cascades to later phases.
Hooks read recorded approvals only (`approved_gates()`, no hashing). `chatur gate verify` (git/CI)
catches stale gates, out-of-order state, and anchors missing from the audit chain. Agents are
denied `chatur gate approve|revoke` by baseline rule `gate.no-agent-approval`.

### Dry run (`chatur check`, ADR-0020)
Evaluates one shell command, file read/write, or tool call against the project policy without
executing or logging it. Exit codes: 0 allow/log/warn, 2 ask, 3 deny, 1 error.

### Claude Code adapter ([`adapters/claude_code.py`](../src/chatur/adapters/claude_code.py), [`hook.py`](../src/chatur/hook.py), ADR-0025/0026)
Claude runs `chatur hook claude_code <Event>` (exec form, no shell) with the payload on stdin.
`run_hook` parses → evaluates (PreToolUse, UserPromptSubmit, Stop, SubagentStop) → appends to the
audit log (every handled event; file-write content stored as sha256 + length only) → renders.
PreToolUse returns only `ask`/`deny` (never `allow`, which would skip Claude's prompt) and fails closed
(exit 2) on any internal error. `chatur hooks install claude [--local]` merges hooks and ~88 native
`permissions.deny` rules into `.claude/settings[.local].json`. Claude enforces those rules itself, even if
Chatur can't run. `.apm/hooks/chatur-claude.json` ships the same hooks via APM.

### SDLC primitives (`.apm/`, ADR-0027)
9 agents (`chatur-orchestrator`, `-product-analyst`, `-architect`, `-security`, `-developer`, `-qa`,
`-reviewer`, `-devops`, `-docs`) with only `name`/`description` frontmatter, so they work in every
assistant. **Least privilege is enforced by Chatur:** baseline `[agents.*]` write scopes +
`agent.read-only` (deny) + profile `agent.write-scope` (strict deny, else ask), keyed on the agent
identity the assistant reports. Commands `/chatur-status|requirements|design|build|test|review|release|adr|check`
each end with the human's `chatur gate approve <phase>` step. Seven skills carry the templates in
`assets/`; `chatur init` installs the same templates in `docs/templates/`.

### Harness boundary (ADR-0029)
Everything Chatur installs into a project is **harness**, and agents may never write it: `.chatur/**`,
`.claude/settings*.json`, `.claude/{agents,commands,rules}/chatur-*`, `.claude/skills/chatur-*/**`, and the
install manifest. The baseline rule `harness.read-only` denies it (critical: hook + git + CI), for file
writes and for any shell mention including parent directories. Regenerable **tooling** is gitignored;
**governance records** (config, local policy, gate state, audit) stay committed.

## 4. What gets installed into a target project
```
<target>/
  AGENTS.md / CLAUDE.md / .github/copilot-instructions.md   (compiled by APM)
  .claude/{agents,skills,commands,rules,settings.json}        (Claude target)
  .github/{agents,prompts,instructions,hooks}                 (Copilot target)
  .chatur/                       # harness, agent read-only (ADR-0029); created by `chatur init`
    config.toml        # committed: profile, assistants, audit.commit, gate artifact overrides
    policy.local.toml  # committed: tighten-only local policy (ADR-0016)
    state.json         # committed: gate approvals (written by `chatur gate`, ADR-0021)
    audit/YYYY-MM-DD.jsonl   # committed unless audit.commit = false
    templates/         # gitignored: SDLC templates (regenerated by `chatur init`)
  .claude/{agents,commands,skills,rules}/chatur-*   # gitignored: `chatur primitives install claude`
  .claude/settings.local.json                       # gitignored: `chatur hooks install claude --local`
  docs/
    decisions/         # ADRs: 0000-template.md + `chatur adr new`
    requirements/  design/  security/  test/  review/  releases/   (README.md in each)
  .gitignore           # managed block; ignores .chatur/audit/ only when audit.commit = false
```

## 5. SDLC phases & agents (ADR-0008, ADR-0010)
| Phase | Owner agent | Exit artifact | Gate |
|-------|-------------|---------------|------|
| 1 Requirements | product-analyst | `docs/requirements/PRD-*.md` | human approve |
| 2 Design | architect (+ security: threat model) | `docs/design/*.md`, ADRs, `docs/security/threat-model.md` | human approve |
| 3 Build | developer | code + unit tests | human approve |
| 4 Test | qa | `docs/test/test-report-*.md` | human approve |
| 5 Review | reviewer (+ security) | review report | human approve |
| 6 Release | devops (+ docs) | release notes, CHANGELOG, tag | human approve |
| cross-cutting | orchestrator, docs | routing, phase status, docs upkeep | — |

## 6. Open questions
Tracked in [roadmap.md](roadmap.md#open-questions).
