---
id: ADR-0031
title: Release 0.9.0 (Claude Code), versioning policy, and trusted publishing
status: Accepted
date: 2026-10-12
deciders: Nitin
phase: release
tags: [release, versioning, pypi, distribution]
refines: [ADR-0009, ADR-0011, ADR-0013]
---

# ADR-0031: Release 0.9.0, versioning, and trusted publishing

## Context
Phases 0–3 and 5 are complete for Claude Code. ADR-0009 commits v1 to Claude Code **and** Copilot, and
the Copilot adapter (Phase 4) isn't built yet. Under semver, a 1.0 also freezes the public interfaces:
`ChaturEvent`, the policy schema, the CLI, and the `.chatur/` layout.

## Decision (maintainer choices)
1. **Ship 0.9.0 now** as a real, installable public release with full Claude Code support. **1.0.0 follows
   Phase 4 (Copilot)**, so ADR-0009 stands unchanged.
2. **Versioning in 0.x:** a minor bump (0.10, 0.11, …) may change public interfaces, with every change
   recorded in an ADR and in CHANGELOG.md under "Changed/Breaking". 1.0.0 freezes them (AGENTS.md rule 8).
   `apm.yml` and `chatur.__version__` always match (enforced by tests).
3. **Publishing:** `.github/workflows/release.yml` runs on a `v*` tag:
   build (sdist + wheel; tag must equal the package version) → **TestPyPI** → **PyPI**, both through PyPI
   **trusted publishing** (OIDC, `id-token: write`; no API tokens stored), with the PyPI job behind a GitHub
   environment `pypi` that requires the maintainer's approval → a GitHub Release whose body comes from
   `docs/releases/<version>.md`. The tag is what APM installs (`apm install nitsharm1910/chatur#v0.9.0`)
   and what the reusable Action pins.
4. **Self-governance:** Chatur's own repo uses the **relaxed** profile (`.chatur/config.toml`, created by the
   maintainer; agents can't write it). Baseline protections still apply in full; ADRs and the journal are the
   process record.
5. **Release documentation:** user-facing README (absolute links, so it renders on PyPI), CHANGELOG.md
   (Keep a Changelog), `docs/releases/0.9.0.md`, SECURITY.md, CONTRIBUTING.md, `docs/guide/`.
   A test requires every CLI command to appear in the command reference.

## Consequences
- Positive: users can adopt Chatur now; interfaces can still improve before 1.0 based on real use.
- Negative: 0.x adopters may face breaking changes (mitigated by ADRs and the changelog).

## Guardrails / best practices this implies
- The release workflow fails if the tag ≠ package version; publishing needs a human approval in the `pypi`
  environment; agents never tag or push (ADR-0014).
- Release checklist (`docs/releases/checklist.md`) covers the human steps and open verifications
  (ADR-0026 modes, ADR-0028 acceptance, the sample walkthrough).
