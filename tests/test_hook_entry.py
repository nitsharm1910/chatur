"""`chatur hook claude_code`: end-to-end through policy, guard, audit, render (ADR-0025)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from chatur.audit import audit_dir, tail, verify
from chatur.hook import run_hook
from chatur.project import init_project

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "claude_code" / "payloads.json").read_text(
        encoding="utf-8"
    )
)
TOKEN = "ghp_" + "Q7dLm2xP9vR4kT8wZ1bN6cY3hJ5fS0gAeUoI"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    init_project(tmp_path)
    return tmp_path


def hook(project: Path, payload: dict, event: str | None = None, **env):
    out = run_hook(
        "claude_code", json.dumps(payload), {"CLAUDE_PROJECT_DIR": str(project), **env}, event
    )
    return out, (json.loads(out.stdout) if out.stdout else None)


def decision(data: dict | None) -> str | None:
    return (data or {}).get("hookSpecificOutput", {}).get("permissionDecision")


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("pre_bash_push", "deny"),
        ("pre_powershell_remove_state", "deny"),
        ("pre_mcp_push_files", "deny"),
        ("pre_bash_status", "ask"),
        ("pre_write_readme", "ask"),
        ("pre_edit", "ask"),
        ("pre_unknown_tool", "ask"),
        ("pre_dontask_bash", "deny"),
        ("pre_read", None),
        ("pre_todowrite", None),
    ],
)
def test_pre_tool_decisions(project, fixture, expected):
    out, data = hook(project, FIXTURES[fixture], "PreToolUse")
    assert out.exit_code == 0, out.stderr
    assert decision(data) == expected


def test_every_event_is_audited_and_chain_valid(project):
    for name in (
        "session_start",
        "prompt_plain",
        "pre_bash_status",
        "post_failure",
        "stop",
        "session_end",
    ):
        hook(project, FIXTURES[name])
    records = tail(project, 20)
    assert [r["event"]["kind"] for r in records] == [
        "session_start",
        "prompt",
        "pre_tool",
        "tool_failure",
        "stop",
        "session_end",
    ]
    assert records[2]["verdict"]["decision"] == "ask"
    assert records[3]["verdict"] is None
    assert verify(project).ok


def test_file_contents_never_logged(project):
    payload = {**FIXTURES["pre_write_readme"]}
    payload["tool_input"] = {"file_path": "/repo/notes.md", "content": "TOP SECRET PLAN body"}
    hook(project, payload)
    raw = next(audit_dir(project).glob("*.jsonl")).read_text(encoding="utf-8")
    assert "TOP SECRET PLAN" not in raw
    args = tail(project, 1)[0]["event"]["tool"]["args"]
    assert args["file_path"] == "/repo/notes.md"
    assert set(args["content"]) == {"sha256", "chars"} and args["content"]["chars"] == 20


def test_secret_write_denied_and_masked(project):
    payload = {
        **FIXTURES["pre_write_readme"],
        "tool_input": {"file_path": "cfg.py", "content": f"T='{TOKEN}'"},
    }
    _, data = hook(project, payload)
    assert decision(data) == "deny"
    assert "secrets.known-token" in data["hookSpecificOutput"]["permissionDecisionReason"]
    assert TOKEN not in next(audit_dir(project).glob("*.jsonl")).read_text(encoding="utf-8")


def test_secret_in_prompt_warns_and_is_masked(project):
    _, data = hook(project, {**FIXTURES["prompt_plain"], "prompt": f"use {TOKEN} please"})
    assert "secret" in data["systemMessage"]
    assert TOKEN not in next(audit_dir(project).glob("*.jsonl")).read_text(encoding="utf-8")


def test_session_start_context_and_env(project, tmp_path_factory):
    env_file = tmp_path_factory.mktemp("env") / "claude.env"
    _, data = hook(project, FIXTURES["session_start"], CLAUDE_ENV_FILE=str(env_file))
    context = data["hookSpecificOutput"]["additionalContext"]
    assert (
        "Chatur guardrails are active (profile: standard; current SDLC phase: requirements)"
        in context
    )
    assert "CHATUR_AGENT_SESSION=1" in env_file.read_text(encoding="utf-8")


def test_unhandled_event_not_audited(project):
    out, data = hook(project, FIXTURES["notification"])
    assert out.exit_code == 0 and data is None
    assert not list(audit_dir(project).glob("*.jsonl"))


# --------------------------------------------------------------------------- fail closed


def test_invalid_json_fails_closed(project):
    out = run_hook("claude_code", "{not json", {"CLAUDE_PROJECT_DIR": str(project)}, "PreToolUse")
    assert out.exit_code == 2 and "failing closed" in out.stderr


def test_event_mismatch_fails_closed(project):
    out, _ = hook(project, FIXTURES["pre_bash_status"], "PostToolUse")
    assert out.exit_code == 1  # registered as PostToolUse: fail open
    out, _ = hook(project, FIXTURES["post_write"], "PreToolUse")
    assert out.exit_code == 2  # registered as PreToolUse: fail closed


def test_invalid_policy_fails_closed_for_pre_tool_only(project):
    (project / ".chatur" / "policy.local.toml").write_text("this is = = bad", encoding="utf-8")
    out, _ = hook(project, FIXTURES["pre_read"], "PreToolUse")
    assert out.exit_code == 2 and "PolicyError" in out.stderr
    out, _ = hook(project, FIXTURES["post_write"], "PostToolUse")
    assert out.exit_code == 1


def test_tampered_audit_fails_closed(project):
    hook(project, FIXTURES["pre_bash_status"])
    log = next(audit_dir(project).glob("*.jsonl"))
    log.write_text(
        log.read_text(encoding="utf-8").replace("git status", "git STATUS"), encoding="utf-8"
    )
    out, _ = hook(project, FIXTURES["pre_read"], "PreToolUse")
    assert out.exit_code == 2 and "AuditError" in out.stderr


def test_capture_dir_writes_redacted_fixture(project, tmp_path_factory):
    capture = tmp_path_factory.mktemp("cap")
    payload = {**FIXTURES["prompt_plain"], "prompt": f"token {TOKEN}"}
    hook(project, payload, CHATUR_CAPTURE_DIR=str(capture))
    (saved,) = capture.glob("UserPromptSubmit-*.json")
    assert TOKEN not in saved.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- real process


def test_cli_end_to_end_subprocess(project):
    result = subprocess.run(
        [sys.executable, "-m", "chatur", "hook", "claude_code", "PreToolUse"],
        input=json.dumps(FIXTURES["pre_bash_push"]).encode("utf-8"),
        capture_output=True,
        env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(project)},
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["hookSpecificOutput"]["permissionDecision"] == "deny"
