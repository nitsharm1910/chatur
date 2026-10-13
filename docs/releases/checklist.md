# Release checklist (maintainer)

Steps for cutting a Chatur release (ADR-0031). Agents prepare; **a human performs every outward-facing
step** (decisions, account settings, tagging, publishing).

## A. Decisions and verification
- [ ] Decide every open ADR (`chatur adr list --status proposed`); for 0.9.0 that's **ADR-0028**.
- [ ] Sample walkthrough in Claude Code (`C:\Users\nitin\chatur-sample`): `/chatur-requirements` → approve →
      `/chatur-design` → approve. Record findings in the journal.
- [ ] *(Before 1.0)* Observe hook `ask` in `acceptEdits` and `bypassPermissions` modes (ADR-0026).

## B. Repository
- [ ] Create Chatur's own `.chatur/config.toml` (agents can't write it), relaxed profile per ADR-0031:
  ```toml
  schema = "chatur.config/v1"
  [policy]
  profile = "relaxed"
  [assistants]
  enabled = ["claude"]
  [audit]
  commit = false
  ```
- [ ] Commit and push; confirm CI is green: test matrix (3 OS × Python 3.11–3.14) and the `backstop` job.
- [ ] Version agrees everywhere: `chatur --version`, `apm.yml`, `CHANGELOG.md` `## [x.y.z]`, `docs/releases/x.y.z.md`
      (tests enforce this).

## C. One-time publishing setup
- [ ] **PyPI trusted publisher:** pypi.org → *Your account → Publishing → Add a new pending publisher*:
      project `chatur`, owner `nitsharm1910`, repository `chatur`, workflow `release.yml`, environment `pypi`.
- [ ] **TestPyPI:** the same on test.pypi.org with environment `testpypi`.
- [ ] **GitHub environments:** *Settings → Environments*: create `testpypi` and `pypi`; on `pypi` add yourself
      as a **required reviewer** (the publish waits for your approval).
- [ ] **Private vulnerability reporting:** *Settings → Code security* → enable (referenced by SECURITY.md).

## D. Tag and publish
- [ ] `git tag -a v0.9.0 -m "Chatur 0.9.0"` then `git push origin v0.9.0`.
- [ ] Watch the `release` workflow: build → TestPyPI → **approve** the `pypi` environment → PyPI → GitHub Release.

## E. After the release
- [ ] In a fresh shell: `pipx install chatur==0.9.0`, then run the README quickstart in a scratch repo.
- [ ] `chatur ci install github` in a test repo; its workflow pins `nitsharm1910/chatur@v0.9.0`, so confirm the action runs.
- [ ] *(If APM is available)* `apm install nitsharm1910/chatur#v0.9.0` and compare with `chatur primitives install`.
- [ ] Open `## [Unreleased]` work in CHANGELOG.md; next milestone: Phase 4 (Copilot) → 1.0.0.
