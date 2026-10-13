# Troubleshooting

## "Chatur hook error … (failing closed)" and every tool call is blocked
Something inside the hook failed: an invalid policy, an audit log that fails verification, or a broken
install. Pre-tool events fail **closed** by design.
1. In your own terminal: `chatur policy validate` and `chatur audit verify`.
2. Fix what they report (e.g. revert a bad edit to `.chatur/policy.local.toml`).
3. Emergency escape hatch: `chatur hooks uninstall claude` (or `--local`), fix, then reinstall.

## Nothing is enforced in Claude Code
- Is `chatur` on PATH for the shell Claude uses? Hooks call `chatur` (or, with `--local`, an absolute
  interpreter path). A missing command makes hooks **fail open**; Claude's native `permissions.deny` rules
  still block the critical commands.
- Run `chatur hooks install claude` again and restart the session.
- `chatur audit tail` should show a record for each tool call. If it doesn't, the hooks aren't running.

## An ordinary shell command is denied
Chatur denies any shell command whose text mentions a protected path (e.g. `.chatur/…`, `.claude/settings.json`),
even read-only ones like `cat`, because it can't tell reading from writing in arbitrary commands (ADR-0017).
Read those files with the assistant's Read tool, or use `chatur` commands (`chatur gate status`,
`chatur audit tail`). Check any command with `chatur check "<command>"`.

## `chatur gate approve` refuses
| Message | Cause |
|---|---|
| `agent/CI session detected (...)` | Run it in your own terminal, not through the assistant or CI. |
| `an interactive terminal is required` | Run it directly in a terminal (not piped or scripted). |
| `earlier gate 'X' is pending/stale` | Approve phases in order; re-approve stale ones. |
| `no artifacts for 'X'` | The phase folder has no real document yet (an unedited placeholder README doesn't count). |
| `audit log failed verification` | Run `chatur audit verify`; investigate before approving anything. |

## A gate became stale
You changed a document after it was approved. That's expected: review the change and run
`chatur gate approve <phase>` again. CI (`chatur ci-check`) fails until you do.

## The git hook blocked my commit
The output names the check, file, and line. Secrets: remove the value and use an environment variable.
Governance: run `chatur audit verify` / `chatur gate verify`. Process rules: add the tests or the ADR, or
change profile deliberately. `git commit --no-verify` skips local hooks, but CI will still check.

## `chatur git-hooks install` refuses
Another tool owns the hooks (`core.hooksPath` is set, e.g. husky), or a non-Chatur hook exists. Use the
pre-commit framework entries `chatur-pre-commit` / `chatur-pre-push`, or `--force` if you're sure.

## A false positive from secret detection
Known token formats are blocked; placeholders (`${VAR}`, `<token>`, `changeme`, `…EXAMPLE`) are ignored.
If a real-looking value is test data, build it at runtime (`"ghp_" + "…"`) instead of writing a literal.
Report systematic false positives as an issue with the (redacted) line.
