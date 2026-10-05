---
description: Show where this project is in the Chatur SDLC and what the next step is
---

Use the **chatur-orchestrator** agent to report the project's SDLC status.

1. Run `chatur gate status` and `chatur adr list`.
2. Look at which phase artifacts exist under `docs/`.
3. Report concisely:
   - current phase and each gate's state (approved / stale / pending);
   - Proposed ADRs awaiting a human decision;
   - what blocks the next gate;
   - the next step: which `/chatur-<phase>` command to run, or which human action is needed
     (for example `chatur gate approve <phase>` run by a human in their own terminal).

Don't change any files.
