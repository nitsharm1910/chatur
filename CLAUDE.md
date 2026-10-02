@AGENTS.md

## Claude Code specifics
- Claude Code is the **reference adapter** (ADR-0009): new hook capabilities are designed against
  it first, then mapped to Copilot.
- When a task needs a decision not covered by an ADR, stop and ask the maintainer; draft the ADR
  as `Proposed` rather than silently choosing.
- End each session by appending to `docs/journal/<today>.md`.
