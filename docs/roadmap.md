# Chatur Roadmap

Legend: ✅ done · 🔄 in progress · ⏳ planned

## Phase 0 — Foundation ✅
- ✅ Repo skeleton, git init, pushed to `nitsharm1910/chatur`
- ✅ AGENTS.md / CLAUDE.md for developing Chatur
- ✅ Architecture draft ([architecture.md](architecture.md))
- ✅ ADR-0001…0014 accepted
- ✅ `.gitignore`, LICENSE (Apache-2.0), draft `policies/baseline.toml`

## Phase 1 — Python core (no assistant yet) 🔄
- ✅ 1.1 `pyproject.toml`, `apm.yml`, package layout, CLI stub, pytest + ruff, CI matrix (3.11→3.14 + 3.15 pre-release, 3 OSes)
- ✅ 1.2 ChaturEvent + Verdict models, secret masking (`redact`) — ADR-0015
- ✅ 1.3 Policy loader (tighten-only), 3 profiles, `chatur policy validate|show` — ADR-0016
- ✅ 1.4 Guard engine + shell analyser + bypass suite (~80 bypasses) — ADR-0017
- ✅ 1.4b Remote-write CLIs denied (gh/glab/hub) — ADR-0018
- ✅ 1.5 Audit log: redacted, hash-chained JSONL, cross-process lock, `chatur audit verify|tail` — ADR-0019 (Proposed)
- ⏳ 1.6 Gates · 1.7 `adr`/`init` · 1.8 Latency benchmark
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
1. ~~Python floor~~: ADR-0012 accepted (3.11 floor, CI through latest + next pre-release).
2. ~~PyPI name~~: `chatur` is unclaimed (checked 2026-10-02); reserve on first release.
3. ~~License~~: Apache-2.0 (ADR-0013).
4. ~~GitHub owner~~: `nitsharm1910/chatur`.
5. Should the audit log be committed by default in `standard` profile?
