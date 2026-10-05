"""Agents can never approve or revoke gates (ADR-0008, ADR-0021)."""

import pytest

from chatur.verdict import Decision
from conftest import check, hit_ids, shell_event


@pytest.mark.parametrize(
    "command",
    [
        "chatur gate approve design",
        "chatur gate revoke requirements",
        "chatur.exe gate approve design --note ok",
        r"C:\tools\chatur.exe gate approve design",
        "/home/u/.local/bin/chatur gate approve design",
        "python -m chatur gate approve design",
        "py -3 -m chatur gate approve build",
        "uv run chatur gate approve design",
        "pipx run chatur gate approve design",
        'sh -c "chatur gate approve design"',
        "pwsh -c 'chatur gate approve design'",
        "echo design | chatur gate approve design",
    ],
)
def test_agent_gate_approval_denied(command):
    verdict = check(shell_event(command))
    assert verdict.decision is Decision.DENY, f"{command!r}: {verdict.reason}"
    assert "gate.no-agent-approval" in hit_ids(verdict)


@pytest.mark.parametrize(
    "command", ["chatur gate status", "chatur gate verify", "chatur audit verify"]
)
def test_read_only_gate_commands_ask(command):
    verdict = check(shell_event(command))
    assert verdict.decision is Decision.ASK
    assert "gate.no-agent-approval" not in hit_ids(verdict)
