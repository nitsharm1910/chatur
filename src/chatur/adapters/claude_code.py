"""Claude Code adapter: native hook payloads <-> ChaturEvent / Verdict (ADR-0025).

Stdlib-only (ADR-0012). Never returns permissionDecision "allow": that would skip Claude's own
permission prompt. Chatur only adds ask/deny on top of Claude's normal flow.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from chatur.adapters import HookOutput
from chatur.events import ChaturEvent, EventKind, ToolCall, ToolCategory
from chatur.verdict import Decision, Verdict

NAME = "claude_code"

EVENT_KINDS: Mapping[str, EventKind] = {
    "SessionStart": EventKind.SESSION_START,
    "UserPromptSubmit": EventKind.PROMPT,
    "PreToolUse": EventKind.PRE_TOOL,
    "PostToolUse": EventKind.POST_TOOL,
    "PostToolUseFailure": EventKind.TOOL_FAILURE,
    "Stop": EventKind.STOP,
    "SubagentStart": EventKind.SUBAGENT_START,
    "SubagentStop": EventKind.SUBAGENT_STOP,
    "SessionEnd": EventKind.SESSION_END,
}
_TOOL_EVENTS = frozenset({EventKind.PRE_TOOL, EventKind.POST_TOOL, EventKind.TOOL_FAILURE})

TOOL_CATEGORIES: Mapping[str, ToolCategory] = {
    "Bash": ToolCategory.SHELL,
    "PowerShell": ToolCategory.SHELL,
    "Write": ToolCategory.FILE_WRITE,
    "Edit": ToolCategory.FILE_WRITE,
    "MultiEdit": ToolCategory.FILE_WRITE,
    "NotebookEdit": ToolCategory.FILE_WRITE,
    "Read": ToolCategory.FILE_READ,
    "NotebookRead": ToolCategory.FILE_READ,
    "Glob": ToolCategory.SEARCH,
    "Grep": ToolCategory.SEARCH,
    "LS": ToolCategory.SEARCH,
    "WebFetch": ToolCategory.WEB,
    "WebSearch": ToolCategory.WEB,
    "Task": ToolCategory.AGENT,
    "Agent": ToolCategory.AGENT,
}
INTERNAL_TOOLS = frozenset(
    {
        "TodoWrite",
        "AskUserQuestion",
        "ExitPlanMode",
        "EnterPlanMode",
        "ToolSearch",
        "Skill",
        "SlashCommand",
        "BashOutput",
        "TaskOutput",
        "ListMcpResourcesTool",
        "ReadMcpResourceTool",
    }
)
_PATH_KEYS = ("file_path", "notebook_path", "path")
RAW_KEYS = (
    "hook_event_name",
    "tool_use_id",
    "permission_mode",
    "agent_id",
    "agent_type",
    "source",
    "reason",
    "stop_hook_active",
    "model",
)

# --------------------------------------------------------------------------- parse


def classify_tool(name: str) -> ToolCategory:
    if name in TOOL_CATEGORIES:
        return TOOL_CATEGORIES[name]
    if name.startswith("mcp__"):
        return ToolCategory.MCP
    if name in INTERNAL_TOOLS:
        return ToolCategory.INTERNAL
    return ToolCategory.OTHER


def _tool_call(name: str, tool_input: Any) -> ToolCall:
    args = dict(tool_input) if isinstance(tool_input, Mapping) else {}
    category = classify_tool(name)
    command = args.get("command") if category is ToolCategory.SHELL else None
    paths = tuple(str(args[k]) for k in _PATH_KEYS if isinstance(args.get(k), str))
    return ToolCall(
        category, name, args, command=command if isinstance(command, str) else None, paths=paths
    )


def is_attended(payload: Mapping[str, Any], env: Mapping[str, str]) -> bool:
    """ADR-0025: dontAsk and CI are unattended; other modes pending the dogfood check."""
    if payload.get("permission_mode") == "dontAsk":
        return False
    return not (env.get("CI") or env.get("GITHUB_ACTIONS"))


def parse(payload: Mapping[str, Any], env: Mapping[str, str]) -> ChaturEvent | None:
    """Native payload -> ChaturEvent. None for events Chatur doesn't handle."""
    event_name = payload.get("hook_event_name")
    if not isinstance(event_name, str):
        raise ValueError("hook input has no 'hook_event_name'")
    kind = EVENT_KINDS.get(event_name)
    if kind is None:
        return None
    tool = None
    if kind in _TOOL_EVENTS:
        tool_name = payload.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name:
            raise ValueError(f"{event_name} input has no 'tool_name'")
        tool = _tool_call(tool_name, payload.get("tool_input"))
    prompt = payload.get("prompt") if kind is EventKind.PROMPT else None
    return ChaturEvent(
        kind=kind,
        assistant=NAME,
        session_id=str(payload.get("session_id", "")),
        cwd=str(payload.get("cwd", "")),
        tool=tool,
        prompt=prompt if isinstance(prompt, str) else None,
        agent=payload.get("agent_type") if isinstance(payload.get("agent_type"), str) else None,
        attended=is_attended(payload, env),
        raw={k: payload[k] for k in RAW_KEYS if k in payload},
    )


