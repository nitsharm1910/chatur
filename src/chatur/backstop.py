"""Git and CI backstop: checks that hold for any committer and any assistant (ADR-0005, ADR-0030).

Stdlib-only. Uses the `git` CLI for repository facts. In-session rules aren't re-run blindly: each
check here declares which rules it backs, because a rule's meaning can differ at commit time
(e.g. a human committing state.json after approving a gate is correct).
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from chatur import audit, gates
from chatur.events import ChaturEvent, EventKind, ToolCall, ToolCategory
from chatur.guard import GuardContext, evaluate, glob_matches
from chatur.policy import Policy, PolicyError, load_project_policy
from chatur.project import TOOLING_IGNORES
from chatur.redact import find_secrets
from chatur.verdict import Decision

BLOCK, WARN = "block", "warn"
AGENT_MARKERS = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CHATUR_AGENT_SESSION", "COPILOT_AGENT_ID")
ZERO_SHA = re.compile(r"^0+$")

# Which rules each check backs (ADR-0030). A test requires every critical git/ci rule to appear.
BACKSTOP_COVERAGE: Mapping[str, tuple[str, ...]] = {
    "agent-session": ("git.no-commit-push",),
    "secrets": ("secrets.known-token", "secrets.credential-shape"),
    "governance": ("gate.state-protected", "harness.read-only"),
    "history-rewrite": ("git.no-history-rewrite",),
    "process": (
        "test.missing-tests",
        "deps.needs-adr",
        "gate.design-before-code",
        "fs.protected-paths",
    ),
}
PROCESS_RULES = frozenset(BACKSTOP_COVERAGE["process"])
CODE_EXTENSIONS = frozenset(
    ".py .js .jsx .ts .tsx .mjs .cjs .go .rs .java .kt .kts .cs .rb .php .c .cc .cpp .h .hpp "
    ".swift .scala .m .mm .dart .lua .sh .ps1".split()
)
DEFAULT_TEST_GLOBS = (
    "tests/**",
    "test/**",
    "**/__tests__/**",
    "**/*_test.*",
    "**/*.test.*",
    "**/*.spec.*",
    "**/test_*.py",
)
AI_TRAILER = re.compile(
    r"(?im)^co-authored-by:.*\b(claude|copilot|codex|gemini|cursor|gpt|openai|anthropic|devin)\b"
)
APPROVED_BY = re.compile(r"(?im)^approved-by:\s*\S")


class GitError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Finding:
    check: str
    severity: str  # BLOCK | WARN
    message: str
    rules: tuple[str, ...] = ()
    file: str | None = None
    line: int | None = None


@dataclass
class Report:
    name: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(f.severity == BLOCK for f in self.findings)

    def extend(self, findings: Iterable[Finding]) -> None:
        self.findings.extend(findings)


# --------------------------------------------------------------------------- git facts


def git(root: Path, *args: str, input_text: str | None = None) -> str:
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", *args],  # noqa: S607 - git from PATH by design
            cwd=root,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitError(f"git {' '.join(args)}: {exc}") from exc
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


@dataclass(frozen=True, slots=True)
class Change:
    status: str  # A, M, D, T, ...
    path: str


def _parse_name_status(out: str) -> list[Change]:
    tokens = [t for t in out.split("\0") if t]
    return [Change(tokens[i][0], tokens[i + 1]) for i in range(0, len(tokens) - 1, 2)]


def staged_changes(root: Path) -> list[Change]:
    return _parse_name_status(git(root, "diff", "--cached", "--name-status", "-z", "--no-renames"))


def range_changes(root: Path, base: str, head: str) -> list[Change]:
    return _parse_name_status(
        git(root, "diff", "--name-status", "-z", "--no-renames", f"{base}...{head}")
    )


def added_lines(diff: str) -> Iterator[tuple[str, int, str]]:
    """(path, new line number, text) for every added line in a unified diff (-U0 works best)."""
    path: str | None = None
    line = 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            path = None if target == "/dev/null" else re.sub(r"^b/", "", target)
        elif raw.startswith("@@"):
            match = re.search(r"\+(\d+)", raw)
            line = int(match.group(1)) if match else 0
        elif raw.startswith("+") and path is not None:
            yield path, line, raw[1:]
            line += 1
        elif raw.startswith(" ") and path is not None:
            line += 1


def staged_diff(root: Path) -> str:
    return git(root, "diff", "--cached", "-U0", "--no-color", "--no-ext-diff")


def range_diff(root: Path, base: str, head: str) -> str:
    return git(root, "diff", "-U0", "--no-color", "--no-ext-diff", f"{base}...{head}")


# --------------------------------------------------------------------------- checks


def check_agent_session(env: Mapping[str, str]) -> list[Finding]:
    markers = [m for m in AGENT_MARKERS if env.get(m)]
    if not markers:
        return []
    return [
        Finding(
            "agent-session",
            BLOCK,
            f"commit/push from an AI agent session ({', '.join(markers)}); a human must commit "
            "from their own terminal (ADR-0014)",
            BACKSTOP_COVERAGE["agent-session"],
        )
    ]


def check_secrets(lines: Iterable[tuple[str, int, str]]) -> list[Finding]:
    findings: dict[tuple[str, int, str], Finding] = {}
    for path, number, text in lines:
        found = find_secrets(text)
        if any(s.category == "token" for s in found):  # a known token supersedes the generic shape
            found = [s for s in found if s.category == "token"]
        for secret in found:
            key = (path, number, secret.category)
            if key in findings:
                continue
            token = secret.category == "token"
            findings[key] = Finding(
                "secrets",
                BLOCK if token else WARN,
                f"{'secret' if token else 'possible hard-coded credential'} ({secret.kind}) added; "
                "remove it and use an environment variable or secret manager"
                + ("" if token else " (confirm it's not real)"),
                ("secrets.known-token",) if token else ("secrets.credential-shape",),
                path,
                number,
            )
    return list(findings.values())


def _approval_records(root: Path) -> list[Mapping[str, object]]:
    records = []
    for _, _, record in audit.iter_records(root):
        event = record.get("event") or {}
        raw = event.get("raw") or {}
        if event.get("kind") == "gate" and raw.get("action") == "approve":
            records.append(raw)
    return records


def check_governance(root: Path, policy_error: PolicyError | None) -> list[Finding]:
    rules = BACKSTOP_COVERAGE["governance"]
    findings: list[Finding] = []
    if policy_error is not None:
        findings.append(Finding("governance", BLOCK, f"policy is invalid: {policy_error}", rules))
    report = audit.verify(root)
    for problem in report.problems[:10]:
        findings.append(Finding("governance", BLOCK, f"audit log: {problem}", rules))
    try:
        state = gates.load_state(root)
    except gates.GateError as exc:
        return [*findings, Finding("governance", BLOCK, f"gate state: {exc}", rules)]
    approvals = state["gates"]
    if approvals and report.ok:
        if report.records == 0:
            findings.append(
                Finding(
                    "governance",
                    WARN,
                    "gate approvals can't be cross-checked: no audit log in this checkout "
                    "(audit.commit = false?)",
                    rules,
                )
            )
        else:
            recorded = _approval_records(root)
            for phase, record in approvals.items():
                digest = (record.get("artifacts") or {}).get("digest")
                if not any(
                    r.get("phase") == phase
                    and r.get("approved_at") == record.get("approved_at")
                    and (r.get("artifacts") or {}).get("digest") == digest
                    for r in recorded
                ):
                    findings.append(
                        Finding(
                            "governance",
                            BLOCK,
                            f"approval of {phase!r} in .chatur/state.json has no matching audit "
                            "record; approvals must come from `chatur gate approve`",
                            rules,
                        )
                    )
    for problem in gates.verify_gates(root):
        if ": stale" not in problem:
            findings.append(Finding("governance", BLOCK, f"gates: {problem}", rules))
    return findings


def check_stale(root: Path, severity: str) -> list[Finding]:
    try:
        problems = gates.verify_gates(root)
    except gates.GateError:
        return []  # reported by governance
    return [
        Finding("stale-gates", severity, f"gate {p} — re-approve with `chatur gate approve`")
        for p in problems
        if ": stale" in p
    ]


def _test_globs(policy: Policy) -> tuple[str, ...]:
    qa = policy.agents.get("chatur-qa")
    if qa is None:
        return DEFAULT_TEST_GLOBS
    return tuple(g for g in qa.write if not g.startswith("docs/"))


def _is_code(path: str) -> bool:
    return Path(path).suffix.lower() in CODE_EXTENSIONS


def check_process(root: Path, policy: Policy, changes: Iterable[Change]) -> list[Finding]:
    changed = [c.path for c in changes if c.status != "D"]
    if not changed:
        return []
    test_globs = _test_globs(policy)
    is_test = [any(glob_matches(p, g) for g in test_globs) for p in changed]
    source = [p for p, t in zip(changed, is_test, strict=True) if t is False and _is_code(p)]
    ctx = GuardContext(
        approved_gates=gates.approved_gates(root),
        missing_tests=bool(source) and not any(is_test),
        adr_changed=any(
            p.startswith("docs/decisions/") and p.endswith(".md") and "0000-template" not in p
            for p in changed
        ),
        project_root=str(root),
    )
    base = {"assistant": "backstop", "session_id": "git", "cwd": str(root)}
    events = [ChaturEvent(kind=EventKind.STOP, **base)] + [
        ChaturEvent(
            kind=EventKind.PRE_TOOL,
            tool=ToolCall(ToolCategory.FILE_WRITE, "commit", {"path": p}, paths=(p,)),
            **base,
        )
        for p in changed
    ]
    findings: dict[tuple[str, str | None], Finding] = {}
    for event in events:
        path = event.tool.paths[0] if event.tool else None
        for hit in evaluate(event, policy, ctx).hits:
            if hit.rule_id not in PROCESS_RULES or hit.decision in (Decision.ALLOW, Decision.LOG):
                continue
            severity = BLOCK if hit.decision is Decision.DENY else WARN
            key = (hit.rule_id, path if hit.rule_id != "test.missing-tests" else None)
            findings.setdefault(
                key,
                Finding("process", severity, f"[{hit.rule_id}] {hit.reason}", (hit.rule_id,), path),
            )
    return list(findings.values())


def check_harness_tooling(changes: Iterable[Change]) -> list[Finding]:
    globs = [g.rstrip("/") + ("/**" if g.endswith("/") else "") for g in TOOLING_IGNORES]
    return [
        Finding(
            "harness-tooling",
            WARN,
            "regenerable Chatur tooling is being committed; it should stay gitignored (ADR-0029)",
            ("harness.read-only",),
            c.path,
        )
        for c in changes
        if c.status != "D" and any(glob_matches(c.path, g) for g in globs)
    ]


def check_history_rewrite(root: Path, before: str | None, after: str) -> list[Finding]:
    if not before or ZERO_SHA.match(before):
        return []
    try:
        git(root, "cat-file", "-e", f"{before}^{{commit}}")
    except GitError:
        return [
            Finding(
                "history-rewrite",
                BLOCK,
                f"previous head {before[:12]} is gone: history was rewritten (force push)",
                BACKSTOP_COVERAGE["history-rewrite"],
            )
        ]
    try:
        git(root, "merge-base", "--is-ancestor", before, after)
    except GitError:
        return [
            Finding(
                "history-rewrite",
                BLOCK,
                f"{before[:12]} is not an ancestor of {after[:12]}: history was rewritten",
                BACKSTOP_COVERAGE["history-rewrite"],
            )
        ]
    return []


def check_ai_trailers(root: Path, base: str, head: str) -> list[Finding]:
    out = git(root, "log", "--format=%H%x1f%B%x1e", f"{base}..{head}")
    findings = []
    for entry in out.split("\x1e"):
        if "\x1f" not in entry:
            continue
        sha, body = entry.strip().split("\x1f", 1)
        if AI_TRAILER.search(body) and not APPROVED_BY.search(body):
            findings.append(
                Finding(
                    "ai-trailers",
                    WARN,
                    f"commit {sha[:12]} is AI co-authored without an `Approved-by:` trailer",
                )
            )
    return findings


# --------------------------------------------------------------------------- entrypoints


def _policy(root: Path) -> tuple[Policy | None, PolicyError | None]:
    try:
        return load_project_policy(root), None
    except PolicyError as exc:
        return None, exc


def pre_commit(root: Path, env: Mapping[str, str]) -> Report:
    report = Report("pre-commit")
    report.extend(check_agent_session(env))
    policy, error = _policy(root)
    changes = staged_changes(root)
    report.extend(check_secrets(added_lines(staged_diff(root))))
    report.extend(check_governance(root, error))
    if policy is not None:
        report.extend(check_process(root, policy, changes))
    report.extend(check_harness_tooling(changes))
    report.extend(check_stale(root, WARN))
    return report


def _pushed_diffs(root: Path, stdin_text: str) -> Iterator[str]:
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        _, local_sha, _, remote_sha = parts
        if ZERO_SHA.match(local_sha):
            continue  # branch deletion
        if ZERO_SHA.match(remote_sha):
            commits = git(root, "rev-list", local_sha, "--not", "--remotes").split()
            for commit in commits:
                yield git(root, "show", "-U0", "--no-color", "--format=", commit)
        else:
            yield git(root, "diff", "-U0", "--no-color", "--no-ext-diff", remote_sha, local_sha)


def pre_push(root: Path, env: Mapping[str, str], stdin_text: str) -> Report:
    report = Report("pre-push")
    report.extend(check_agent_session(env))
    _, error = _policy(root)
    diffs = list(_pushed_diffs(root, stdin_text))
    from_ref, to_ref = env.get("PRE_COMMIT_FROM_REF"), env.get("PRE_COMMIT_TO_REF")
    if not diffs and from_ref and to_ref:  # pre-commit framework passes refs via env, not stdin
        diffs.append(git(root, "diff", "-U0", "--no-color", "--no-ext-diff", from_ref, to_ref))
    for diff in diffs:
        report.extend(check_secrets(added_lines(diff)))
    report.extend(check_governance(root, error))
    report.extend(check_stale(root, WARN))
    return report


def ci_check(
    root: Path, *, base: str | None = None, head: str = "HEAD", before: str | None = None
) -> Report:
    report = Report("ci-check")
    policy, error = _policy(root)
    report.extend(check_governance(root, error))
    report.extend(check_stale(root, BLOCK))
    report.extend(check_history_rewrite(root, before, head))
    if base and not ZERO_SHA.match(base):
        changes = range_changes(root, base, head)
        report.extend(check_secrets(added_lines(range_diff(root, base, head))))
        if policy is not None:
            report.extend(check_process(root, policy, changes))
        report.extend(check_harness_tooling(changes))
        report.extend(check_ai_trailers(root, base, head))
    return report


# --------------------------------------------------------------------------- output


GROUP_AFTER = 3  # identical findings beyond this are summarised on one line


def _where(f: Finding) -> str:
    if f.file and f.line:
        return f"{f.file}:{f.line}"
    return f.file or ""


def render(report: Report, *, github: bool = False) -> str:
    lines = []
    ordered = sorted(report.findings, key=lambda f: (f.severity != BLOCK, f.check, f.message))
    groups: dict[tuple[str, str, str], list[Finding]] = {}
    for f in ordered:
        groups.setdefault((f.severity, f.check, f.message), []).append(f)
    for (severity, check, message), items in groups.items():
        if len(items) > GROUP_AFTER:
            sample = ", ".join(_where(f) for f in items[:GROUP_AFTER] if _where(f))
            summary = f"({len(items)} locations: {sample}, ...)"
            lines.append(f"  {severity.upper():<5} [{check}] {message} {summary}")
        else:
            for f in items:
                where = f" {_where(f)}" if _where(f) else ""
                lines.append(f"  {severity.upper():<5} [{check}]{where} {message}")
    for f in ordered:
        if github:
            kind = "error" if f.severity == BLOCK else "warning"
            loc = f" file={f.file}" + (f",line={f.line}" if f.line else "") if f.file else ""
            lines.append(f"::{kind}{loc}::{f.message}")
    blocks = sum(f.severity == BLOCK for f in report.findings)
    warns = len(report.findings) - blocks
    verdict = "BLOCKED" if report.blocked else "OK"
    plural = "s" if warns != 1 else ""
    head = f"chatur {report.name}: {verdict} ({blocks} blocking, {warns} warning{plural})"
    return "\n".join([head, *lines])


def step_summary(report: Report) -> str:
    rows = "\n".join(
        f"| {f.severity} | {f.check} | {f.file or ''}{':' + str(f.line) if f.line else ''} | "
        f"{f.message.replace('|', '/')} |"
        for f in report.findings
    )
    status = "❌ blocked" if report.blocked else "✅ passed"
    table = (
        f"\n| Severity | Check | Location | Finding |\n|---|---|---|---|\n{rows}\n" if rows else ""
    )
    return f"## Chatur {report.name}: {status}\n{table}"


def write_github_summary(report: Report, env: Mapping[str, str]) -> None:
    target = env.get("GITHUB_STEP_SUMMARY")
    if target:
        with Path(target).open("a", encoding="utf-8") as f:
            f.write(step_summary(report) + "\n")


def is_github(env: Mapping[str, str]) -> bool:
    return env.get("GITHUB_ACTIONS") == "true"
