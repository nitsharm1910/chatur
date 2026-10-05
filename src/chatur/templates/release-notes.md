---
title: Release <version>
status: Draft            # gate: release
version: <x.y.z>
date: YYYY-MM-DD
---

# Release <version>

## Highlights
Two or three sentences a user cares about.

## Added
## Changed
## Fixed
## Security
## Deprecated / removed
## Breaking changes and migration
Steps users must take, with examples.

## Traceability
| Item | PRD / ADR / ticket |
|---|---|

## Release checklist
- [ ] All earlier gates approved and fresh (`chatur gate status`, `chatur gate verify`)
- [ ] CHANGELOG.md updated (chatur-docs)
- [ ] Version bumped consistently
- [ ] CI green on the release commit
- [ ] Rollback plan documented
- [ ] A human tags and publishes the release (agents never push or tag)
