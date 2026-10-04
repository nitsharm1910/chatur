"""`chatur` command-line entrypoint.

Stdlib-only (ADR-0012). Subcommands are added step by step through Phase 1 (see docs/roadmap.md).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from chatur import __version__, audit
from chatur.policy import Policy, PolicyError, load_policy, load_project_policy


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return args.func(args)
