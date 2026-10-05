---
id: ADR-0025
title: Claude Code adapter, hook entrypoint, and installation
status: Accepted
date: 2026-10-04
deciders: Nitin
phase: design
tags: [adapter, claude-code, hooks, install]
refines: [ADR-0003, ADR-0004, ADR-0005, ADR-0006, ADR-0009, ADR-0012, ADR-0014]
---

# ADR-0025: Claude Code adapter, hook entrypoint, and installation

## Context
Claude Code is the reference adapter (ADR-0009). Facts from the Claude Code hooks reference that drive this design:
- Hooks are configured in `.claude/settings.json` / `.claude/settings.local.json`
  (`hooks.<Event>[] = {matcher, hooks: [{type: "command", command, args?, timeout}]}`).
  **Exec form** (`command` + `args`) skips the shell.
- **Hooks fail open:** a missing command, a timeout, or any exit code other than 2 lets the action proceed.
- PreToolUse JSON output: `hookSpecificOutput.permissionDecision = allow|deny|ask` + `permissionDecisionReason`.
  Returning `allow` would **skip** Claude's own permission prompt, so Chatur never returns it.
- SessionStart can persist environment variables through `CLAUDE_ENV_FILE`.
- APM accepts Claude-format hook files in `.apm/hooks/` and merges them into `.claude/settings.json`.

## Decision (maintainer choices marked ★)

### Adapter (`chatur.adapters.claude_code`)
- **Events:** `SessionStart→session_start`, `UserPromptSubmit→prompt`, `PreToolUse→pre_tool`,
  `PostToolUse→post_tool`, `PostToolUseFailure→tool_failure`, `Stop→stop`, `SubagentStart/Stop`,
  `SessionEnd→session_end`. Other events are ignored (exit 0).
- **Tools:** `Bash`, `PowerShell` → shell · `Write`, `Edit`, `MultiEdit`, `NotebookEdit` → file_write ·
  `Read`, `NotebookRead` → file_read · `Glob`, `Grep`, `LS` → search · `WebFetch`, `WebSearch` → web ·
  `Task`, `Agent` → agent · `mcp__*` → mcp · assistant-internal tools (`TodoWrite`, `AskUserQuestion`,
  `ExitPlanMode`, `EnterPlanMode`, `ToolSearch`, `Skill`, `BashOutput`, …) → new category **`internal`**
  (no rules; allowed and logged) · anything else → `other` (`defaults.unknown_tool`: ask/deny).
- **Attended:** `false` when `permission_mode == "dontAsk"` or `CI`/`GITHUB_ACTIONS` is set.
  ★ *Verify first:* how a hook's `ask` behaves in `auto`, `acceptEdits`, and `bypassPermissions` will be
  observed while dogfooding and fixed in a follow-up ADR.
- **raw** keeps only small metadata fields (`hook_event_name`, `tool_use_id`, `permission_mode`,
  `agent_id`, `agent_type`, `source`, `reason`, `stop_hook_active`, `model`), never `tool_input`,
  `tool_response`, or transcripts.

### Rendering verdicts
| Event | allow / log | warn | ask | deny |
|---|---|---|---|---|
| PreToolUse | no output (Claude's normal flow) | `systemMessage` | `permissionDecision: ask` | `permissionDecision: deny` |
| UserPromptSubmit | none | `systemMessage` | `systemMessage` | `decision: block` |
| Stop / SubagentStop | none | `systemMessage` | `systemMessage` | `decision: block` (not when `stop_hook_active`) |
| others | audit only | | | |

SessionStart returns `additionalContext` (Chatur active, profile, current phase, key rules) and appends
`CHATUR_AGENT_SESSION=1` to `CLAUDE_ENV_FILE`, so gate approval and the git backstop can recognise agent shells.

### Hook entrypoint (`chatur hook claude_code [EVENT]`)
Reads the JSON on stdin; project root = `CLAUDE_PROJECT_DIR`, else `cwd`; loads the project policy and
recorded gates; evaluates; appends to the audit log; renders. **Fail closed on PreToolUse:** any
exception (bad input, invalid policy, audit failure) → `deny` with the reason, and exit code 2 if even
rendering fails. Other events fail open (warning on stderr), per ADR-0012.

### Audit content (fixes an ADR-0006 gap)
File-write events are logged with **paths only**. Every other string argument (`content`,
`new_string`, `edits`, …) is replaced by `{"sha256": …, "chars": n}`. Shell commands are still logged in full (ADR-0015).

### Installation
- ★ **Both channels from one generator:** `.apm/hooks/chatur-claude.json` (shell-form command string,
  for APM) and `chatur hooks install claude` write the same events. A test keeps the APM file in sync.
- ★ **Invocation:** shared settings call `chatur` from PATH (`pipx install chatur`);
  `--local` writes `.claude/settings.local.json` with this machine's absolute interpreter
  (`<python> -m chatur hook claude_code`), for dev and dogfooding.
- **Native backstop:** install also adds Claude `permissions.deny` rules for the critical commands
  (git commit/push/merge/rebase/reset --hard/tag/…, gh/glab remote writes, `chatur gate approve|revoke`,
  edits to `.chatur/state.json` and `.chatur/audit/**`). Claude enforces these itself even if Chatur
  can't run, which covers the fail-open case. They're prefix-based (weaker than Chatur's analyser), so
  they're a second layer, not a replacement.
- Install is idempotent: it replaces earlier Chatur entries, keeps everything else, and `uninstall` removes only Chatur's entries.
- ★ **Dogfood:** install on this repo with `--local` as soon as the adapter passes its tests.

## Consequences
- Positive: in-session enforcement for Claude Code, with a native deny layer that still works if Chatur is missing.
- Negative: every hook spawns a Python process (~200 ms, ADR-0012 budget). Prompts for every command and edit (ADR-0014) are now real.

## Guardrails / best practices this implies
- Fixture tests for every event and tool category; render tests for every decision × event; a fail-closed
  test for each failure mode; an install round-trip test (install → reinstall → uninstall leaves foreign settings intact); an APM drift test.
