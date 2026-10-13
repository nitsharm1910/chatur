"""Git and CI backstop (ADR-0030), against real temporary git repositories."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from chatur import backstop, gates, githooks
from chatur.audit import AuditLog, audit_dir
from chatur.backstop import BLOCK, WARN, added_lines
from chatur.cli import main
from chatur.policy import load_policy
from chatur.project import init_project
from conftest import shell_event

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

TOKEN = "ghp_" + "Q7dLm2xP9vR4kT8wZ1bN6cY3hJ5fS0gAeUoI"
HUMAN = {"env": {}, "interactive": True, "confirm": lambda r: True, "who": "Tester <t@x>"}
CLEAN_ENV = {k: v for k, v in os.environ.items() if k not in backstop.AGENT_MARKERS}


def run(root: Path, *args: str, env: dict | None = None, check: bool = True):
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, env=env or CLEAN_ENV, check=check
    )


def write(root: Path, rel: str, text: str = "x\n") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def stage(root: Path, *rels: str, force: bool = False) -> None:
    run(root, "add", *(["-f"] if force else []), *rels)


def commit(root: Path, message: str = "change") -> str:
    run(root, "commit", "-q", "--no-verify", "--allow-empty", "-m", message)
    return run(root, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    run(tmp_path, "init", "-q", "-b", "main")
    run(tmp_path, "config", "user.name", "Tester")
    run(tmp_path, "config", "user.email", "t@example.com")
    run(tmp_path, "config", "commit.gpgsign", "false")
    init_project(tmp_path)
    stage(tmp_path, ".")
    commit(tmp_path, "init")
    return tmp_path


def set_profile(root: Path, profile: str) -> None:
    cfg = root / ".chatur" / "config.toml"
    cfg.write_text(
        cfg.read_text(encoding="utf-8").replace('"standard"', f'"{profile}"'), encoding="utf-8"
    )


def checks(report: backstop.Report, severity: str | None = None) -> set[str]:
    return {f.check for f in report.findings if severity is None or f.severity == severity}


# --------------------------------------------------------------------------- units


def test_added_lines_parses_unified_diff():
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,0 +2,2 @@\n+one\n+two\n"
        "diff --git a/gone.py b/gone.py\n--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n"
    )
    assert list(added_lines(diff)) == [("a.py", 2, "one"), ("a.py", 3, "two")]


def test_agent_session_markers():
    assert backstop.check_agent_session({}) == []
    (finding,) = backstop.check_agent_session({"CHATUR_AGENT_SESSION": "1"})
    assert finding.severity == BLOCK and finding.rules == ("git.no-commit-push",)


def test_every_critical_git_or_ci_rule_has_a_backstop_check():
    covered = {r for rules in backstop.BACKSTOP_COVERAGE.values() for r in rules}
    for profile in ("strict", "standard", "relaxed"):
        for rule in load_policy(profile).rules:
            if rule.critical and {"git", "ci"} & set(rule.layers):
                assert rule.id in covered, f"{rule.id} ({profile}) has no git/ci backstop check"


# --------------------------------------------------------------------------- pre-commit


def test_clean_commit_passes(repo):
    write(repo, "notes.txt", "hello\n")
    stage(repo, "notes.txt")
    report = backstop.pre_commit(repo, {})
    assert not report.blocked, backstop.render(report)


def test_secret_blocks_with_location(repo):
    write(repo, "src/config.py", f"x = 1\nTOKEN = '{TOKEN}'\n")
    stage(repo, "src/config.py")
    report = backstop.pre_commit(repo, {})
    (finding,) = [f for f in report.findings if f.check == "secrets"]
    assert finding.severity == BLOCK and (finding.file, finding.line) == ("src/config.py", 2)
    assert TOKEN not in backstop.render(report)  # never echo the secret


def test_credential_warns_and_placeholder_ignored(repo):
    write(repo, "settings.py", 'DB_PASSWORD = "s3cr3t-Value9"\nAPI_KEY = "${API_KEY}"\n')
    stage(repo, "settings.py")
    secrets = [f for f in backstop.pre_commit(repo, {}).findings if f.check == "secrets"]
    assert [(f.severity, f.line) for f in secrets] == [(WARN, 1)]


def test_agent_session_blocks_pre_commit(repo):
    assert "agent-session" in checks(backstop.pre_commit(repo, {"CLAUDECODE": "1"}), BLOCK)


def test_tampered_audit_blocks(repo):
    AuditLog(repo).append(shell_event("ls"))
    log = next(audit_dir(repo).glob("*.jsonl"))
    log.write_text(log.read_text(encoding="utf-8").replace('"ls"', '"rm"'), encoding="utf-8")
    assert "governance" in checks(backstop.pre_commit(repo, {}), BLOCK)


def test_hand_edited_approval_blocks(repo):
    write(repo, "docs/requirements/PRD.md", "# PRD\n")
    fake = {
        "approved_by": "Mallory",
        "approved_at": "2026-01-01T00:00:00.000Z",
        "artifacts": {"digest": "0" * 64, "file_count": 1},
        "audit_anchor": {"seq": 0, "hash": "0" * 64},
    }
    AuditLog(repo).append(shell_event("ls"))  # a log exists, but has no approval record
    gates.save_state(repo, {"schema": "chatur.state/v1", "gates": {"requirements": fake}})
    report = backstop.pre_commit(repo, {})
    assert any(
        "no matching audit record" in f.message for f in report.findings if f.severity == BLOCK
    )


def test_real_approval_passes_governance(repo):
    write(repo, "docs/requirements/PRD.md", "# PRD\n")
    gates.approve(repo, "requirements", **HUMAN)
    report = backstop.pre_commit(repo, {})
    assert "governance" not in checks(report), backstop.render(report)


def test_invalid_policy_blocks(repo):
    write(repo, ".chatur/policy.local.toml", "this is = = broken")
    assert "governance" in checks(backstop.pre_commit(repo, {}), BLOCK)


@pytest.mark.parametrize(
    ("profile", "expected"), [("strict", BLOCK), ("standard", WARN), ("relaxed", None)]
)
def test_missing_tests_by_profile(repo, profile, expected):
    set_profile(repo, profile)
    stage(repo, ".chatur/config.toml")
    commit(repo, "profile")
    write(repo, "src/app.py", "def f():\n    return 1\n")
    stage(repo, "src/app.py")
    found = [f for f in backstop.pre_commit(repo, {}).findings if "test.missing-tests" in f.rules]
    assert [f.severity for f in found] == ([expected] if expected else [])


def test_code_with_tests_is_fine(repo):
    set_profile(repo, "strict")
    write(repo, "src/app.py", "def f(): ...\n")
    write(repo, "tests/test_app.py", "def test_f(): ...\n")
    stage(repo, ".")
    assert not [
        f for f in backstop.pre_commit(repo, {}).findings if "test.missing-tests" in f.rules
    ]


def test_dependency_needs_adr_in_strict(repo):
    set_profile(repo, "strict")
    write(repo, "pyproject.toml", "[project]\nname='x'\n")
    stage(repo, ".")
    found = [f for f in backstop.pre_commit(repo, {}).findings if "deps.needs-adr" in f.rules]
    assert found and found[0].severity == BLOCK and found[0].file == "pyproject.toml"
    write(repo, "docs/decisions/0001-add-dependency.md", "---\nid: ADR-0001\n---\n")
    stage(repo, ".")
    assert not [f for f in backstop.pre_commit(repo, {}).findings if "deps.needs-adr" in f.rules]


def test_design_gate_in_strict(repo):
    set_profile(repo, "strict")
    write(repo, "src/app.py", "x = 1\n")
    write(repo, "tests/test_app.py", "x = 1\n")
    stage(repo, ".")
    found = [
        f for f in backstop.pre_commit(repo, {}).findings if "gate.design-before-code" in f.rules
    ]
    assert found and found[0].severity == BLOCK


def test_force_added_tooling_warns(repo):
    write(repo, ".claude/agents/chatur-developer.md", "agent\n")
    stage(repo, ".claude/agents/chatur-developer.md", force=True)
    assert "harness-tooling" in checks(backstop.pre_commit(repo, {}), WARN)


def test_stale_gate_warns_locally_blocks_in_ci(repo):
    write(repo, "docs/requirements/PRD.md", "# PRD\n")
    gates.approve(repo, "requirements", **HUMAN)
    write(repo, "docs/requirements/PRD.md", "# PRD v2\n")
    assert "stale-gates" in checks(backstop.pre_commit(repo, {}), WARN)
    assert "stale-gates" in checks(backstop.ci_check(repo), BLOCK)


# --------------------------------------------------------------------------- CI


def test_ci_range_secret_and_trailers(repo):
    base = run(repo, "rev-parse", "HEAD").stdout.strip()
    write(repo, "a.txt", "fine\n")
    stage(repo, "a.txt")
    commit(repo, "feat: a\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    write(repo, "b.txt", "fine\n")
    stage(repo, "b.txt")
    commit(repo, "feat: b\n\nCo-Authored-By: Claude <noreply@anthropic.com>\nApproved-by: Nitin")
    report = backstop.ci_check(repo, base=base)
    trailers = [f for f in report.findings if f.check == "ai-trailers"]
    assert len(trailers) == 1 and trailers[0].severity == WARN and not report.blocked
    write(repo, "c.py", f"T = '{TOKEN}'\n")
    stage(repo, "c.py")
    commit(repo, "oops")
    assert "secrets" in checks(backstop.ci_check(repo, base=base), BLOCK)


def test_ci_detects_history_rewrite(repo):
    write(repo, "a.txt", "1\n")
    stage(repo, "a.txt")
    first = commit(repo, "one")
    run(repo, "reset", "-q", "--hard", "HEAD~1")
    write(repo, "b.txt", "2\n")
    stage(repo, "b.txt")
    commit(repo, "two")
    assert "history-rewrite" in checks(backstop.ci_check(repo, before=first), BLOCK)
    assert "history-rewrite" in checks(backstop.ci_check(repo, before="f" * 40), BLOCK)
    assert "history-rewrite" not in checks(backstop.ci_check(repo, before="0" * 40))


# --------------------------------------------------------------------------- pre-push


def test_pre_push_scans_new_commits(repo):
    write(repo, "c.py", f"T = '{TOKEN}'\n")
    stage(repo, "c.py")
    sha = commit(repo, "secret")
    stdin = f"refs/heads/main {sha} refs/heads/main {'0' * 40}\n"
    assert "secrets" in checks(backstop.pre_push(repo, {}, stdin), BLOCK)


def test_pre_push_framework_env_refs(repo):
    base = run(repo, "rev-parse", "HEAD").stdout.strip()
    write(repo, "c.py", f"T = '{TOKEN}'\n")
    stage(repo, "c.py")
    sha = commit(repo, "secret")
    env = {"PRE_COMMIT_FROM_REF": base, "PRE_COMMIT_TO_REF": sha}
    assert "secrets" in checks(backstop.pre_push(repo, env, ""), BLOCK)


# --------------------------------------------------------------------------- git hooks + end to end


def test_install_refuses_foreign_and_hooks_path(repo):
    foreign = githooks.hooks_dir(repo) / "pre-commit"
    foreign.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    with pytest.raises(githooks.InstallError, match="isn't managed by Chatur"):
        githooks.install(repo)
    assert githooks.install(repo, force=True)
    run(repo, "config", "core.hooksPath", ".husky")
    with pytest.raises(githooks.InstallError, match=r"core\.hooksPath"):
        githooks.install(repo)


def test_uninstall_only_removes_ours(repo):
    githooks.install(repo)
    other = githooks.hooks_dir(repo) / "post-commit"
    other.write_text("#!/bin/sh\n", encoding="utf-8")
    removed = githooks.uninstall(repo)
    assert {p.name for p in removed} == {"pre-commit", "pre-push"} and other.exists()


def test_end_to_end_commit_blocked_by_real_hook(repo):
    githooks.install(repo)
    script = (githooks.hooks_dir(repo) / "pre-commit").read_text(encoding="utf-8")
    assert githooks.MARKER in script and Path(sys.executable).as_posix() in script
    head = run(repo, "rev-parse", "HEAD").stdout.strip()

    write(repo, "c.py", f"T = '{TOKEN}'\n")
    stage(repo, "c.py")
    blocked = run(repo, "commit", "-q", "-m", "secret", check=False)
    assert blocked.returncode != 0 and "BLOCKED" in blocked.stderr
    assert run(repo, "rev-parse", "HEAD").stdout.strip() == head

    run(repo, "rm", "-q", "--cached", "c.py")
    write(repo, "ok.txt", "fine\n")
    stage(repo, "ok.txt")
    agent_env = {**CLEAN_ENV, "CHATUR_AGENT_SESSION": "1"}
    as_agent = run(repo, "commit", "-q", "-m", "by agent", env=agent_env, check=False)
    assert as_agent.returncode != 0 and "agent session" in as_agent.stderr

    assert run(repo, "commit", "-q", "-m", "human", check=False).returncode == 0


# --------------------------------------------------------------------------- CLI + output


def test_cli_ci_check_exit_codes(repo, capsys):
    assert main(["ci-check", "--root", str(repo)]) == 0
    write(repo, "docs/requirements/PRD.md", "# PRD\n")
    gates.approve(repo, "requirements", **HUMAN)
    write(repo, "docs/requirements/PRD.md", "# changed\n")
    assert main(["ci-check", "--root", str(repo)]) == 1
    assert "stale" in capsys.readouterr().err


def test_github_annotations_and_summary(repo, tmp_path_factory, monkeypatch, capsys):
    summary = tmp_path_factory.mktemp("gh") / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    write(repo, "c.py", f"T = '{TOKEN}'\n")
    stage(repo, "c.py")
    commit(repo, "secret")
    assert main(["ci-check", "--root", str(repo), "--base", "HEAD~1"]) == 1
    assert "::error file=c.py,line=1::" in capsys.readouterr().err
    text = summary.read_text(encoding="utf-8")
    assert "## Chatur ci-check: ❌ blocked" in text and TOKEN not in text


def test_cli_ci_install_github(repo, capsys):
    assert main(["ci", "install", "github", "--root", str(repo)]) == 0
    workflow = (repo / githooks.WORKFLOW_REL).read_text(encoding="utf-8")
    assert "uses: nitsharm1910/chatur@v" in workflow and "fetch-depth: 0" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert main(["ci", "install", "github", "--root", str(repo)]) == 1  # no silent overwrite


def test_cli_git_hooks_install(repo, capsys):
    assert main(["git-hooks", "install", "--root", str(repo)]) == 0
    assert (githooks.hooks_dir(repo) / "pre-push").is_file()
    assert main(["git-hooks", "uninstall", "--root", str(repo)]) == 0


def test_action_yml_passes_inputs_via_env():
    action = (Path(__file__).resolve().parents[1] / "action.yml").read_text(encoding="utf-8")
    run_lines = [ln for ln in action.splitlines() if ln.strip().startswith("run:")]
    assert run_lines and all("${{" not in ln for ln in run_lines)  # no expression injection


def test_render_never_contains_secret(repo):
    write(repo, "c.py", f"T = '{TOKEN}'\n")
    stage(repo, "c.py")
    report = backstop.pre_commit(repo, {})
    assert TOKEN not in backstop.render(report, github=True)
    assert TOKEN not in json.dumps(
        [f.__dict__ if hasattr(f, "__dict__") else str(f) for f in report.findings]
    )
