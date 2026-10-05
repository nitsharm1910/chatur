"""Claude Code adapter: parse, render, install (ADR-0025)."""

import json
from pathlib import Path

import pytest

from chatur.adapters import claude_code as cc
from chatur.adapters import get_adapter
from chatur.events import EventKind, ToolCategory
from chatur.verdict import Decision, RuleHit, Verdict

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "claude_code" / "payloads.json").read_text(
        encoding="utf-8"
    )
)
REPO = Path(__file__).resolve().parents[1]


def _verdict(decision: Decision) -> Verdict:
    return Verdict.from_hits([RuleHit("r", decision, "because")])


# --------------------------------------------------------------------------- parse


@pytest.mark.parametrize(
    ("name", "kind", "category"),
    [
        ("pre_bash_status", EventKind.PRE_TOOL, ToolCategory.SHELL),
        ("pre_powershell_remove_state", EventKind.PRE_TOOL, ToolCategory.SHELL),
        ("pre_write_readme", EventKind.PRE_TOOL, ToolCategory.FILE_WRITE),
        ("pre_edit", EventKind.PRE_TOOL, ToolCategory.FILE_WRITE),
        ("pre_read", EventKind.PRE_TOOL, ToolCategory.FILE_READ),
        ("pre_todowrite", EventKind.PRE_TOOL, ToolCategory.INTERNAL),
        ("pre_mcp_push_files", EventKind.PRE_TOOL, ToolCategory.MCP),
        ("pre_unknown_tool", EventKind.PRE_TOOL, ToolCategory.OTHER),
        ("post_write", EventKind.POST_TOOL, ToolCategory.FILE_WRITE),
        ("post_failure", EventKind.TOOL_FAILURE, ToolCategory.SHELL),
        ("prompt_plain", EventKind.PROMPT, None),
        ("session_start", EventKind.SESSION_START, None),
        ("stop", EventKind.STOP, None),
        ("subagent_stop", EventKind.SUBAGENT_STOP, None),
        ("session_end", EventKind.SESSION_END, None),
    ],
)
def test_parse_fixture(name, kind, category):
    event = cc.parse(FIXTURES[name], {})
    assert event.kind is kind
    assert event.assistant == "claude_code"
    assert (event.tool.category if event.tool else None) is category
    assert "tool_input" not in event.raw and "transcript_path" not in event.raw
    assert event.raw["hook_event_name"] == FIXTURES[name]["hook_event_name"]


def test_parse_details():
    shell = cc.parse(FIXTURES["pre_bash_status"], {})
    assert shell.tool.command == "git status"
    assert shell.session_id == "s1" and shell.cwd == "/repo"
    write = cc.parse(FIXTURES["pre_write_readme"], {})
    assert write.tool.paths == ("/repo/README.md",)
    assert write.tool.args["content"].startswith("# Hello")  # guard sees content
    assert cc.parse(FIXTURES["prompt_plain"], {}).prompt == "Build the authentication module"
    assert cc.parse(FIXTURES["pre_subagent_bash"], {}).agent == "developer"


@pytest.mark.parametrize(
    ("mode", "attended"),
    [
        ("default", True),
        ("plan", True),
        ("auto", True),  # observed 2026-10-04: hook "ask" prompts the user (ADR-0026)
        ("acceptEdits", True),  # unverified (ADR-0026)
        ("bypassPermissions", True),  # unverified (ADR-0026)
        ("dontAsk", False),
    ],
)
def test_permission_mode_table(mode, attended):
    payload = {**FIXTURES["pre_bash_status"], "permission_mode": mode}
    assert cc.parse(payload, {}).attended is attended


def test_attended():
    assert cc.parse(FIXTURES["pre_bash_status"], {}).attended is True
    assert cc.parse(FIXTURES["pre_dontask_bash"], {}).attended is False
    assert cc.parse(FIXTURES["pre_bash_status"], {"CI": "true"}).attended is False
    assert cc.parse(FIXTURES["pre_bash_status"], {"GITHUB_ACTIONS": "true"}).attended is False


