# Chatur Roadmap

Legend: ✅ done · 🔄 in progress · ⏳ planned

## Phase 0 — Foundation ✅
- ✅ Repo skeleton, git init, pushed to `nitsharm1910/chatur`
- ✅ AGENTS.md / CLAUDE.md for developing Chatur
- ✅ Architecture draft ([architecture.md](architecture.md))
- ✅ ADR-0001…0014 accepted
- ✅ `.gitignore`, LICENSE (Apache-2.0), draft `policies/baseline.toml`

## Phase 1 — Python core (no assistant yet) ✅
- ✅ 1.1 `pyproject.toml`, `apm.yml`, package layout, CLI stub, pytest + ruff, CI matrix (3.11→3.14 + 3.15 pre-release, 3 OSes)
- ✅ 1.2 ChaturEvent + Verdict models, secret masking (`redact`) — ADR-0015
- ✅ 1.3 Policy loader (tighten-only), 3 profiles, `chatur policy validate|show` — ADR-0016
- ✅ 1.4 Guard engine + shell analyser + bypass suite (~80 bypasses) — ADR-0017
- ✅ 1.4b Remote-write CLIs denied (gh/glab/hub) — ADR-0018
- ✅ 1.5 Audit log: redacted, hash-chained JSONL, cross-process lock, `chatur audit verify|tail` — ADR-0019
- ✅ 1.5b `chatur check` dry-run CLI — ADR-0020
- ✅ 1.6 Gates: `chatur gate status|approve|revoke|verify`, human-only, audit anchors — ADR-0021
- ✅ 1.7 `chatur init` + `chatur adr new|list` — ADR-0022
- ✅ 1.8 ADR-0012 guardrail tests: stdlib-only (static + bare `python -I -S` run), fresh-process hook path p95 ~194 ms (< 500 ms)
- ✅ 1.9 Secret-detection baseline rules (gap found in 1.8): tokens deny, credential shapes ask, prompts warn; files, shell, tool args, prompts — ADR-0023
- ✅ 1.10 `chatur adr supersede` + `adr new --supersedes` — ADR-0024

## Phase 2 — Claude Code adapter (reference) 🔄
- ✅ 2.1 ADR-0025 (adapter, entrypoint, install, native deny layer)
- ✅ 2.2 `adapters/claude_code.py`: parse/render, tool classification (new `internal` category)
- ✅ 2.3 `chatur hook claude_code`: fail closed on PreToolUse, audit every event, SessionStart context + `CHATUR_AGENT_SESSION`; **fixed**: file contents no longer logged (ADR-0006)
- ✅ 2.4 `chatur hooks install|uninstall|print claude [--local]`, `.apm/hooks/chatur-claude.json` (drift-tested)
- ✅ 2.5 Dogfooding on this repo (`--local`); auto mode honours "ask" — ADR-0026
- ⏳ 2.6 Verify acceptEdits / bypassPermissions behaviour; replace doc-shaped fixtures with captured payloads
- ⏳ 2.7 Verify `apm install` output for the Claude target (needs APM installed)

## Phase 3 — Primitives 🔄
- ✅ 3.1 ADR-0027 (Chatur-enforced least privilege, per-phase commands, one-source templates)
- ✅ 3.2 Agent write scopes in policy (`[agents.*]`, `agent.read-only` baseline deny, `agent.write-scope` deny strict / ask otherwise); **bug found while dogfooding** (selectors missing from the guard matched every write) fixed + regression test
- ✅ 3.3 9 agents `.apm/agents/chatur-*.agent.md`
- ✅ 3.4 `.apm/instructions/chatur-sdlc.instructions.md`
- ✅ 3.5 9 commands `.apm/prompts/chatur-*.prompt.md`
- ✅ 3.6 7 skills with `assets/` templates; 7 new templates; `chatur init` installs `docs/templates/`
- ✅ 3.7 Primitive lint tests (`tests/test_primitives.py`), `scripts/sync_primitives.py`
- ✅ 3.8a `chatur primitives install|uninstall claude` + primitives in the wheel — ADR-0028 (Proposed)
- ✅ 3.8b Sample project `C:\Users\nitin\chatur-sample` (init + hooks + primitives)
- ✅ 3.9 Harness boundary (maintainer request): `harness.read-only` baseline deny; tooling gitignored, governance committed; templates → `.chatur/templates/` — ADR-0029
- ⏳ 3.8c Maintainer walkthrough in Claude Code: `/chatur-status` → `/chatur-requirements` → approve → `/chatur-design`

## Phase 4 — Copilot adapter
- `.github/hooks/*.json` (version 1), bash + powershell, cloud-agent constraints
- Copilot agents/prompts/instructions verification

## Phase 5 — Backstop ✅
- ✅ 5.1 ADR-0030 (explicit checks mapped to the rules they back; critical-rule coverage test)
- ✅ 5.2 `backstop.py`: agent-session, secrets, governance (audit/policy/approval↔audit consistency), stale gates, profile process rules, history rewrite, AI trailers, committed tooling
- ✅ 5.3 `chatur git-hook pre-commit|pre-push`, `chatur git-hooks install|uninstall`, `.pre-commit-hooks.yaml`
- ✅ 5.4 `chatur ci-check`, root `action.yml` (inputs via env), `chatur ci install github`; Chatur's own CI runs it
- ✅ 5.5 Real-git tests incl. end-to-end blocked commit; dogfood findings fixed (fake PEM literals in tests; credential false positives in code/prose; grouped output)

## Phase 6 — Release 0.9.0 🔄 (ADR-0031: 0.9 now for Claude Code; 1.0.0 after Phase 4)
- ✅ 6.1 ADR-0031 · 6.2 version 0.9.0, beta classifier
- ✅ 6.3 `release.yml`: tag → build (version check, wheel contents) → TestPyPI → PyPI (OIDC, approval) → GitHub Release
- ✅ 6.4 README quickstart, CHANGELOG, release notes, SECURITY, CONTRIBUTING, `docs/guide/` (CLI coverage test)
- ✅ 6.5 Clean-venv wheel smoke test of the full quickstart (found and fixed a CRLF/LF gate-digest bug)
- ⏳ 6.6 Maintainer: [release checklist](releases/checklist.md) (ADR-0028, self config, PyPI/GitHub setup, tag)

## 1.0.0
- Phase 4 Copilot adapter; ADR-0026 mode verification; interface freeze

## Later
- Codex, Gemini, Cursor adapters · SDK runner for CI/headless · external exporters (GitHub Issues/Jira)

## Open questions
1. ~~Python floor~~: ADR-0012 accepted (3.11 floor, CI through latest + next pre-release).
2. ~~PyPI name~~: `chatur` is unclaimed (checked 2026-10-02); reserve on first release.
3. ~~License~~: Apache-2.0 (ADR-0013).
4. ~~GitHub owner~~: `nitsharm1910/chatur`.
5. ~~Audit log in git~~: committed by default for strict + standard, ignored for relaxed (ADR-0022).
6. ~~Secret detection~~: scan files, shell, tool args, prompts; tiered (ADR-0023).
