"""Guard engine: evaluate a ChaturEvent against a Policy (ADR-0014, ADR-0016, ADR-0017).

Pure and stdlib-only (ADR-0012): no I/O. Facts the engine can't derive from the event (approved
gates, git-diff facts) come in through GuardContext. Strictest matching rule wins.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from chatur.events import ChaturEvent, ToolCategory
from chatur.policy import Policy, Rule
from chatur.shell import ShellAnalysis, analyze, command_base, normalize_path
from chatur.verdict import Decision, RuleHit, Verdict

SELECTORS = (
    "any",
    "file_write",
    "shebang",
    "path_globs",
    "shell_patterns",
    "git_subcommands",
    "git_patterns",
    "argv_patterns",
    "tool_name_patterns",
)
_WILDCARDS = re.compile(r"[*?\[]")


@dataclass(frozen=True, slots=True)
class GuardContext:
    approved_gates: frozenset[str] = frozenset()  # phases approved in .chatur/state.json
    adr_changed: bool = False  # an ADR was added/changed in the current change set
    missing_tests: bool = False  # source changed without test changes
    project_root: str | None = None  # defaults to event.cwd


def effective(decision: Decision, attended: bool) -> Decision:
    """ADR-0014: with nobody to answer, ask becomes deny."""
    return Decision.DENY if not attended and decision is Decision.ASK else decision


# --------------------------------------------------------------------------- globs


@lru_cache(maxsize=512)
def _glob_regex(pattern: str) -> re.Pattern[str]:
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out), re.IGNORECASE)


def _literal_prefix(pattern: str) -> str:
    match = _WILDCARDS.search(pattern)
    return pattern[: match.start()] if match else pattern


def _ancestors(path: str) -> list[str]:
    parts = [p for p in path.rstrip("/").split("/") if p]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def path_matches(path: str, pattern: str) -> bool:
    """Normalised path vs glob: case-insensitive, ancestor and wildcard-token rules (ADR-0017)."""
    if not path:
        return False
    regex = _glob_regex(pattern)
    if regex.fullmatch(path):
        return True
    if "/" not in pattern and regex.fullmatch(path.rsplit("/", 1)[-1]):
        return True
    if path in (".", "/"):
        return False
    literal = _literal_prefix(pattern).lower()
    # ancestor: deleting/moving a parent directory touches the protected path
    if literal.startswith(path.lower().rstrip("/") + "/"):
        return True
    # wildcard token that could expand to a protected path: `rm .chat*/state.json`, `rm -rf .*`
    if _WILDCARDS.search(path):
        token = _glob_regex(path)
        return any(token.fullmatch(candidate) for candidate in _ancestors(literal))
    return False


# --------------------------------------------------------------------------- matching


@lru_cache(maxsize=1024)
def _regex(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class _Facts:
    event: ChaturEvent
    shell: ShellAnalysis | None
    paths: tuple[str, ...]
    allowlisted: bool


def _selector(key: str, value: object, facts: _Facts) -> bool:
    tool = facts.event.tool
    shell = facts.shell
    if key == "any":
        if facts.allowlisted:
            return False
        return value is True
    if key == "file_write":
        return value is True and tool is not None and tool.category is ToolCategory.FILE_WRITE
    if key == "shebang":
        return (
            value is True
            and tool is not None
            and any(isinstance(v, str) and v.lstrip().startswith("#!") for v in tool.args.values())
        )
    if key == "path_globs":
        return any(path_matches(p, g) for p in facts.paths for g in value)  # type: ignore[union-attr]
    if key == "shell_patterns":
        return shell is not None and any(
            _regex(p).search(t)
            for p in value  # type: ignore[union-attr]
            for t in shell.texts
        )
    if key == "git_subcommands":
        wanted = {s.lower() for s in value}  # type: ignore[union-attr]
        return shell is not None and any(c.subcommand in wanted for c in shell.git_calls)
    if key == "git_patterns":
        return shell is not None and any(
            _regex(p).search(c.text())
            for p in value  # type: ignore[union-attr]
            for c in shell.git_calls
        )
    if key == "argv_patterns":
        # each real command as "<basename> <args...>", after wrappers/nesting (ADR-0018)
        return shell is not None and any(
            _regex(p).search(" ".join((command_base(argv[0]), *argv[1:])))
            for p in value  # type: ignore[union-attr]
            for argv in shell.argvs
        )
    if key == "tool_name_patterns":
        return tool is not None and any(_regex(p).search(tool.name) for p in value)  # type: ignore[union-attr]
    raise AssertionError(f"unknown selector {key!r}")  # policy loader rejects unknown keys


def rule_matches(rule: Rule, facts: _Facts, ctx: GuardContext) -> bool:
    event = facts.event
    if event.kind not in rule.events:
        return False
    if rule.tool_categories and (
        event.tool is None or event.tool.category not in rule.tool_categories
    ):
        return False
    match = rule.match
    selectors = [k for k in SELECTORS if k in match]
    if selectors and not any(_selector(k, match[k], facts) for k in selectors):
        return False
    gate = match.get("requires_gate")
    if gate is not None and gate in ctx.approved_gates:
        return False
    if match.get("requires_adr") and ctx.adr_changed:
        return False
    return not (match.get("missing_tests") and not ctx.missing_tests)


def _event_paths(
    event: ChaturEvent, shell: ShellAnalysis | None, root: str | None
) -> tuple[str, ...]:
    raw: list[str] = list(event.tool.paths) if event.tool else []
    if shell is not None:
        raw.extend(shell.paths)
    normalized = (normalize_path(p, root) for p in raw)
    return tuple(dict.fromkeys(p for p in normalized if p))


def _allowlisted(shell: ShellAnalysis | None, patterns: Iterable[str]) -> bool:
    if shell is None or not shell.simple:
        return False
    command = shell.command.strip()
    return any(_regex(p).search(command) for p in patterns)


def evaluate(event: ChaturEvent, policy: Policy, ctx: GuardContext | None = None) -> Verdict:
    ctx = ctx or GuardContext()
    tool = event.tool
    shell: ShellAnalysis | None = None
    if tool is not None and tool.category is ToolCategory.SHELL:
        shell = analyze(tool.command or "")
    facts = _Facts(
        event=event,
        shell=shell,
        paths=_event_paths(event, shell, ctx.project_root or event.cwd),
        allowlisted=_allowlisted(shell, policy.readonly_allowlist),
    )

    hits = [
        RuleHit(
            rule.id,
            rule.verdict if event.attended else rule.unattended,
            rule.reason,
            rule.adr,
        )
        for rule in policy.rules
        if rule_matches(rule, facts, ctx)
    ]
    if tool is not None and tool.category is ToolCategory.OTHER:
        hits.append(
            RuleHit(
                "default.unknown_tool",
                effective(policy.defaults.unknown_tool, event.attended),
                f"Unclassified tool {tool.name!r}.",
                "ADR-0016",
            )
        )
    if shell is not None and not shell.parseable:
        hits.append(
            RuleHit(
                "default.unparseable_command",
                effective(policy.defaults.unparseable_command, event.attended),
                "Command could not be fully analysed: " + "; ".join(shell.problems),
                "ADR-0017",
            )
        )
    return Verdict.from_hits(hits, profile=policy.profile)


def error_verdict(policy: Policy | None, reason: str, *, attended: bool = True) -> Verdict:
    """Verdict for a hook that failed internally: fail closed (ADR-0012)."""
    decision = policy.defaults.adapter_error if policy else Decision.DENY
    hit = RuleHit("default.adapter_error", effective(decision, attended), reason, "ADR-0012")
    return Verdict.from_hits([hit], profile=policy.profile if policy else None)
