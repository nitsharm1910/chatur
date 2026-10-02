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

### ChaturEvent (normalized; draft)
| Field | Type | Notes |
|-------|------|-------|
| `schema` | str | `chatur.event/v1` |
| `id`, `ts` | str | ULID-ish id, ISO-8601 UTC |
| `assistant` | str | `claude_code`, `copilot`, … |
| `session_id` | str | from assistant |
| `kind` | enum | `session_start`, `prompt`, `pre_tool`, `post_tool`, `tool_failure`, `stop`, `subagent_start`, `subagent_stop`, `session_end`, `error` |
| `tool` | obj? | `{category: shell\|file_read\|file_write\|search\|web\|agent\|other, name, args}` |
| `phase` | str | current SDLC phase from `.chatur/state.json` |
| `cwd` | str | |
| `raw` | obj | original payload (redacted) for debugging |

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

## 4. What gets installed into a target project
```
<target>/
  AGENTS.md / CLAUDE.md / .github/copilot-instructions.md   (compiled by APM)
  .claude/{agents,skills,commands,rules,settings.json}        (Claude target)
  .github/{agents,prompts,instructions,hooks}                 (Copilot target)
  .chatur/
    config.toml        # profile, enabled assistants, phase gate settings
    state.json         # current phase + approvals
    audit/YYYY-MM-DD.jsonl
  docs/
    decisions/         # project ADRs (template from Chatur)
    requirements/  design/  test/  security/  releases/
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
