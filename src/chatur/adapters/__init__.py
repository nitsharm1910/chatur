"""Assistant adapters (ADR-0004). Assistant-specific code lives only in this package.

Each adapter module provides: NAME, parse(payload, env) -> ChaturEvent | None,
render(event, verdict, payload, context=None) -> HookOutput,
failure(event_name, reason) -> HookOutput, project_root(payload, env) -> Path,
on_session_start(env) -> None, plus install/uninstall/hook_settings/apm_hook_file.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType

ALIASES = {"claude": "claude_code", "claude-code": "claude_code"}


@dataclass(frozen=True, slots=True)
class HookOutput:
    stdout: str = ""
    exit_code: int = 0
    stderr: str = ""


def get_adapter(name: str) -> ModuleType:
    canonical = ALIASES.get(name.lower(), name.lower())
    if canonical == "claude_code":
        from chatur.adapters import claude_code

        return claude_code
    raise ValueError(f"unknown assistant adapter {name!r} (available: claude_code)")
