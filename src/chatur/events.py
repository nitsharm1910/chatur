"""Normalized event model shared by every adapter, the guard engine, audit, and gates (ADR-0004).

Stdlib-only (ADR-0012). Changing field names or semantics is a breaking change (AGENTS.md rule 8).
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from chatur.redact import redact

SCHEMA = "chatur.event/v1"


class EventKind(StrEnum):
    SESSION_START = "session_start"
    PROMPT = "prompt"
    PRE_TOOL = "pre_tool"
    POST_TOOL = "post_tool"
    TOOL_FAILURE = "tool_failure"
    STOP = "stop"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_STOP = "subagent_stop"
    SESSION_END = "session_end"
    ERROR = "error"
    GATE = "gate"  # human gate approve/revoke via the chatur CLI (ADR-0021)


class ToolCategory(StrEnum):
    SHELL = "shell"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    SEARCH = "search"
    WEB = "web"
    AGENT = "agent"
    MCP = "mcp"
    INTERNAL = "internal"  # assistant-internal: todo lists, questions, plan mode (ADR-0025)
    OTHER = "other"


def new_event_id() -> str:
    """Time-ordered id: 12 hex chars of epoch-ms + 16 random hex chars (sortable, unique)."""
    return f"{time.time_ns() // 1_000_000:012x}{secrets.token_hex(8)}"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A tool invocation, classified so rules can target categories rather than tool names."""

    category: ToolCategory
    name: str
    args: Mapping[str, Any] = field(default_factory=dict)
    command: str | None = None  # full shell command, for SHELL tools
    paths: tuple[str, ...] = ()  # files the tool reads/writes/deletes

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "name": self.name,
            "args": dict(self.args),
            "command": self.command,
            "paths": list(self.paths),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ToolCall:
        return cls(
            category=ToolCategory(data["category"]),
            name=data["name"],
            args=dict(data.get("args") or {}),
            command=data.get("command"),
            paths=tuple(data.get("paths") or ()),
        )


@dataclass(frozen=True, slots=True)
class ChaturEvent:
    kind: EventKind
    assistant: str  # adapter id: "claude_code", "copilot", ...
    session_id: str
    cwd: str
    tool: ToolCall | None = None
    prompt: str | None = None  # user prompt text, for PROMPT events
    agent: str | None = None  # active subagent/custom agent, when the assistant exposes it
    phase: str | None = None  # SDLC phase from .chatur/state.json
    attended: bool = True  # False only when the adapter knows no human can answer (ADR-0014)
    raw: Mapping[str, Any] = field(default_factory=dict)  # original native payload
    id: str = field(default_factory=new_event_id)
    ts: str = field(default_factory=utc_now)
    schema: str = SCHEMA

    def to_dict(self, *, redact_secrets: bool = True) -> dict[str, Any]:
        """Serialise for persistence. Redaction is on by default (ADR-0015)."""
        data: dict[str, Any] = {
            "schema": self.schema,
            "id": self.id,
            "ts": self.ts,
            "kind": self.kind.value,
            "assistant": self.assistant,
            "session_id": self.session_id,
            "cwd": self.cwd,
            "tool": self.tool.to_dict() if self.tool else None,
            "prompt": self.prompt,
            "agent": self.agent,
            "phase": self.phase,
            "attended": self.attended,
            "raw": dict(self.raw),
        }
        return redact(data) if redact_secrets else data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ChaturEvent:
        schema = data.get("schema", SCHEMA)
        if schema != SCHEMA:
            raise ValueError(f"unsupported event schema {schema!r}; expected {SCHEMA!r}")
        tool = data.get("tool")
        return cls(
            kind=EventKind(data["kind"]),
            assistant=data["assistant"],
            session_id=data["session_id"],
            cwd=data["cwd"],
            tool=ToolCall.from_dict(tool) if tool else None,
            prompt=data.get("prompt"),
            agent=data.get("agent"),
            phase=data.get("phase"),
            attended=bool(data.get("attended", True)),
            raw=dict(data.get("raw") or {}),
            id=data["id"],
            ts=data["ts"],
            schema=schema,
        )
