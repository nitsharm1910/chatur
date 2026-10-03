"""`chatur` command-line entrypoint.

Stdlib-only (ADR-0012). Subcommands (hook, gate, adr, init, ...) are added in later Phase 1 steps.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from chatur import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatur",
        description="Portable, multi-assistant AI harness for the full SDLC.",
    )
    parser.add_argument("--version", action="version", version=f"chatur {__version__}")
    parser.add_subparsers(dest="command", metavar="<command>")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
    return 0
