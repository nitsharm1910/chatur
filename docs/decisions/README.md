# Decision Log

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions as ADRs | Accepted |
| [0002](0002-multi-assistant-agents-md-canonical.md) | AGENTS.md as canonical instructions | Accepted |
| [0003](0003-package-as-apm.md) | Package as APM package | Accepted |
| [0004](0004-python-core-normalized-events.md) | Python core + normalized events + adapters | Accepted |
| [0005](0005-defense-in-depth-enforcement.md) | Defense-in-depth enforcement | Accepted |
| [0006](0006-in-repo-tracking.md) | In-repo tracking (audit JSONL, state, ADRs) | Accepted |
| [0007](0007-tiered-guardrail-profiles.md) | Tiered guardrail profiles | Accepted |
| [0008](0008-human-approved-phase-gates.md) | Human-approved phase gates | Accepted |
| [0009](0009-v1-targets-claude-copilot.md) | v1 targets: Claude Code + Copilot | Accepted |
| [0010](0010-agent-roster.md) | SDLC agent roster (9 agents) | Accepted |
| [0011](0011-distribution.md) | Distribution: APM package + pip core | Accepted |
| [0012](0012-python-311-stdlib-hook-path.md) | Python ≥3.11 (CI to latest), TOML, stdlib-only hook path | Accepted |
| [0013](0013-license-apache-2.md) | License under Apache-2.0 | Accepted |
| [0014](0014-human-in-the-loop-baseline.md) | Human-in-the-loop baseline: git deny, file/exec ask (amends 0007) | Accepted |
| [0015](0015-audit-full-commands-masked.md) | Audit stores full commands, secrets masked (refines 0006) | Accepted |
| [0016](0016-policy-schema-and-composition.md) | Policy schema v1, tighten-only composition | Accepted |
| [0017](0017-guard-matching-semantics.md) | Guard matching semantics and shell bypass handling | Accepted |
| [0018](0018-deny-remote-write-clis.md) | Deny remote-write CLIs (gh/glab/hub); `argv_patterns` selector (amends 0014, 0016) | Accepted |
| [0019](0019-audit-log-format-and-integrity.md) | Audit log format, hash chain, concurrency | Accepted |
| [0020](0020-chatur-check-cli.md) | `chatur check` dry-run CLI | Accepted |
| [0021](0021-phase-gate-state.md) | Phase gate state, approval rules, audit anchoring | Accepted |
| [0022](0022-project-init-and-adr-cli.md) | `chatur init` layout, audit-commit defaults, `chatur adr` CLI | Accepted |
| [0023](0023-secret-detection-rules.md) | Secret-detection baseline rules, tiered (implements 0007) | Accepted |
| [0024](0024-adr-supersede-workflow.md) | ADR supersede workflow | Accepted |
| [0025](0025-claude-code-adapter.md) | Claude Code adapter, hook entrypoint, install (fixes ADR-0006 content logging) | Accepted |
| [0026](0026-claude-permission-modes.md) | Claude permission modes vs "ask" (auto observed attended) | Accepted |
| [0027](0027-sdlc-primitives.md) | SDLC primitives: agents + write scopes, commands, skills, templates | Accepted |

List from the CLI: `chatur adr list` · create: `chatur adr new "<title>"`.

New decision: copy [0000-template.md](0000-template.md), use the next number, status `Proposed`.
