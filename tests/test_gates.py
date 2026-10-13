"""Phase gates: human-only approval, order, staleness, revoke, audit anchors (ADR-0008/0021)."""

import json
from pathlib import Path

import pytest

from chatur import gates
from chatur.audit import AuditLog, audit_dir, tail
from chatur.cli import main
from chatur.gates import GateError, approve, approved_gates, revoke, status, verify_gates
from conftest import shell_event

HUMAN = {"env": {}, "interactive": True, "confirm": lambda request: True, "who": "Tester <t@x>"}


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
    with pytest.raises(GateError, match="not confirmed; the 'requirements' gate was not changed"):
        approve(project, "requirements", **{**HUMAN, "confirm": lambda request: False})
    assert not gates.state_path(project).exists()


def test_confirmation_shows_what_is_approved(project):
    seen = []
    approve(project, "requirements", **{**HUMAN, "confirm": lambda r: seen.append(r) or True})
    (request,) = seen
    assert request.action == "approve" and request.phase == "requirements"
    assert request.approver == "Tester <t@x>"
    assert request.details == ("Artifacts (1 file):", "  - docs/requirements/PRD-login.md")


def test_confirmation_flags_reapproval(project):
    approve(project, "requirements", **HUMAN)
    (project / "docs" / "requirements" / "PRD-login.md").write_text("changed", encoding="utf-8")
    seen = []
    approve(project, "requirements", **{**HUMAN, "confirm": lambda r: seen.append(r) or True})
    assert seen[0].details[0].startswith("Re-approval")


def test_preconditions_checked_before_asking(tmp_path):
    asked = []
    with pytest.raises(GateError, match="no artifacts"):
        approve(tmp_path, "requirements", **{**HUMAN, "confirm": lambda r: asked.append(r)})
    with pytest.raises(GateError, match="earlier gate"):
        approve(tmp_path, "design", **{**HUMAN, "confirm": lambda r: asked.append(r)})
    assert asked == []  # never asked to confirm something that would fail


def test_long_artifact_lists_are_truncated(project):
    for i in range(15):
        (project / "docs" / "requirements" / f"extra-{i:02d}.md").write_text("x", encoding="utf-8")
    seen = []
    approve(project, "requirements", **{**HUMAN, "confirm": lambda r: seen.append(r) or True})
    details = seen[0].details
    assert details[0] == "Artifacts (16 files):"
    assert details[-1] == "  ... and 6 more"


def test_revoke_confirmation_lists_cascade(project):
    approve(project, "requirements", **HUMAN)
    approve(project, "design", **HUMAN)
    seen = []
    revoke(project, "requirements", **{**HUMAN, "confirm": lambda r: seen.append(r) or True})
    assert seen[0].details == ("Gates that will be revoked: requirements, design",)


# --------------------------------------------------------------------------- terminal prompt


def _request(phase: str = "requirements") -> gates.ConfirmRequest:
    return gates.ConfirmRequest("approve", phase, "Tester <t@x>", ("Artifacts (1 file):",))


def _answers(*values: str):
    it = iter(values)
    return lambda prompt: next(it)


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        (("requirements",), True),
        (("Requirements ",), True),  # case and surrounding spaces ignored
        (("PRD-tasks-cli", "requirements"), True),  # the reported mistake, then corrected
        (("x", "y", "z"), False),  # three wrong attempts
        (("",), False),  # empty line cancels
    ],
)
def test_terminal_prompt(capsys, answers, expected):
    from chatur.cli import _confirm

    assert _confirm("approve", read=_answers(*answers))(_request()) is expected
    out = capsys.readouterr().out
    assert "You are about to APPROVE the 'requirements' gate." in out
    assert "To confirm, type the phase name: requirements" in out
    if answers[0] == "PRD-tasks-cli":
        assert "You typed 'PRD-tasks-cli'. Type the phase name 'requirements' itself" in out


def test_terminal_prompt_ctrl_c_cancels():
    from chatur.cli import _confirm

    def interrupt(prompt):
        raise KeyboardInterrupt

    assert _confirm("approve", read=interrupt)(_request()) is False


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


def test_init_placeholder_readmes_are_not_artifacts(tmp_path):
    # Walkthrough finding (2026-10-11): placeholder READMEs counted as artifacts, so a gate could
    # be approved with no real document.
    from chatur.project import init_project

    init_project(tmp_path)
    assert all(s.file_count == 0 for s in status(tmp_path))
    with pytest.raises(GateError, match="no artifacts for 'requirements'"):
        approve(tmp_path, "requirements", **HUMAN)
    readme = tmp_path / "docs" / "requirements" / "README.md"
    readme.write_text("# Requirements\n\nThe real PRD lives here.\n", encoding="utf-8")
    assert approve(tmp_path, "requirements", **HUMAN)["artifacts"]["files"] == [
        "docs/requirements/README.md"  # edited README is real content and counts
    ]


def test_line_endings_dont_make_gates_stale(project):
    # Release smoke test (2026-10-12): Windows checkouts (autocrlf) have CRLF, Linux CI has LF.
    prd = project / "docs" / "requirements" / "PRD-login.md"
    prd.write_bytes(b"# PRD\nline two\n")
    approve(project, "requirements", **HUMAN)
    prd.write_bytes(b"# PRD\r\nline two\r\n")
    assert {s.phase: s.state for s in status(project)}["requirements"] == "approved"
    prd.write_bytes(b"# PRD\r\nline 2\r\n")  # a real content change is still detected
    assert {s.phase: s.state for s in status(project)}["requirements"] == "stale"


def test_binary_artifacts_hash_raw_bytes(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"\x00\r\n")
    (tmp_path / "b.bin").write_bytes(b"\x00\n")
    assert gates.artifact_digest(tmp_path, ["a.bin"]) != gates.artifact_digest(tmp_path, ["b.bin"])


def test_crlf_placeholder_still_recognised(tmp_path):
    from chatur.project import placeholder_readme

    path = tmp_path / "docs" / "design" / "README.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(placeholder_readme("design").replace("\n", "\r\n").encode("utf-8"))
    assert gates.collect_artifacts(tmp_path, ("docs/design/**/*.md",)) == []


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