def project_root(payload: Mapping[str, Any], env: Mapping[str, str]) -> Path:
    return Path(env.get("CLAUDE_PROJECT_DIR") or str(payload.get("cwd") or "."))


# --------------------------------------------------------------------------- render


def _out(obj: Mapping[str, Any]) -> HookOutput:
    return HookOutput(stdout=json.dumps(obj, ensure_ascii=False))


def render(
    event: ChaturEvent,
    verdict: Verdict | None,
    payload: Mapping[str, Any],
    context: str | None = None,
) -> HookOutput:
    decision = verdict.decision if verdict else Decision.ALLOW
    reason = f"Chatur: {verdict.reason}" if verdict else ""
    if event.kind is EventKind.SESSION_START:
        if not context:
            return HookOutput()
        return _out(
            {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
        )
    if event.kind is EventKind.PRE_TOOL:
        if decision in (Decision.ASK, Decision.DENY):
            return _out(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": decision.value,
                        "permissionDecisionReason": reason,
                    }
                }
            )
        return _out({"systemMessage": reason}) if decision is Decision.WARN else HookOutput()
    if event.kind in (EventKind.PROMPT, EventKind.STOP, EventKind.SUBAGENT_STOP):
        blocking_allowed = not (
            event.kind is not EventKind.PROMPT and payload.get("stop_hook_active")
        )
        if decision is Decision.DENY and blocking_allowed:
            return _out({"decision": "block", "reason": reason})
        if decision in (Decision.WARN, Decision.ASK, Decision.DENY):
            return _out({"systemMessage": reason})
    return HookOutput()


def failure(event_name: str | None, reason: str) -> HookOutput:
    """Internal error. PreToolUse fails closed (exit 2 blocks); everything else fails open."""
    if event_name == "PreToolUse" or event_name is None:
        return HookOutput(exit_code=2, stderr=f"{reason} (failing closed, ADR-0012)")
    return HookOutput(exit_code=1, stderr=reason)


def on_session_start(env: Mapping[str, str]) -> None:
    """Mark agent shells so gate approval and the git backstop can recognise them (ADR-0021)."""
    env_file = env.get("CLAUDE_ENV_FILE")
    if env_file:
        with Path(env_file).open("a", encoding="utf-8") as f:
            f.write("export CHATUR_AGENT_SESSION=1\n")


# --------------------------------------------------------------------------- install


HOOK_EVENTS: Sequence[tuple[str, str | None, int]] = (
    ("SessionStart", None, 15),
    ("UserPromptSubmit", None, 15),
    ("PreToolUse", "*", 30),
    ("PostToolUse", "*", 15),
    ("PostToolUseFailure", "*", 15),
    ("Stop", None, 15),
    ("SubagentStop", None, 15),
    ("SessionEnd", None, 15),
)
SHARED_INVOCATION = ("chatur", "hook", NAME)

