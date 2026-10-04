"""Shared builders for guard tests."""

from __future__ import annotations

import pytest

from chatur.events import ChaturEvent, EventKind, ToolCall, ToolCategory
from chatur.guard import GuardContext, evaluate
from chatur.policy import load_policy
from chatur.verdict import Verdict

ROOT = "/repo"


def shell_event(command: str, *, attended: bool = True) -> ChaturEvent:
    return ChaturEvent(
        kind=EventKind.PRE_TOOL,
        assistant="test",
        session_id="s",
        cwd=ROOT,
        attended=attended,
        tool=ToolCall(ToolCategory.SHELL, "Bash", {"command": command}, command=command),
    )


def write_event(path: str, content: str = "x", *, attended: bool = True) -> ChaturEvent:
    return ChaturEvent(
        kind=EventKind.PRE_TOOL,
        assistant="test",
        session_id="s",
        cwd=ROOT,
        attended=attended,
        tool=ToolCall(
            ToolCategory.FILE_WRITE, "Write", {"file_path": path, "content": content}, paths=(path,)
        ),
    )


def tool_event(category: ToolCategory, name: str, *, attended: bool = True) -> ChaturEvent:
    return ChaturEvent(
        kind=EventKind.PRE_TOOL,
        assistant="test",
        session_id="s",
        cwd=ROOT,
        attended=attended,
        tool=ToolCall(category, name, {}),
    )


def stop_event() -> ChaturEvent:
    return ChaturEvent(kind=EventKind.STOP, assistant="test", session_id="s", cwd=ROOT)


_POLICIES: dict[str, object] = {}


def check(
    event: ChaturEvent, profile: str = "standard", ctx: GuardContext | None = None
) -> Verdict:
    if profile not in _POLICIES:
        _POLICIES[profile] = load_policy(profile)
    return evaluate(event, _POLICIES[profile], ctx)  # type: ignore[arg-type]


def hit_ids(verdict: Verdict) -> set[str]:
    return {h.rule_id for h in verdict.hits}


@pytest.fixture
def standard():
    return load_policy("standard")
