# Chatur Roadmap

Legend: ✅ done · 🔄 in progress · ⏳ planned

## Phase 0 — Foundation 🔄
- ✅ Repo skeleton, git init
- ✅ AGENTS.md / CLAUDE.md for developing Chatur
- ✅ Architecture draft ([architecture.md](architecture.md))
- ✅ ADR-0001…0011 accepted, ADR-0012 proposed
- ⏳ `apm.yml`, `pyproject.toml`, `.gitignore`, LICENSE
- ⏳ Maintainer review of architecture + ADR-0012

## Phase 1 — Python core (no assistant yet)
- `ChaturEvent`, `Verdict` models
- Policy loader (TOML, profiles, baseline-not-weakenable)
- Guard engine + baseline rules (secrets, destructive shell, protected paths)
- Audit writer (JSONL, redaction, hash chain)
- Phase state + `chatur gate status|approve`
- `chatur adr new|list|supersede`
- `chatur init` (writes `.chatur/`, docs folders)

## Phase 2 — Claude Code adapter (reference)
- Adapter parse/render + recorded fixtures
- `.apm/hooks/*` declarations → `.claude/settings.json`
- Verify `apm compile`/`apm install` output for Claude target

## Phase 3 — Primitives
- 9 agents (`.apm/agents/`), SDLC instructions, prompts (`/chatur-plan`, `/chatur-approve`, `/chatur-status`…), skills per phase
- Artifact templates (PRD, design, threat model, test plan/report, review, release notes)

## Phase 4 — Copilot adapter
- `.github/hooks/*.json` (version 1), bash + powershell, cloud-agent constraints
- Copilot agents/prompts/instructions verification

## Phase 5 — Backstop
- `chatur git-hook pre-commit|pre-push`
- `chatur ci-check` + reusable GitHub Actions workflow

## Phase 6 — Release v1.0
- Dogfood on a sample target project end-to-end, docs, tag `v1.0.0`

## Later
- Codex, Gemini, Cursor adapters · SDK runner for CI/headless · external exporters (GitHub Issues/Jira)

## Open questions
1. ADR-0012: accept 3.11 floor (3.14 dev, 3.11–3.14 CI matrix)? Maintainer asked "why not 3.14"; rationale added to ADR.
2. Package/CLI name on PyPI: is `chatur` free? Fallback `chatur-harness`.
3. ~~License~~: Apache-2.0 (ADR-0013).
4. GitHub owner/org for `apm install <owner>/chatur`: deferred, placeholder `<owner>`.
5. Should the audit log be committed by default in `standard` profile?
