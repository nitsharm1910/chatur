"""Phase gates: human-only approval, order, staleness, revoke, audit anchors (ADR-0008/0021)."""

import json
from pathlib import Path

import pytest

from chatur import gates
from chatur.audit import AuditLog, audit_dir, tail
from chatur.cli import main
from chatur.gates import GateError, approve, approved_gates, revoke, status, verify_gates
from conftest import shell_event

HUMAN = {"env": {}, "interactive": True, "confirm": lambda phase: True, "who": "Tester <t@x>"}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "requirements").mkdir(parents=True)
    (tmp_path / "docs" / "requirements" / "PRD-login.md").write_text("# PRD\n", encoding="utf-8")
    (tmp_path / "docs" / "design").mkdir(parents=True)
    (tmp_path / "docs" / "design" / "login.md").write_text("# Design\n", encoding="utf-8")
    return tmp_path


def _state(root: Path) -> dict:
    return json.loads(gates.state_path(root).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- approve


def test_approve_records_everything(project):
    record = approve(project, "requirements", note="kickoff", **HUMAN)
    assert record["approved_by"] == "Tester <t@x>"
    assert record["artifacts"]["files"] == ["docs/requirements/PRD-login.md"]
    assert record["artifacts"]["file_count"] == 1
    assert record["audit_anchor"] == {"seq": 0, "hash": "0" * 64}  # empty log
    assert record["note"] == "kickoff"
    assert _state(project)["gates"]["requirements"] == record
    assert not list(gates.state_path(project).parent.glob("*.tmp"))  # atomic write cleaned up


def test_approval_is_audited_and_anchored(project):
    AuditLog(project).append(shell_event("ls"))
    approve(project, "requirements", **HUMAN)
    record = _state(project)["gates"]["requirements"]
    assert record["audit_anchor"]["seq"] == 1
    last = tail(project, 1)[0]
    assert last["event"]["kind"] == "gate"
    assert last["event"]["raw"]["action"] == "approve"
    assert last["event"]["raw"]["phase"] == "requirements"


@pytest.mark.parametrize("marker", gates.AGENT_ENV_MARKERS)
def test_refuses_inside_agent_or_ci(project, marker):
    with pytest.raises(GateError, match=f"session detected \\({marker}\\)"):
        approve(project, "requirements", **{**HUMAN, "env": {marker: "1"}})
    assert not gates.state_path(project).exists()


def test_refuses_without_terminal(project):
    with pytest.raises(GateError, match="interactive terminal"):
        approve(project, "requirements", **{**HUMAN, "interactive": False})


def test_refuses_wrong_confirmation(project):
    with pytest.raises(GateError, match="confirmation did not match"):
        approve(project, "requirements", **{**HUMAN, "confirm": lambda phase: False})


def test_refuses_unknown_phase(project):
    with pytest.raises(GateError, match="unknown phase"):
        approve(project, "deploy", **HUMAN)


def test_sequential_order_enforced(project):
    with pytest.raises(GateError, match="earlier gate 'requirements' is pending"):
        approve(project, "design", **HUMAN)
    approve(project, "requirements", **HUMAN)
    approve(project, "design", **HUMAN)
    assert approved_gates(project) == {"requirements", "design"}


def test_refuses_without_artifacts(tmp_path):
    with pytest.raises(GateError, match="no artifacts for 'requirements'"):
        approve(tmp_path, "requirements", **HUMAN)


def test_already_approved(project):
    approve(project, "requirements", **HUMAN)
    with pytest.raises(GateError, match="already approved"):
        approve(project, "requirements", **HUMAN)


def test_edit_makes_gate_stale_and_blocks_next(project):
    approve(project, "requirements", **HUMAN)
    (project / "docs" / "requirements" / "PRD-login.md").write_text("# changed\n", encoding="utf-8")
    states = {s.phase: s.state for s in status(project)}
    assert states["requirements"] == "stale"
    with pytest.raises(GateError, match="'requirements' is stale"):
        approve(project, "design", **HUMAN)
    approve(project, "requirements", **HUMAN)  # re-approval refreshes the digest
    assert {s.phase: s.state for s in status(project)}["requirements"] == "approved"


def test_refuses_when_audit_log_tampered(project):
    AuditLog(project).append(shell_event("ls"))
    log_file = next(audit_dir(project).glob("*.jsonl"))
    log_file.write_text(log_file.read_text(encoding="utf-8").replace("ls", "xx"), encoding="utf-8")
    with pytest.raises(GateError, match="audit log failed verification"):
        approve(project, "requirements", **HUMAN)


def test_config_overrides_artifacts(project):
    (project / ".chatur").mkdir()
    (project / ".chatur" / "config.toml").write_text(
        '[gates.requirements]\nartifacts = ["specs/*.txt"]\n', encoding="utf-8"
    )
    with pytest.raises(GateError, match=r"specs/\*\.txt"):
        approve(project, "requirements", **HUMAN)
    (project / "specs").mkdir()
    (project / "specs" / "a.txt").write_text("x", encoding="utf-8")
    assert approve(project, "requirements", **HUMAN)["artifacts"]["files"] == ["specs/a.txt"]


def test_artifact_walk_skips_tool_dirs(project):
    (project / "node_modules" / "docs" / "requirements").mkdir(parents=True)
    (project / "node_modules" / "docs" / "requirements" / "x.md").write_text("x", encoding="utf-8")
    files = gates.collect_artifacts(project, ("**/requirements/*.md",))
    assert files == ["docs/requirements/PRD-login.md"]


# --------------------------------------------------------------------------- revoke


def test_revoke_cascades(project):
    approve(project, "requirements", **HUMAN)
    approve(project, "design", **HUMAN)
    assert revoke(project, "requirements", **HUMAN) == ["requirements", "design"]
    assert approved_gates(project) == frozenset()
    assert tail(project, 1)[0]["event"]["raw"]["action"] == "revoke"


def test_revoke_requires_human(project):
    approve(project, "requirements", **HUMAN)
    with pytest.raises(GateError, match="session detected"):
        revoke(project, "requirements", **{**HUMAN, "env": {"CLAUDECODE": "1"}})
    assert approved_gates(project) == {"requirements"}


def test_revoke_nothing(project):
    with pytest.raises(GateError, match="nothing to revoke"):
        revoke(project, "design", **HUMAN)


# --------------------------------------------------------------------------- hook path + verify


def test_approved_gates_is_tolerant(project):
    gates.state_path(project).parent.mkdir(parents=True)
    gates.state_path(project).write_text("{broken", encoding="utf-8")
    assert approved_gates(project) == frozenset()  # unreadable -> stricter (no gates)


def test_verify_ok(project):
    approve(project, "requirements", **HUMAN)
    approve(project, "design", **HUMAN)
    assert verify_gates(project) == []


def test_verify_reports_stale(project):
    approve(project, "requirements", **HUMAN)
    (project / "docs" / "requirements" / "new.md").write_text("x", encoding="utf-8")
    assert any("requirements: stale" in p for p in verify_gates(project))


def test_verify_detects_audit_tail_truncation(project):
    approve(project, "requirements", **HUMAN)  # anchor seq 0; approval itself is record 1
    approve(project, "design", **HUMAN)  # anchor = record 1
    log_file = next(audit_dir(project).glob("*.jsonl"))
    log_file.write_text("", encoding="utf-8")  # wipe the newest records
    problems = verify_gates(project)
    assert any("design: audit anchor seq 1 not found" in p for p in problems)


def test_verify_detects_out_of_order_state(project):
    approve(project, "requirements", **HUMAN)
    approve(project, "design", **HUMAN)
    state = _state(project)
    del state["gates"]["requirements"]
    gates.save_state(project, state)
    assert any(
        "design: approved although earlier gate 'requirements'" in p for p in verify_gates(project)
    )


# --------------------------------------------------------------------------- CLI


def test_cli_status(project, capsys):
    approve(project, "requirements", **HUMAN)
    assert main(["gate", "status", "--root", str(project)]) == 0
    out = capsys.readouterr().out
    assert "current phase: design" in out
    assert "requirements  approved" in out


def test_cli_status_json(project, capsys):
    assert main(["gate", "status", "--root", str(project), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["current"] == "requirements"
    assert [g["phase"] for g in data["gates"]] == list(gates.PHASES)


def test_cli_approve_refuses_under_pytest(project, capsys):
    # pytest has no TTY (and may run inside an agent session): must refuse.
    assert main(["gate", "approve", "requirements", "--root", str(project)]) == 1
    assert "refusing to approve" in capsys.readouterr().err
    assert not gates.state_path(project).exists()


def test_cli_verify(project, capsys):
    assert main(["gate", "verify", "--root", str(project)]) == 0
    approve(project, "requirements", **HUMAN)
    (project / "docs" / "requirements" / "PRD-login.md").write_text("edit", encoding="utf-8")
    assert main(["gate", "verify", "--root", str(project)]) == 1
    assert "stale" in capsys.readouterr().err
