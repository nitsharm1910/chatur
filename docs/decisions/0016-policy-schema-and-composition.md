---
id: ADR-0016
title: Policy schema v1 and tighten-only composition
status: Accepted
date: 2026-10-03
deciders: Nitin
phase: design
tags: [policy, guardrails, schema]
refines: [ADR-0007, ADR-0014]
---

# ADR-0016: Policy schema v1 and tighten-only composition

## Context
ADR-0007 defines profiles and a baseline that can't be weakened; ADR-0014 fills in the baseline.
The loader needs an exact schema and merge rules. Two risks matter most: a typo that quietly
weakens a rule (e.g. `verdcit = "allow"`), and a local file that loosens a profile.

## Decision

### Files and layering
1. `baseline.toml` (`kind = "baseline"`): every rule has `baseline = true`. Always loaded.
2. `<profile>.toml` (`kind = "profile"`): `strict`, `standard`, `relaxed`, or a custom profile file.
3. `.chatur/policy.local.toml` (`kind = "local"`, optional, per target project).

Packaged policies live in `src/chatur/policies/` (shipped in the wheel). The profile name is chosen
in `.chatur/config.toml` → `[policy] profile = "…"` and defaults to `standard`.

### Tighten-only (maintainer decision)
Profiles and local files may:
- **add** new rules (never `baseline = true`; never reuse an existing id);
- **tighten** existing rules via `[tighten."<rule-id>"] verdict/unattended`, only to an equal or stricter decision;
- **tighten** `[defaults]`;
- (local only) **add** redaction patterns `[redact] extra_patterns` (ADR-0015).

Anything that would loosen (a weaker verdict, redefining a rule, disabling it, enabling the read-only
allowlist outside baseline) is a **load error**. To loosen, a project picks a different profile.
Because the strictest matching rule always wins (ADR-0014), an added `allow` rule can never override
another rule's `ask` or `deny`.

### Rule schema (`[[rule]]`)
| Key | Required | Notes |
|---|---|---|
| `id` | ✓ | `^[a-z0-9][a-z0-9_.-]*$`, unique across all layers |
| `verdict` | ✓ | `allow \| log \| warn \| ask \| deny` |
| `reason` | ✓ | shown to the agent and the human |
| `unattended` | | default: `deny` if verdict is `ask`, else same as verdict; must be ≥ verdict |
| `adr` | | decision that justifies the rule |
| `baseline` | | baseline file only |
| `critical` | | if true, `layers` must include `git` or `ci` (ADR-0005) |
| `layers` | | subset of `hook, git, ci`; default `["hook"]` |
| `applies_to` | | `tool_category = [...]` (empty = any tool), `events = [...]` (default `["pre_tool"]`) |
| `match` | ✓ | see below; at least one key |

### Match semantics
- **Selectors** (`any`, `file_write`, `shebang`, `path_globs`, `shell_patterns`, `git_subcommands`,
  `git_patterns`, `tool_name_patterns`) are **OR-ed**: any one hit selects the event.
- **Conditions** (`requires_gate = "<phase>"`, `requires_adr`, `missing_tests`) are **AND-ed** with the
  selector result. A rule with only conditions applies to every event it covers.
- Unknown keys anywhere → load error (stops typos from silently weakening a rule).

### Failure behaviour
`load_policy` collects **all** problems and raises one `PolicyError`. Hook entrypoints that can't
load a valid policy apply `adapter_error` (deny) on pre-tool events. They fail closed (ADR-0012).

## Consequences
- Positive: a project file can't weaken a guardrail, and typos fail loudly.
- Negative: loosening means switching profile (or writing a custom profile file inside Chatur, which needs review).

## Guardrails / best practices this implies
- `chatur policy validate` runs in CI and in the git pre-commit hook.
- Tests cover every loosening path (weaker verdict, redefinition, unknown key, local baseline flag, allowlist enable) and confirm each is rejected.
