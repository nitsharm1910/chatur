"""ChaturEvent / ToolCall model (ADR-0004)."""

import dataclasses
import json

import pytest

from chatur.events import SCHEMA, ChaturEvent, EventKind, ToolCall, ToolCategory, new_event_id


def _shell_event(command: str = "git status", **kw) -> ChaturEvent:
    return ChaturEvent(
        kind=EventKind.PRE_TOOL,
        assistant="claude_code",
        session_id="s-1",
        cwd="/repo",
        tool=ToolCall(
            category=ToolCategory.SHELL, name="Bash", args={"command": command}, command=command
        ),
        raw={"tool_input": {"command": command}},
        **kw,
    )


def test_round_trip_without_redaction():
    event = _shell_event(agent="developer", phase="build", attended=False)
    data = event.to_dict(redact_secrets=False)
    assert ChaturEvent.from_dict(json.loads(json.dumps(data))) == event


def test_defaults():
    event = _shell_event()
    assert event.schema == SCHEMA
    assert event.attended is True
    assert event.ts.endswith("Z")
    assert len(event.id) == 28


def test_event_is_immutable():
    event = _shell_event()
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.kind = EventKind.STOP  # type: ignore[misc]


def test_to_dict_redacts_by_default():
    secret = "ghp_" + "x" * 36
    data = _shell_event(f"git clone https://{secret}@github.com/a/b").to_dict()
    blob = json.dumps(data)
    assert secret not in blob
    assert "[REDACTED:github_token]" in blob


def test_redaction_does_not_touch_live_event():
    secret = "ghp_" + "x" * 36
    event = _shell_event(f"echo {secret}")
    event.to_dict()
    assert secret in event.tool.command  # guard engine must see the real value


def test_ids_are_time_ordered_and_unique():
    ids = [new_event_id() for _ in range(200)]
    assert len(set(ids)) == 200
    assert [i[:12] for i in ids] == sorted(i[:12] for i in ids)


def test_unknown_schema_rejected():
    data = _shell_event().to_dict()
    data["schema"] = "chatur.event/v999"
    with pytest.raises(ValueError, match="unsupported event schema"):
        ChaturEvent.from_dict(data)


def test_unknown_kind_rejected():
    data = _shell_event().to_dict()
    data["kind"] = "teleport"
    with pytest.raises(ValueError):
        ChaturEvent.from_dict(data)


def test_event_without_tool():
    event = ChaturEvent(
        kind=EventKind.PROMPT, assistant="copilot", session_id="s", cwd=".", prompt="hi"
    )
    assert ChaturEvent.from_dict(event.to_dict()) == event
