"""`chatur check` dry-run CLI (ADR-0020)."""

import json

import pytest

from chatur.audit import audit_dir
from chatur.cli import main


@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (["git commit -m x"], 3),
        (["gh pr merge 1"], 3),
        (["git status"], 2),
        (["--read", "README.md"], 0),
        (["--write", "README.md"], 2),
        (["--write", ".chatur/state.json"], 3),
        (["--tool", "WebFetch", "--category", "web"], 0),
        (["--tool", "mystery"], 2),
        (["--tool", "mystery", "--profile", "strict"], 3),
        (["git status", "--unattended"], 3),
        (["chatur gate approve design"], 3),
    ],
)
def test_exit_codes(tmp_path, capsys, argv, code):
    assert main(["check", *argv, "--root", str(tmp_path)]) == code
    capsys.readouterr()


def test_gate_flag_what_if(tmp_path, capsys):
    args = ["check", "--write", "src/app.py", "--profile", "strict", "--root", str(tmp_path)]
    assert main(args) == 3
    assert "gate.design-before-code" in capsys.readouterr().out
    assert main([*args, "--gate", "design"]) == 2
    assert "gate.design-before-code" not in capsys.readouterr().out


def test_json_output(tmp_path, capsys):
    assert main(["check", "git push", "--json", "--root", str(tmp_path)]) == 3
    data = json.loads(capsys.readouterr().out)
    assert data["decision"] == "deny"
    assert any(h["rule_id"] == "git.no-commit-push" for h in data["hits"])


def test_text_output_lists_hits(tmp_path, capsys):
    main(["check", "git push", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert out.startswith("deny: [git.no-commit-push]")
    assert "exec.needs-approval" in out


@pytest.mark.parametrize("argv", [[], ["ls", "--write", "x"]])
def test_requires_exactly_one_action(tmp_path, capsys, argv):
    assert main(["check", *argv, "--root", str(tmp_path)]) == 1
    assert "exactly one" in capsys.readouterr().err


def test_check_never_writes_audit(tmp_path, capsys):
    main(["check", "git status", "--root", str(tmp_path)])
    capsys.readouterr()
    assert not audit_dir(tmp_path).exists()
