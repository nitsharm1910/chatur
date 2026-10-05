---
description: Release phase — release notes, changelog, version bump plan, release checklist
input:
  - version
---

Start the **release** phase for version ${input:version}

1. Run `chatur gate status` and `chatur gate verify`. Every earlier gate must be approved and fresh;
   if not, stop and tell me which.
2. Delegate to **chatur-devops** (`chatur-release-notes` skill): `docs/releases/${input:version}.md`
   with traceability to PRDs/ADRs, the version bump plan (every file that holds the version), and the
   release checklist.
3. Delegate to **chatur-docs** to update `CHANGELOG.md` and user-facing docs.
4. Summarise the release contents and the checklist status.

End with exactly this instruction for me:
> Review the release notes and changelog, then run in your own terminal: `chatur gate approve release`.
> After that, **you** commit, tag `v${input:version}`, and publish. Agents never tag or push.
