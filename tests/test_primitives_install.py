"""`chatur primitives install|uninstall claude` (ADR-0028)."""

import json
from pathlib import Path

import pytest

from chatur import primitives
from chatur.adapters import claude_code as cc
from chatur.adr import parse_front_matter
from chatur.cli import main

REPO = Path(__file__).resolve().parents[1]
MANIFEST = cc.PRIMITIVES_MANIFEST


def install(root: Path, force: bool = False) -> primitives.InstallReport:
    files = cc.primitive_files(primitives.primitives_root())
    return primitives.apply(root, files, MANIFEST, force=force)


def test_primitives_root_is_repo_apm_in_checkout():
    assert primitives.primitives_root() == REPO / ".apm"


def test_install_maps_every_primitive(tmp_path):
    report = install(tmp_path)
    claude = tmp_path / ".claude"
    assert len(list((claude / "agents").glob("chatur-*.md"))) == 9
    assert len(list((claude / "commands").glob("chatur-*.md"))) == 9
    assert (claude / "rules" / "chatur-sdlc.md").is_file()
    assert (claude / "skills" / "chatur-test-plan" / "SKILL.md").is_file()
    assert (claude / "skills" / "chatur-test-plan" / "assets" / "test-report.md").is_file()
    assert not report.skipped
    manifest = json.loads((tmp_path / MANIFEST).read_text(encoding="utf-8"))
    assert set(manifest["files"]) == set(report.written)


def test_agents_copied_verbatim(tmp_path):
    install(tmp_path)
    for src in (REPO / ".apm" / "agents").glob("*.agent.md"):
        target = tmp_path / ".claude" / "agents" / src.name.replace(".agent.md", ".md")
        assert target.read_bytes() == src.read_bytes()


def test_command_conversion(tmp_path):
    install(tmp_path)
    text = (tmp_path / ".claude" / "commands" / "chatur-requirements.md").read_text(
        encoding="utf-8"
    )
    fields = parse_front_matter(text)
    assert fields["argument-hint"] == "<feature>"
    assert "input" not in fields
    assert "${input:" not in text and "$ARGUMENTS" in text
    status = (tmp_path / ".claude" / "commands" / "chatur-status.md").read_text(encoding="utf-8")
    assert "argument-hint" not in status  # no inputs, no hint


def test_command_with_multiple_inputs_uses_positional():
    text = "---\ndescription: d\ninput:\n  - a\n  - b\n---\nuse ${input:a} then ${input:b}\n"
    out = cc.command_from_prompt(text)
    assert "argument-hint: <a> <b>" in out and "use $1 then $2" in out


def test_rule_conversion():
    out = cc.rule_from_instructions('---\ndescription: x\napplyTo: "src/**, tests/**"\n---\nbody\n')
    assert out.startswith('---\ndescription: x\npaths: ["src/**", "tests/**"]\n---\n')


def test_reinstall_is_idempotent(tmp_path):
    first = install(tmp_path)
    second = install(tmp_path)
    assert second.written == second.updated == second.removed == []
    assert sorted(second.unchanged) == sorted(first.written)


def test_user_edits_and_foreign_files_preserved(tmp_path):
    install(tmp_path)
    edited = tmp_path / ".claude" / "agents" / "chatur-developer.md"
    edited.write_text("my tuned developer agent\n", encoding="utf-8")
    report = install(tmp_path)
    assert edited.read_text(encoding="utf-8") == "my tuned developer agent\n"
    assert any(
        p == ".claude/agents/chatur-developer.md" and "modified locally" in r
        for p, r in report.skipped
    )

    other = tmp_path / "other"
    foreign = other / ".claude" / "commands" / "chatur-status.md"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("someone else's command\n", encoding="utf-8")
    report = install(other)
    assert foreign.read_text(encoding="utf-8") == "someone else's command\n"
    assert any("not created by chatur" in r for _, r in report.skipped)


def test_force_overwrites(tmp_path):
    install(tmp_path)
    edited = tmp_path / ".claude" / "agents" / "chatur-qa.md"
    edited.write_text("x", encoding="utf-8")
    report = install(tmp_path, force=True)
    assert ".claude/agents/chatur-qa.md" in report.updated
    assert edited.read_bytes() == (REPO / ".apm" / "agents" / "chatur-qa.agent.md").read_bytes()


def test_stale_files_removed_unless_modified(tmp_path):
    files = cc.primitive_files(primitives.primitives_root())
    primitives.apply(tmp_path, files, MANIFEST, force=False)
    keep_modified = tmp_path / ".claude" / "agents" / "chatur-docs.md"
    keep_modified.write_text("edited", encoding="utf-8")
    fewer = [
        f for f in files if "chatur-orchestrator" not in f.target and "chatur-docs" not in f.target
    ]
    report = primitives.apply(tmp_path, fewer, MANIFEST, force=False)
    assert ".claude/agents/chatur-orchestrator.md" in report.removed
    assert keep_modified.is_file()


def test_uninstall_removes_only_unmodified_ours(tmp_path):
    install(tmp_path)
    mine = tmp_path / ".claude" / "settings.json"
    mine.write_text("{}", encoding="utf-8")
    edited = tmp_path / ".claude" / "rules" / "chatur-sdlc.md"
    edited.write_text("edited", encoding="utf-8")
    report = primitives.remove(tmp_path, MANIFEST)
    assert edited.is_file() and mine.is_file()
    assert not (tmp_path / ".claude" / "agents").exists()  # emptied dirs pruned
    assert not (tmp_path / MANIFEST).exists()
    assert any("modified locally" in r for _, r in report.skipped)


def test_cli_install_and_uninstall(tmp_path, capsys):
    assert main(["primitives", "install", "claude", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "written   .claude/agents/chatur-architect.md" in out
    assert "chatur hooks install claude" in out
    assert main(["primitives", "uninstall", "claude", "--root", str(tmp_path)]) == 0
    assert "removed" in capsys.readouterr().out


def test_bad_manifest_reported(tmp_path, capsys):
    (tmp_path / ".claude").mkdir()
    (tmp_path / MANIFEST).write_text("{nope", encoding="utf-8")
    assert main(["primitives", "install", "claude", "--root", str(tmp_path)]) == 1
    assert "not valid JSON" in capsys.readouterr().err


@pytest.mark.parametrize("adapter", ["copilot", "nope"])
def test_unknown_adapter(tmp_path, capsys, adapter):
    assert main(["primitives", "install", adapter, "--root", str(tmp_path)]) == 1
