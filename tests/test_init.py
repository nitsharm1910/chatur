"""`chatur init` (ADR-0022)."""

import tomllib

import pytest

from chatur.cli import main
from chatur.policy import PolicyError, load_project_policy
from chatur.project import (
    DOC_FOLDERS,
    GITIGNORE_BEGIN,
    TEMPLATES,
    InitError,
    gitignore_block,
    init_project,
)


def test_init_creates_layout(tmp_path):
    result = init_project(tmp_path)
    expected = {
        ".chatur/config.toml",
        ".chatur/policy.local.toml",
        "docs/decisions/0000-template.md",
        ".gitignore",
        *(f"docs/{f}/README.md" for f in DOC_FOLDERS),
        *(f".chatur/templates/{t}" for t in TEMPLATES),  # harness-owned (ADR-0029)
    }
    assert set(result.created) == expected
    config = tomllib.loads((tmp_path / ".chatur/config.toml").read_text(encoding="utf-8"))
    assert config["schema"] == "chatur.config/v1"
    assert config["policy"]["profile"] == "standard"
    assert config["assistants"]["enabled"] == ["claude", "copilot"]
    assert config["audit"]["commit"] is True
    policy = load_project_policy(tmp_path)  # written files compose cleanly
    assert policy.sources == ("baseline", "profile:standard", "local")


def test_init_is_idempotent_and_never_overwrites(tmp_path):
    init_project(tmp_path)
    readme = tmp_path / "docs/design/README.md"
    readme.write_text("my own notes\n", encoding="utf-8")
    result = init_project(tmp_path, profile="strict")
    assert result.created == []
    assert ".chatur/config.toml" in result.skipped
    assert readme.read_text(encoding="utf-8") == "my own notes\n"
    assert load_project_policy(tmp_path).profile == "standard"  # existing config kept


def test_force_rewrites_config_only(tmp_path):
    init_project(tmp_path)
    (tmp_path / "docs/design/README.md").write_text("keep\n", encoding="utf-8")
    state = tmp_path / ".chatur/state.json"
    state.write_text('{"schema": "chatur.state/v1", "gates": {}}', encoding="utf-8")
    result = init_project(tmp_path, profile="strict", force=True)
    assert result.updated == [".chatur/config.toml"]  # standard and strict both commit audit
    assert load_project_policy(tmp_path).profile == "strict"
    assert (tmp_path / "docs/design/README.md").read_text(encoding="utf-8") == "keep\n"
    assert state.read_text(encoding="utf-8").startswith('{"schema"')


@pytest.mark.parametrize(
    ("profile", "audit_ignored"), [("strict", False), ("standard", False), ("relaxed", True)]
)
def test_gitignore_block_per_profile(tmp_path, profile, audit_ignored):
    init_project(tmp_path, profile=profile)
    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".chatur/audit/.lock" in text
    assert (".chatur/audit/\n" in text) is audit_ignored


def test_gitignore_appends_and_replaces_block(tmp_path):
    (tmp_path / ".gitignore").write_text("node_modules/\n*.log", encoding="utf-8")
    init_project(tmp_path)
    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert text.startswith("node_modules/\n*.log\n" + GITIGNORE_BEGIN)
    # re-running with a different audit setting replaces the block in place
    (tmp_path / ".chatur/config.toml").unlink()
    init_project(tmp_path, profile="relaxed")
    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert text.count(GITIGNORE_BEGIN) == 1
    assert text.endswith(gitignore_block(commit_audit=False))


def test_existing_config_commit_setting_wins(tmp_path):
    init_project(tmp_path, profile="relaxed")  # commit = false
    result = init_project(tmp_path, profile="strict")  # config kept -> still false
    assert ".gitignore" in result.skipped
    assert ".chatur/audit/\n" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_invalid_profile_writes_nothing(tmp_path):
    with pytest.raises(PolicyError):
        init_project(tmp_path, profile="yolo")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("assistants", [["chatgpt"], [""], ["claude", "notreal"]])
def test_invalid_assistants_write_nothing(tmp_path, assistants):
    with pytest.raises(InitError):
        init_project(tmp_path, assistants=assistants)
    assert list(tmp_path.iterdir()) == []


def test_instructions_only_assistants_noted(tmp_path):
    result = init_project(tmp_path, assistants=["claude", "gemini", "Codex"])
    config = tomllib.loads((tmp_path / ".chatur/config.toml").read_text(encoding="utf-8"))
    assert config["assistants"]["enabled"] == ["claude", "gemini", "codex"]
    assert any(n.startswith("gemini: instructions-only") for n in result.notes)
    assert any(n.startswith("codex: instructions-only") for n in result.notes)


def test_cli_init(tmp_path, capsys):
    assert main(["init", "--root", str(tmp_path), "--profile", "strict"]) == 0
    out = capsys.readouterr().out
    assert "created  .chatur/config.toml" in out
    assert main(["policy", "validate", "--root", str(tmp_path)]) == 0
    assert "profile=strict" in capsys.readouterr().out


def test_cli_init_bad_profile(tmp_path, capsys):
    assert main(["init", "--root", str(tmp_path), "--profile", "nope"]) == 1
    assert "chatur init:" in capsys.readouterr().err