_DENY_COMMANDS = (
    "git commit",
    "git push",
    "git merge",
    "git rebase",
    "git reset --hard",
    "git tag",
    "git cherry-pick",
    "git revert",
    "git clean",
    "git branch -D",
    "git filter-branch",
    "git update-ref",
    "gh pr merge",
    "gh pr create",
    "gh release create",
    "gh release delete",
    "gh repo delete",
    "glab mr merge",
    "glab mr create",
    "chatur gate approve",
    "chatur gate revoke",
)
NATIVE_DENY: tuple[str, ...] = (
    *(
        f"{tool}({cmd}{suffix})"
        for tool in ("Bash", "PowerShell")
        for cmd in _DENY_COMMANDS
        for suffix in ("", " *")
    ),
    *(
        f"{tool}({path})"
        for tool in ("Edit", "Write")
        for path in (".chatur/state.json", ".chatur/audit/**")
    ),
)
_CHATUR_HANDLER = re.compile(r"chatur(\.exe)?\s+hook\s+claude(_code)?\b", re.IGNORECASE)


def hook_settings(invocation: Sequence[str], *, shell_form: bool = False) -> dict[str, Any]:
    """The `hooks` object for settings.json. Exec form by default; shell form for APM files."""
    hooks: dict[str, Any] = {}
    for event_name, matcher, timeout in HOOK_EVENTS:
        handler: dict[str, Any] = {"type": "command", "timeout": timeout}
        if shell_form:
            handler["command"] = " ".join([*invocation, event_name])
        else:
            handler["command"] = invocation[0]
            handler["args"] = [*invocation[1:], event_name]
        entry: dict[str, Any] = {"hooks": [handler]}
        if matcher:
            entry = {"matcher": matcher, **entry}
        hooks[event_name] = [entry]
    return hooks


def is_chatur_handler(handler: Mapping[str, Any]) -> bool:
    text = " ".join([str(handler.get("command", "")), *map(str, handler.get("args") or [])])
    return bool(_CHATUR_HANDLER.search(text))


def settings_path(root: Path, *, local: bool) -> Path:
    return root / ".claude" / ("settings.local.json" if local else "settings.json")


def _load_settings(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON ({exc}); fix it before installing") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _strip_chatur(data: dict[str, Any]) -> None:
    """Remove Chatur's hook handlers and native deny rules; keep everything else."""
    hooks = data.get("hooks")
    if isinstance(hooks, dict):
        for event_name in list(hooks):
            entries = []
            for entry in hooks[event_name] if isinstance(hooks[event_name], list) else []:
                handlers = [
                    h
                    for h in entry.get("hooks", [])
                    if not (isinstance(h, dict) and is_chatur_handler(h))
                ]
                if handlers:
                    entries.append({**entry, "hooks": handlers})
            if entries:
                hooks[event_name] = entries
            else:
                del hooks[event_name]
        if not hooks:
            del data["hooks"]
    permissions = data.get("permissions")
    if isinstance(permissions, dict) and isinstance(permissions.get("deny"), list):
        permissions["deny"] = [r for r in permissions["deny"] if r not in NATIVE_DENY]
        if not permissions["deny"]:
            del permissions["deny"]
        if not permissions:
            del data["permissions"]


def _write_settings(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def install(root: Path, *, local: bool, invocation: Sequence[str]) -> Path:
    """Merge Chatur's hooks and native deny rules into Claude settings (idempotent)."""
    path = settings_path(root, local=local)
    data = _load_settings(path)
    _strip_chatur(data)
    hooks = data.setdefault("hooks", {})
    for event_name, entries in hook_settings(invocation).items():
        hooks.setdefault(event_name, []).extend(entries)
    deny = data.setdefault("permissions", {}).setdefault("deny", [])
    deny.extend(rule for rule in NATIVE_DENY if rule not in deny)
    _write_settings(path, data)
    return path


def uninstall(root: Path, *, local: bool) -> Path | None:
    path = settings_path(root, local=local)
    if not path.is_file():
        return None
    data = _load_settings(path)
    _strip_chatur(data)
    _write_settings(path, data)
    return path


def apm_hook_file() -> dict[str, Any]:
    """Content of .apm/hooks/chatur-claude.json (shell form; `chatur` from PATH)."""
    return {"hooks": hook_settings(SHARED_INVOCATION, shell_form=True)}