def test_unhandled_event_ignored():
    assert cc.parse(FIXTURES["notification"], {}) is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"hook_event_name": 3},
        {"hook_event_name": "PreToolUse"},
        {"hook_event_name": "PreToolUse", "tool_name": ""},
    ],
)
def test_parse_rejects_bad_input(payload):
    with pytest.raises(ValueError):
        cc.parse(payload, {})


def test_project_root():
    assert cc.project_root({"cwd": "/repo/sub"}, {"CLAUDE_PROJECT_DIR": "/repo"}) == Path("/repo")
    assert cc.project_root({"cwd": "/repo/sub"}, {}) == Path("/repo/sub")


def test_get_adapter_aliases():
    assert get_adapter("claude") is cc and get_adapter("Claude_Code") is cc
    with pytest.raises(ValueError, match="unknown assistant adapter"):
        get_adapter("copilot")


# --------------------------------------------------------------------------- render


def _render(fixture: str, decision: Decision | None, **kw):
    payload = FIXTURES[fixture]
    verdict = _verdict(decision) if decision else None
    out = cc.render(cc.parse(payload, {}), verdict, payload, **kw)
    return out, (json.loads(out.stdout) if out.stdout else None)


@pytest.mark.parametrize("decision", [Decision.ASK, Decision.DENY])
def test_pre_tool_ask_deny(decision):
    out, data = _render("pre_bash_status", decision)
    assert out.exit_code == 0
    spec = data["hookSpecificOutput"]
    assert spec == {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision.value,
        "permissionDecisionReason": "Chatur: [r] because",
    }


@pytest.mark.parametrize("decision", [Decision.ALLOW, Decision.LOG, None])
def test_pre_tool_allow_defers_to_claude(decision):
    out, data = _render("pre_bash_status", decision)
    assert data is None and out.exit_code == 0  # never "allow": Claude's own prompt still applies


def test_pre_tool_warn():
    _, data = _render("pre_bash_status", Decision.WARN)
    assert data == {"systemMessage": "Chatur: [r] because"}


def test_prompt_and_stop():
    assert _render("prompt_plain", Decision.DENY)[1] == {
        "decision": "block",
        "reason": "Chatur: [r] because",
    }
    assert "systemMessage" in _render("prompt_plain", Decision.WARN)[1]
    assert _render("stop", Decision.DENY)[1]["decision"] == "block"
    active = {**FIXTURES["stop"], "stop_hook_active": True}
    out = cc.render(cc.parse(active, {}), _verdict(Decision.DENY), active)
    assert json.loads(out.stdout) == {"systemMessage": "Chatur: [r] because"}  # no block loop
    assert _render("subagent_stop", Decision.ALLOW)[1] is None


def test_session_start_context():
    _, data = _render("session_start", None, context="ctx here")
    assert data == {
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "ctx here"}
    }
    assert _render("session_start", None)[1] is None


def test_observational_events_render_nothing():
    for name in ("post_write", "post_failure", "session_end"):
        assert _render(name, Decision.DENY)[1] is None


def test_failure_modes():
    closed = cc.failure("PreToolUse", "boom")
    assert closed.exit_code == 2 and "failing closed" in closed.stderr
    assert cc.failure(None, "boom").exit_code == 2  # unknown event: assume the worst
    assert cc.failure("PostToolUse", "boom").exit_code == 1


def test_on_session_start_writes_env_file(tmp_path):
    env_file = tmp_path / "env.sh"
    cc.on_session_start({"CLAUDE_ENV_FILE": str(env_file)})
    assert env_file.read_text(encoding="utf-8") == "export CHATUR_AGENT_SESSION=1\n"
    cc.on_session_start({})  # no env file: no-op


# --------------------------------------------------------------------------- install


