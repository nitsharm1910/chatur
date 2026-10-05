"""Guard engine: per-rule allow/deny cases, profiles, context, defaults (ADR-0014/0016/0017)."""

from dataclasses import replace

import pytest

from chatur.events import ChaturEvent, EventKind, ToolCall, ToolCategory
from chatur.guard import GuardContext, error_verdict, evaluate, path_matches
from chatur.policy import load_policy
from chatur.verdict import Decision
from conftest import check, hit_ids, shell_event, stop_event, tool_event, write_event

# --------------------------------------------------------------------------- rule coverage
# AGENTS.md rule 5: every rule in every shipped profile is triggered by at least one case.
TRIGGERS = {
    "git.no-commit-push": shell_event("git commit -m x"),
    "git.no-history-rewrite": shell_event("git reset --hard HEAD~1"),
    "git.remote-tools": tool_event(ToolCategory.MCP, "mcp__github__push_files"),
    "git.remote-cli": shell_event("gh pr merge 12 --squash"),
    "gate.no-agent-approval": shell_event("chatur gate approve design"),
    "secrets.known-token": write_event(
        "cfg.py", "K = 'ghp_" + "Q7dLm2xP9vR4kT8wZ1bN6cY3hJ5fS0gAeUoI'"
    ),
    "secrets.credential-shape": write_event("cfg.py", 'DB_PASSWORD = "s3cr3t-Value9"'),
    "agent.read-only": ChaturEvent(
        kind=EventKind.PRE_TOOL,
        assistant="t",
        session_id="s",
        cwd="/repo",
        agent="chatur-reviewer",
        tool=ToolCall(ToolCategory.FILE_WRITE, "Write", {}, paths=("x.md",)),
    ),
    "agent.write-scope": ChaturEvent(
        kind=EventKind.PRE_TOOL,
        assistant="t",
        session_id="s",
        cwd="/repo",
        agent="chatur-qa",
        tool=ToolCall(ToolCategory.FILE_WRITE, "Write", {}, paths=("src/app.py",)),
    ),
    "secrets.in-prompt": ChaturEvent(
        kind=EventKind.PROMPT,
        assistant="t",
        session_id="s",
        cwd="/repo",
        prompt="password=Hunter2Pass",
    ),
    "gate.state-protected": write_event(".chatur/state.json"),
    "fs.change-needs-approval": write_event("README.md"),
    "exec.needs-approval": shell_event("ls"),
    "exec.no-new-executables": write_event("deploy.sh"),
    "fs.protected-paths": write_event(".github/workflows/ci.yml"),
    "gate.design-before-code": write_event("src/app.py"),
    "test.missing-tests": stop_event(),
    "deps.needs-adr": shell_event("pip install requests"),
    "net.web-tools": tool_event(ToolCategory.WEB, "WebFetch"),
}
COVERAGE_CTX = GuardContext(missing_tests=True)


def test_every_shipped_rule_has_a_trigger():
    shipped = {r.id for p in ("strict", "standard", "relaxed") for r in load_policy(p).rules}
    assert shipped == set(TRIGGERS)


@pytest.mark.parametrize("profile", ["strict", "standard", "relaxed"])
@pytest.mark.parametrize("rule_id", sorted(TRIGGERS))
def test_trigger_hits_rule(profile, rule_id):
    policy = load_policy(profile)
    if rule_id not in {r.id for r in policy.rules}:
        pytest.skip(f"{rule_id} not in {profile}")
    assert rule_id in hit_ids(evaluate(TRIGGERS[rule_id], policy, COVERAGE_CTX))


# --------------------------------------------------------------------------- allow cases


def test_file_read_allowed():
    assert check(tool_event(ToolCategory.FILE_READ, "Read")).decision is Decision.ALLOW


def test_search_allowed():
    assert check(tool_event(ToolCategory.SEARCH, "Grep")).decision is Decision.ALLOW


def test_mcp_read_tool_allowed():
    v = check(tool_event(ToolCategory.MCP, "mcp__github__get_file_contents"))
    assert v.decision is Decision.ALLOW


def test_stop_without_missing_tests_allowed():
    assert check(stop_event(), "strict").decision is Decision.ALLOW


# --------------------------------------------------------------------------- ADR-0014 baseline


@pytest.mark.parametrize(
    "command",
    ["git status", "git log --oneline -5", "git diff", "ls -la", "python -m pytest", "npm test"],
)
@pytest.mark.parametrize("profile", ["strict", "standard", "relaxed"])
def test_read_only_commands_still_need_approval(command, profile):
    v = check(shell_event(command), profile)
    assert v.decision is Decision.ASK
    assert "exec.needs-approval" in hit_ids(v)


@pytest.mark.parametrize("profile", ["strict", "standard", "relaxed"])
def test_commit_denied_in_every_profile(profile):
    v = check(shell_event("git commit -m 'msg'"), profile)
    assert v.decision is Decision.DENY
    assert v.reason.startswith("[git.no-commit-push]")


@pytest.mark.parametrize("profile", ["strict", "standard", "relaxed"])
def test_any_write_needs_approval(profile):
    assert check(write_event("docs/notes.md"), profile).decision is Decision.ASK


def test_unattended_ask_becomes_deny():
    assert check(shell_event("git status", attended=False)).decision is Decision.DENY
    assert check(write_event("docs/x.md", attended=False)).decision is Decision.DENY


