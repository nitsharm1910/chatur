---
name: chatur-release-notes
description: Use when preparing a release — release notes, version bump plan, changelog coordination, and the release checklist — after the review gate.
---

# Release notes

Template: `assets/release-notes.md` (also `docs/templates/release-notes.md`).
Save as `docs/releases/<version>.md`.

## Steps
1. Confirm every earlier gate is approved and fresh (`chatur gate status`, `chatur gate verify`).
2. Collect the changes since the last release (`git log <last-tag>..HEAD`, read-only) and group them:
   Added / Changed / Fixed / Security / Deprecated / Removed.
3. Pick the version (semver): breaking changes mean major, features minor, fixes patch. List every file
   that holds the version and must change together.
4. Breaking changes get a migration section with before/after examples.
5. Traceability table: each item points to its PRD, ADR, or ticket.
6. Fill in the release checklist; ask chatur-docs to update `CHANGELOG.md`.

The human approves the gate (`chatur gate approve release`), commits, tags, and publishes.
Agents never tag, push, or publish.
