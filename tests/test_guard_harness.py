"""Harness boundary (ADR-0029): Chatur files are read-only for agents; tooling is gitignored."""

import pytest

from chatur.events import ChaturEvent, EventKind, ToolCall, ToolCategory
from chatur.project import TOOLING_IGNORES, ensure_gitignore, gitignore_block
from chatur.verdict import Decision
from conftest import ROOT, check, hit_ids, shell_event, write_event

HARNESS_WRITES = [
    ".chatur/config.toml",
    ".chatur/policy.local.toml",
    ".chatur/templates/prd.md",
    ".Chatur/Templates/PRD.md",  # case-insensitive (ADR-0017)
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/agents/chatur-developer.md",
    ".claude/commands/chatur-build.md",
    ".claude/skills/chatur-adr/SKILL.md",
    ".claude/skills/chatur-adr/assets/adr.md",
    ".claude/rules/chatur-sdlc.md",
    ".claude/.chatur-primitives.json",
    "/repo/.claude/agents/chatur-qa.md",  # absolute inside the project
]


@pytest.mark.parametrize("path", HARNESS_WRITES)
@pytest.mark.parametrize("profile", ["strict", "standard", "relaxed"])
def test_harness_writes_denied(path, profile):
    verdict = check(write_event(path), profile)
    assert verdict.decision is Decision.DENY
    assert "harness.read-only" in hit_ids(verdict)


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf .claude",
        "rm -rf .claude/skills",
        "Remove-Item .claude\\agents\\chatur-developer.md",
        "echo x >> .claude/settings.json",
        "sed -i s/deny/allow/ .claude/settings.local.json",
        "cp evil.md .claude/commands/chatur-build.md",
        "pwsh -c 'Set-Content .chatur/config.toml x'",
        "mv .chatur/templates/prd.md /tmp",
    ],
)
def test_harness_shell_denied(command):
    verdict = check(shell_event(command))
    assert verdict.decision is Decision.DENY
    assert "harness.read-only" in hit_ids(verdict)


@pytest.mark.parametrize(
    "event",
    [
        write_event(".claude/agents/my-own-agent.md"),  # project-owned agent
        write_event(".claude/commands/deploy.md"),
        write_event("docs/requirements/PRD-x.md"),
        write_event("docs/templates-guide.md"),
        shell_event("ls docs"),
        shell_event("grep -r login docs/"),
    ],
    ids=["own-agent", "own-command", "phase-artifact", "similar-name", "ls-docs", "grep-docs"],
)
def test_not_harness(event):
    verdict = check(event)
    assert "harness.read-only" not in hit_ids(verdict)
    assert verdict.decision is Decision.ASK  # ordinary ADR-0014 approval


def test_reading_harness_files_allowed():
    event = ChaturEvent(
        kind=EventKind.PRE_TOOL,
        assistant="t",
        session_id="s",
        cwd=ROOT,
        tool=ToolCall(ToolCategory.FILE_READ, "Read", {}, paths=(".chatur/templates/prd.md",)),
    )
    assert check(event).decision is Decision.ALLOW


# --------------------------------------------------------------------------- gitignore


@pytest.mark.parametrize("commit", [True, False])
def test_gitignore_block_ignores_tooling_keeps_governance(commit):
    block = gitignore_block(commit)
    for line in TOOLING_IGNORES:
        assert f"\n{line}\n" in block
    for governance in (".chatur/config.toml", ".chatur/policy.local.toml", ".chatur/state.json\n"):
        assert governance not in block
    assert ("\n.chatur/audit/\n" in block) is (not commit)


def test_ensure_gitignore_respects_config(tmp_path):
    (tmp_path / ".chatur").mkdir()
    (tmp_path / ".chatur" / "config.toml").write_text("[audit]\ncommit = false\n", encoding="utf-8")
    ensure_gitignore(tmp_path)
    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "\n.chatur/audit/\n" in text and ".claude/agents/chatur-*" in text
    assert ensure_gitignore(tmp_path).skipped == [".gitignore"]  # idempotent