def test_unattended_log_stays_log():
    v = check(tool_event(ToolCategory.WEB, "WebFetch", attended=False))
    assert v.decision is Decision.LOG


def test_new_executable_flagged():
    assert "exec.no-new-executables" in hit_ids(check(write_event("scripts/run.ps1")))
    assert "exec.no-new-executables" in hit_ids(check(write_event("tool", "#!/bin/sh\necho")))
    assert "exec.no-new-executables" in hit_ids(check(shell_event("chmod +x tool")))
    assert "exec.no-new-executables" not in hit_ids(check(write_event("notes.md", "hello")))


@pytest.mark.parametrize(
    "command",
    [
        "rm .chatur/state.json",
        "echo {} > .chatur/state.json",
        r"Remove-Item .Chatur\State.json",
        "rm -rf .chatur",
        "rm -rf .chatur/audit",
        "rm .chat*/state.json",
        "rm -rf .*",
        "mv /repo/.chatur/state.json /tmp/x",
        "cp evil.json src/../.chatur/state.json",
        "pwsh -c 'Set-Content .chatur/audit/2026-10-03.jsonl x'",
    ],
)
def test_gate_state_protected_from_shell(command):
    v = check(shell_event(command))
    assert v.decision is Decision.DENY
    assert "gate.state-protected" in hit_ids(v)


def test_gate_state_not_triggered_by_dot():
    assert "gate.state-protected" not in hit_ids(check(shell_event("ls .")))


# --------------------------------------------------------------------------- profiles + context


def test_design_gate_by_profile_and_context():
    event = write_event("src/app.py")
    assert check(event, "strict").decision is Decision.DENY
    assert check(event, "standard").decision is Decision.ASK  # ask (baseline) beats warn
    assert "gate.design-before-code" in hit_ids(check(event, "standard"))
    approved = GuardContext(approved_gates=frozenset({"design"}))
    assert check(event, "strict", approved).decision is Decision.ASK
    assert "gate.design-before-code" not in hit_ids(check(event, "strict", approved))


def test_design_gate_only_for_code_paths():
    assert "gate.design-before-code" not in hit_ids(check(write_event("docs/design/x.md")))


def test_missing_tests_on_stop():
    ctx = GuardContext(missing_tests=True)
    assert check(stop_event(), "standard", ctx).decision is Decision.WARN
    assert check(stop_event(), "strict", ctx).decision is Decision.DENY
    assert check(stop_event(), "relaxed", ctx).decision is Decision.ALLOW


def test_deps_rule_respects_adr_context():
    event = shell_event("npm install left-pad")
    assert "deps.needs-adr" in hit_ids(check(event))
    assert "deps.needs-adr" not in hit_ids(check(event, ctx=GuardContext(adr_changed=True)))
    assert "deps.needs-adr" in hit_ids(check(write_event("services/api/pyproject.toml")))


def test_protected_paths_by_profile():
    event = write_event(".github/workflows/release.yml")
    assert check(event, "strict").decision is Decision.DENY
    assert check(event, "standard").decision is Decision.ASK
    assert check(event, "relaxed").decision is Decision.ASK  # baseline ask beats relaxed warn


def test_web_by_profile():
    event = tool_event(ToolCategory.WEB, "WebSearch")
    assert check(event, "strict").decision is Decision.ASK
    assert check(event, "standard").decision is Decision.LOG


# --------------------------------------------------------------------------- defaults


def test_unknown_tool_default():
    event = tool_event(ToolCategory.OTHER, "mystery")
    assert check(event, "standard").decision is Decision.ASK
    assert check(event, "strict").decision is Decision.DENY
    assert check(tool_event(ToolCategory.OTHER, "x", attended=False)).decision is Decision.DENY


def test_unparseable_command_default():
    v = check(shell_event('echo "oops'))
    assert v.decision is Decision.ASK
    assert "default.unparseable_command" in hit_ids(v)


def test_error_verdict_fails_closed():
    assert error_verdict(load_policy("relaxed"), "boom").decision is Decision.DENY
    assert error_verdict(None, "no policy").decision is Decision.DENY


# --------------------------------------------------------------------------- allowlist


def test_readonly_allowlist_suppresses_only_any_selector():
    policy = load_policy("standard")
    enabled = replace(policy, readonly_allowlist=(r"^git\s+(status|log|diff|show)\b",))
    assert evaluate(shell_event("git status"), enabled).decision is Decision.ALLOW
    # not simple -> still ask
    assert evaluate(shell_event("git status && ls"), enabled).decision is Decision.ASK
    # other rules still apply
    assert (
        evaluate(shell_event("git status > .chatur/state.json"), enabled).decision is Decision.DENY
    )


# --------------------------------------------------------------------------- globs


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("deploy.sh", "**/*.sh", True),
        ("a/b/deploy.sh", "**/*.sh", True),
        ("services/api/pyproject.toml", "pyproject.toml", True),
        ("requirements-dev.txt", "requirements*.txt", True),
        (".GITHUB/Workflows/CI.yml", ".github/workflows/**", True),
        ("src/app.py", "src/**", True),
        ("srcx/app.py", "src/**", False),
        ("docs/src/app.py", "src/**", False),
        (".chatur", ".chatur/state.json", True),
        (".", ".chatur/state.json", False),
        (".c*", ".chatur/audit/**", True),
        ("README.md", "**/*.sh", False),
    ],
)
def test_path_matches(path, pattern, expected):
    assert path_matches(path, pattern) is expected
