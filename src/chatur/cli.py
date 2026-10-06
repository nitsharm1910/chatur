"""`chatur` command-line entrypoint.

Stdlib-only (ADR-0012). Subcommands are added step by step through Phase 1 (see docs/roadmap.md).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from chatur import __version__, adr, audit, gates, primitives, project
from chatur.adapters import get_adapter
from chatur.events import ChaturEvent, EventKind, ToolCall, ToolCategory
from chatur.guard import GuardContext, evaluate
from chatur.hook import run_hook
from chatur.policy import Policy, PolicyError, load_policy, load_project_policy
from chatur.verdict import Decision


def _resolve_policy(args: argparse.Namespace) -> Policy:
    root = Path(args.root).resolve()
    if args.profile:
        local = root / ".chatur" / "policy.local.toml"
        return load_policy(args.profile, local_path=local if local.is_file() else None)
    return load_project_policy(root)


def _cmd_policy_validate(args: argparse.Namespace) -> int:
    try:
        policy = _resolve_policy(args)
    except PolicyError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(
        f"policy OK: profile={policy.profile} sources={','.join(policy.sources)} "
        f"rules={len(policy.rules)}"
    )
    return 0


def _cmd_policy_show(args: argparse.Namespace) -> int:
    try:
        policy = _resolve_policy(args)
    except PolicyError as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.json:
        data = {
            "profile": policy.profile,
            "sources": list(policy.sources),
            "defaults": {
                k: getattr(policy.defaults, k).value
                for k in ("unknown_tool", "unparseable_command", "adapter_error")
            },
            "rules": [
                {
                    "id": r.id,
                    "verdict": r.verdict.value,
                    "unattended": r.unattended.value,
                    "baseline": r.baseline,
                    "source": r.source,
                    "tightened_by": list(r.tightened_by),
                    "adr": r.adr,
                    "reason": r.reason,
                }
                for r in policy.rules
            ],
        }
        print(json.dumps(data, indent=2))
        return 0
    print(f"profile: {policy.profile}   sources: {' -> '.join(policy.sources)}")
    header = f"{'rule':<28} {'verdict':<8} {'unattended':<10} {'base':<5} source"
    print(header)
    print("-" * len(header))
    for r in policy.rules:
        source = r.source + (
            f" (tightened by {', '.join(r.tightened_by)})" if r.tightened_by else ""
        )
        base = "yes" if r.baseline else ""
        print(f"{r.id:<28} {r.verdict.value:<8} {r.unattended.value:<10} {base:<5} {source}")
    return 0


def _cmd_audit_verify(args: argparse.Namespace) -> int:
    report = audit.verify(Path(args.root).resolve())
    if report.ok:
        print(f"audit OK: {report.records} records in {report.files} file(s)")
        return 0
    print(f"audit FAILED: {len(report.problems)} problem(s)", file=sys.stderr)
    for problem in report.problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


def _cmd_audit_tail(args: argparse.Namespace) -> int:
    try:
        records = audit.tail(Path(args.root).resolve(), args.n)
    except audit.AuditError as exc:
        print(exc, file=sys.stderr)
        return 1
    for record in records:
        print(json.dumps(record) if args.json else audit.summarize(record))
    return 0


_CHECK_EXIT = {
    Decision.ALLOW: 0,
    Decision.LOG: 0,
    Decision.WARN: 0,
    Decision.ASK: 2,
    Decision.DENY: 3,
}


def _check_event(args: argparse.Namespace, root: Path) -> ChaturEvent:
    common = {
        "kind": EventKind.PRE_TOOL,
        "assistant": "chatur-check",
        "session_id": "check",
        "cwd": str(root),
        "attended": not args.unattended,
    }
    if args.shell_command:
        cmd = args.shell_command
        tool = ToolCall(ToolCategory.SHELL, "shell", {"command": cmd}, cmd)
    elif args.write:
        tool = ToolCall(ToolCategory.FILE_WRITE, "write", {"path": args.write}, paths=(args.write,))
    elif args.read:
        tool = ToolCall(ToolCategory.FILE_READ, "read", {"path": args.read}, paths=(args.read,))
    else:
        tool = ToolCall(ToolCategory(args.category), args.tool, {})
    return ChaturEvent(tool=tool, **common)


def _cmd_check(args: argparse.Namespace) -> int:
    chosen = [x for x in (args.shell_command, args.write, args.read, args.tool) if x]
    if len(chosen) != 1:
        print("chatur check: give exactly one of COMMAND, --write, --read, --tool", file=sys.stderr)
        return 1
    root = Path(args.root).resolve()
    try:
        policy = _resolve_policy(args)
    except PolicyError as exc:
        print(exc, file=sys.stderr)
        return 1
    ctx = GuardContext(
        approved_gates=gates.approved_gates(root) | frozenset(args.gate or ()),
        project_root=str(root),
    )
    verdict = evaluate(_check_event(args, root), policy, ctx)
    if args.json:
        print(json.dumps(verdict.to_dict(), indent=2))
    else:
        print(f"{verdict.decision.value}: {verdict.reason}")
        for hit in verdict.hits:
            print(f"  - {hit.rule_id:<28} {hit.decision.value:<5} {hit.adr or ''}")
    return _CHECK_EXIT[verdict.decision]


def _gate_root(args: argparse.Namespace) -> Path:
    return Path(args.root).resolve()


def _redact_patterns(root: Path) -> tuple[str, ...]:
    try:
        return load_project_policy(root).redact_patterns
    except PolicyError:
        return ()


def _cmd_gate_status(args: argparse.Namespace) -> int:
    root = _gate_root(args)
    try:
        statuses = gates.status(root)
    except gates.GateError as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.json:
        print(
            json.dumps(
                {
                    "current": gates.current_phase(statuses),
                    "gates": [
                        {
                            "phase": s.phase,
                            "state": s.state,
                            "files": s.file_count,
                            "approved_by": (s.record or {}).get("approved_by"),
                            "approved_at": (s.record or {}).get("approved_at"),
                        }
                        for s in statuses
                    ],
                },
                indent=2,
            )
        )
        return 0
    print(f"current phase: {gates.current_phase(statuses) or 'all gates approved'}")
    for s in statuses:
        who = f"{s.record['approved_by']} at {s.record['approved_at']}" if s.record else ""
        print(f"  {s.phase:<13} {s.state:<9} {s.file_count:>4} file(s)  {who}")
    return 0


def _confirm(action: str) -> gates.Confirm:
    def ask(phase: str) -> bool:
        try:
            return input(f"Type '{phase}' to {action} this gate: ").strip() == phase
        except EOFError:
            return False

    return ask


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _cmd_gate_approve(args: argparse.Namespace) -> int:
    root = _gate_root(args)
    try:
        record = gates.approve(
            root,
            args.phase,
            env=os.environ,
            interactive=_interactive(),
            confirm=_confirm("approve"),
            note=args.note,
            extra_patterns=_redact_patterns(root),
        )
    except (gates.GateError, audit.AuditError) as exc:
        print(f"gate approve: {exc}", file=sys.stderr)
        return 1
    files = record["artifacts"]["file_count"]
    print(f"approved {args.phase!r} ({files} artifact file(s)) by {record['approved_by']}")
    return 0


def _cmd_gate_revoke(args: argparse.Namespace) -> int:
    root = _gate_root(args)
    try:
        removed = gates.revoke(
            root,
            args.phase,
            env=os.environ,
            interactive=_interactive(),
            confirm=_confirm("revoke"),
            extra_patterns=_redact_patterns(root),
        )
    except (gates.GateError, audit.AuditError) as exc:
        print(f"gate revoke: {exc}", file=sys.stderr)
        return 1
    print(f"revoked: {', '.join(removed)}")
    return 0


def _cmd_gate_verify(args: argparse.Namespace) -> int:
    problems = gates.verify_gates(_gate_root(args))
    if not problems:
        print("gates OK")
        return 0
    print(f"gates FAILED: {len(problems)} problem(s)", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


def _cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    try:
        result = project.init_project(
            root, profile=args.profile, assistants=args.assistants.split(","), force=args.force
        )
    except (project.InitError, PolicyError) as exc:
        print(f"chatur init: {exc}", file=sys.stderr)
        return 1
    print(f"chatur init: {root} (profile={args.profile})")
    for label, paths in (
        ("created", result.created),
        ("updated", result.updated),
        ("skipped", result.skipped),
    ):
        for path in paths:
            print(f"  {label:<8} {path}")
    for note in result.notes:
        print(f"  note: {note}")
    return 0


def _cmd_adr_new(args: argparse.Namespace) -> int:
    try:
        path = adr.new_adr(
            Path(args.root).resolve(),
            args.title,
            phase=args.phase,
            tags=args.tags.split(",") if args.tags else (),
            supersedes=args.supersedes.split(",") if args.supersedes else (),
        )
    except adr.AdrError as exc:
        print(f"chatur adr new: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


def _cmd_adr_supersede(args: argparse.Namespace) -> int:
    try:
        old_path, new_path = adr.supersede(Path(args.root).resolve(), args.old, args.by)
    except adr.AdrError as exc:
        print(f"chatur adr supersede: {exc}", file=sys.stderr)
        return 1
    print(f"{old_path.name} superseded by {new_path.name}")
    return 0


def _cmd_adr_list(args: argparse.Namespace) -> int:
    adrs = adr.list_adrs(Path(args.root).resolve(), status=args.status)
    if args.json:
        rows = [
            {"id": a.id, "title": a.title, "status": a.status, "date": a.date, "path": str(a.path)}
            for a in adrs
        ]
        print(json.dumps(rows, indent=2))
        return 0
    for a in adrs:
        print(f"{a.id:<9} {a.status:<11} {a.title}")
    return 0


def _cmd_hook(args: argparse.Namespace) -> int:
    """Called by the assistant: stdin = native payload; stdout/exit code = native response."""
    stdin_text = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    output = run_hook(args.adapter, stdin_text, os.environ, args.event)
    if output.stdout:
        sys.stdout.buffer.write(output.stdout.encode("utf-8"))
        sys.stdout.flush()
    if output.stderr:
        sys.stderr.buffer.write((output.stderr + "\n").encode("utf-8"))
        sys.stderr.flush()
    return output.exit_code


def _cmd_hooks(args: argparse.Namespace) -> int:
    try:
        adapter = get_adapter(args.adapter)
    except ValueError as exc:
        print(f"chatur hooks: {exc}", file=sys.stderr)
        return 1
    root = Path(args.root).resolve()
    if args.hooks_command == "print":
        data = (
            adapter.apm_hook_file()
            if args.apm
            else {"hooks": adapter.hook_settings(_invocation(adapter, local=args.local))}
        )
        print(json.dumps(data, indent=2))
        return 0
    try:
        if args.hooks_command == "install":
            path = adapter.install(
                root, local=args.local, invocation=_invocation(adapter, local=args.local)
            )
            print(f"installed Chatur hooks + native deny rules into {path}")
            if args.local:
                _report_gitignore(root)
            else:
                print("  hooks call `chatur` from PATH; install it with `pipx install chatur`")
            return 0
        path = adapter.uninstall(root, local=args.local)
        print(f"removed Chatur hooks from {path}" if path else "nothing to remove")
        return 0
    except ValueError as exc:
        print(f"chatur hooks: {exc}", file=sys.stderr)
        return 1


def _cmd_primitives(args: argparse.Namespace) -> int:
    try:
        adapter = get_adapter(args.adapter)
        root = Path(args.root).resolve()
        if args.primitives_command == "install":
            files = adapter.primitive_files(primitives.primitives_root())
            report = primitives.apply(root, files, adapter.PRIMITIVES_MANIFEST, force=args.force)
        else:
            report = primitives.remove(root, adapter.PRIMITIVES_MANIFEST)
    except (ValueError, primitives.PrimitivesError) as exc:
        print(f"chatur primitives: {exc}", file=sys.stderr)
        return 1
    for label, paths in (
        ("written", report.written),
        ("updated", report.updated),
        ("removed", report.removed),
    ):
        for path in paths:
            print(f"  {label:<9} {path}")
    for path, reason in report.skipped:
        print(f"  skipped   {path} ({reason})")
    print(
        f"{args.primitives_command}: {len(report.written)} written, {len(report.updated)} updated, "
        f"{len(report.unchanged)} unchanged, {len(report.removed)} removed, "
        f"{len(report.skipped)} skipped"
    )
    if args.primitives_command == "install":
        _report_gitignore(root)
        print("  hooks are separate: chatur hooks install claude [--local]")
    return 0


def _report_gitignore(root: Path) -> None:
    result = project.ensure_gitignore(root)
    if result.created or result.updated:
        print("  .gitignore: managed block added/updated (harness tooling ignored, ADR-0029)")


def _invocation(adapter: object, *, local: bool) -> tuple[str, ...]:
    if local:  # this machine's interpreter: no PATH dependency (ADR-0025)
        return (sys.executable, "-m", "chatur", "hook", adapter.NAME)  # type: ignore[attr-defined]
    return adapter.SHARED_INVOCATION  # type: ignore[attr-defined]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatur",
        description="Portable, multi-assistant AI harness for the full SDLC.",
    )
    parser.add_argument("--version", action="version", version=f"chatur {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="<command>")

    policy = commands.add_parser("policy", help="inspect and validate guardrail policy")
    policy_cmds = policy.add_subparsers(dest="policy_command", metavar="<action>", required=True)
    for name, func, help_text in (
        ("validate", _cmd_policy_validate, "check policy files; exit 1 on any problem"),
        ("show", _cmd_policy_show, "print the effective (composed) policy"),
    ):
        sub = policy_cmds.add_parser(name, help=help_text)
        sub.add_argument("--root", default=".", help="project root (default: current directory)")
        sub.add_argument("--profile", help="override the profile from .chatur/config.toml")
        if name == "show":
            sub.add_argument("--json", action="store_true", help="machine-readable output")
        sub.set_defaults(func=func)

    audit_cmd = commands.add_parser("audit", help="inspect and verify the audit log")
    audit_cmds = audit_cmd.add_subparsers(dest="audit_command", metavar="<action>", required=True)
    verify = audit_cmds.add_parser("verify", help="check the hash chain; exit 1 on tampering")
    verify.add_argument("--root", default=".", help="project root (default: current directory)")
    verify.set_defaults(func=_cmd_audit_verify)
    tail = audit_cmds.add_parser("tail", help="show the most recent records")
    tail.add_argument("--root", default=".", help="project root (default: current directory)")
    tail.add_argument("-n", type=int, default=20, help="number of records (default 20)")
    tail.add_argument("--json", action="store_true", help="print full JSON records")
    tail.set_defaults(func=_cmd_audit_tail)

    check = commands.add_parser(
        "check",
        help="dry-run one action against the policy (exit 0 allow, 2 ask, 3 deny)",
        description="Evaluate one action without executing or logging it (ADR-0020).",
    )
    check.add_argument(
        "shell_command", nargs="?", metavar="COMMAND", help="shell command to evaluate (quote it)"
    )
    check.add_argument("--write", metavar="PATH", help="evaluate a file write")
    check.add_argument("--read", metavar="PATH", help="evaluate a file read")
    check.add_argument("--tool", metavar="NAME", help="evaluate a named tool call")
    check.add_argument(
        "--category",
        default="other",
        choices=[c.value for c in ToolCategory],
        help="category for --tool (default: other)",
    )
    check.add_argument("--root", default=".", help="project root (default: current directory)")
    check.add_argument("--profile", help="override the profile from .chatur/config.toml")
    check.add_argument("--unattended", action="store_true", help="no human present (ask -> deny)")
    check.add_argument(
        "--gate", action="append", choices=gates.PHASES, help="treat PHASE as approved (repeatable)"
    )
    check.add_argument("--json", action="store_true", help="machine-readable output")
    check.set_defaults(func=_cmd_check)

    gate = commands.add_parser("gate", help="SDLC phase gates (human approval)")
    gate_cmds = gate.add_subparsers(dest="gate_command", metavar="<action>", required=True)
    g_status = gate_cmds.add_parser("status", help="approved / stale / pending per phase")
    g_status.add_argument("--json", action="store_true", help="machine-readable output")
    g_status.set_defaults(func=_cmd_gate_status)
    g_approve = gate_cmds.add_parser("approve", help="approve a phase (human, interactive)")
    g_approve.add_argument("phase", choices=gates.PHASES)
    g_approve.add_argument("--note", help="optional note stored with the approval")
    g_approve.set_defaults(func=_cmd_gate_approve)
    g_revoke = gate_cmds.add_parser("revoke", help="revoke a phase and all later phases")
    g_revoke.add_argument("phase", choices=gates.PHASES)
    g_revoke.set_defaults(func=_cmd_gate_revoke)
    g_verify = gate_cmds.add_parser("verify", help="CI check: stale gates, missing audit anchors")
    g_verify.set_defaults(func=_cmd_gate_verify)
    for sub in (g_status, g_approve, g_revoke, g_verify):
        sub.add_argument("--root", default=".", help="project root (default: current directory)")

    init = commands.add_parser("init", help="prepare this project for Chatur (ADR-0022)")
    init.add_argument("--root", default=".", help="project root (default: current directory)")
    init.add_argument("--profile", default="standard", help="strict | standard | relaxed")
    init.add_argument(
        "--assistants",
        default=",".join(project.DEFAULT_ASSISTANTS),
        help=f"comma-separated: {', '.join(project.ASSISTANTS)} (default: claude,copilot)",
    )
    init.add_argument("--force", action="store_true", help="rewrite .chatur/config.toml only")
    init.set_defaults(func=_cmd_init)

    adr_cmd = commands.add_parser("adr", help="Architecture Decision Records")
    adr_cmds = adr_cmd.add_subparsers(dest="adr_command", metavar="<action>", required=True)
    a_new = adr_cmds.add_parser("new", help="create the next numbered ADR (status Proposed)")
    a_new.add_argument("title", help="decision title (quote it)")
    a_new.add_argument("--phase", default="design", choices=adr.PHASE_CHOICES)
    a_new.add_argument("--tags", help="comma-separated tags")
    a_new.add_argument("--supersedes", help="comma-separated ADRs this one replaces (e.g. 7,9)")
    a_new.set_defaults(func=_cmd_adr_new)
    a_sup = adr_cmds.add_parser(
        "supersede", help="mark OLD superseded by an Accepted ADR (ADR-0024)"
    )
    a_sup.add_argument("old", help="ADR being replaced (e.g. 7 or ADR-0007)")
    a_sup.add_argument("--by", required=True, help="the Accepted replacement ADR")
    a_sup.set_defaults(func=_cmd_adr_supersede)
    a_list = adr_cmds.add_parser("list", help="list ADRs with status")
    a_list.add_argument("--status", help="filter by status prefix (e.g. proposed)")
    a_list.add_argument("--json", action="store_true", help="machine-readable output")
    a_list.set_defaults(func=_cmd_adr_list)
    for sub in (a_new, a_list, a_sup):
        sub.add_argument("--root", default=".", help="project root (default: current directory)")

    hook = commands.add_parser(
        "hook", help="assistant hook entrypoint (reads the native payload on stdin)"
    )
    hook.add_argument("adapter", help="assistant adapter, e.g. claude_code")
    hook.add_argument("event", nargs="?", help="native event name, e.g. PreToolUse")
    hook.set_defaults(func=_cmd_hook)

    hooks = commands.add_parser("hooks", help="install/uninstall assistant hooks (ADR-0025)")
    hooks_cmds = hooks.add_subparsers(dest="hooks_command", metavar="<action>", required=True)
    for name, help_text in (
        ("install", "add Chatur hooks + native deny rules to the assistant's settings"),
        ("uninstall", "remove only Chatur's hooks and deny rules"),
        ("print", "print the hook configuration JSON"),
    ):
        sub = hooks_cmds.add_parser(name, help=help_text)
        sub.add_argument("adapter", help="assistant: claude")
        sub.add_argument("--root", default=".", help="project root (default: current directory)")
        sub.add_argument(
            "--local",
            action="store_true",
            help="use .claude/settings.local.json and this machine's interpreter path",
        )
        if name == "print":
            sub.add_argument("--apm", action="store_true", help="APM hook file format")
        sub.set_defaults(func=_cmd_hooks)

    prims = commands.add_parser(
        "primitives", help="install agents/commands/skills/rules without APM (ADR-0028)"
    )
    prims_cmds = prims.add_subparsers(dest="primitives_command", metavar="<action>", required=True)
    for name, help_text in (
        ("install", "copy Chatur agents, commands, skills, rules into the assistant's folder"),
        ("uninstall", "remove only unmodified files Chatur installed"),
    ):
        sub = prims_cmds.add_parser(name, help=help_text)
        sub.add_argument("adapter", help="assistant: claude")
        sub.add_argument("--root", default=".", help="project root (default: current directory)")
        if name == "install":
            sub.add_argument(
                "--force", action="store_true", help="overwrite modified/foreign files"
            )
        else:
            sub.set_defaults(force=False)
        sub.set_defaults(func=_cmd_primitives)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return args.func(args)