def test_hook_settings_exec_form():
    hooks = cc.hook_settings(("py", "-m", "chatur", "hook", "claude_code"))
    assert set(hooks) == {e for e, _, _ in cc.HOOK_EVENTS}
    (entry,) = hooks["PreToolUse"]
    assert entry["matcher"] == "*"
    assert entry["hooks"][0] == {
        "type": "command",
        "timeout": 30,
        "command": "py",
        "args": ["-m", "chatur", "hook", "claude_code", "PreToolUse"],
    }
    assert "matcher" not in hooks["SessionStart"][0]


@pytest.mark.parametrize(
    ("handler", "ours"),
    [
        ({"command": "chatur hook claude_code PreToolUse"}, True),
        ({"command": "chatur", "args": ["hook", "claude_code", "Stop"]}, True),
        (
            {
                "command": "C:\\py\\python.exe",
                "args": ["-m", "chatur", "hook", "claude_code", "Stop"],
            },
            True,
        ),
        ({"command": "chatur.exe hook claude SessionStart"}, True),
        ({"command": "./scripts/lint.sh"}, False),
        ({"command": "echo chatur"}, False),
    ],
)
def test_is_chatur_handler(handler, ours):
    assert cc.is_chatur_handler(handler) is ours


FOREIGN = {
    "model": "opus",
    "hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "./lint.sh"}]}],
        "Notification": [{"hooks": [{"type": "command", "command": "notify-send hi"}]}],
    },
    "permissions": {"allow": ["Bash(npm test)"], "deny": ["Bash(rm -rf /)"]},
}


def test_install_round_trip_preserves_foreign_settings(tmp_path):
    path = cc.settings_path(tmp_path, local=False)
    path.parent.mkdir()
    path.write_text(json.dumps(FOREIGN), encoding="utf-8")
    inv = cc.SHARED_INVOCATION
    cc.install(tmp_path, local=False, invocation=inv)
    once = json.loads(path.read_text(encoding="utf-8"))
    cc.install(tmp_path, local=False, invocation=inv)  # idempotent
    twice = json.loads(path.read_text(encoding="utf-8"))
    assert once == twice
    assert twice["model"] == "opus"
    assert twice["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "./lint.sh"
    assert len(twice["hooks"]["PreToolUse"]) == 2
    assert "Bash(git push *)" in twice["permissions"]["deny"]
    assert twice["permissions"]["deny"][0] == "Bash(rm -rf /)"
    assert twice["permissions"]["allow"] == ["Bash(npm test)"]
    cc.uninstall(tmp_path, local=False)
    assert json.loads(path.read_text(encoding="utf-8")) == FOREIGN


def test_install_switches_invocation(tmp_path):
    cc.install(tmp_path, local=True, invocation=cc.SHARED_INVOCATION)
    cc.install(
        tmp_path, local=True, invocation=("C:/py/python.exe", "-m", "chatur", "hook", "claude_code")
    )
    data = json.loads(cc.settings_path(tmp_path, local=True).read_text(encoding="utf-8"))
    handlers = [h for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert len(handlers) == 1 and handlers[0]["command"] == "C:/py/python.exe"


def test_install_refuses_invalid_json(tmp_path):
    path = cc.settings_path(tmp_path, local=False)
    path.parent.mkdir()
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        cc.install(tmp_path, local=False, invocation=cc.SHARED_INVOCATION)
    assert path.read_text(encoding="utf-8") == "{oops"


def test_uninstall_missing_file(tmp_path):
    assert cc.uninstall(tmp_path, local=True) is None


def test_native_deny_covers_critical_commands():
    for rule in (
        "Bash(git commit *)",
        "PowerShell(git push *)",
        "Bash(gh pr merge *)",
        "Bash(chatur gate approve *)",
        "Edit(.chatur/state.json)",
        "Write(.chatur/audit/**)",
    ):
        assert rule in cc.NATIVE_DENY


def test_apm_hook_file_in_sync():
    committed = json.loads(
        (REPO / ".apm" / "hooks" / "chatur-claude.json").read_text(encoding="utf-8")
    )
    assert committed == cc.apm_hook_file(), "regenerate .apm/hooks/chatur-claude.json"
