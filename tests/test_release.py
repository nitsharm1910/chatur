"""Release readiness (ADR-0031): docs cover the CLI, release workflow is safe, versions agree."""

import argparse
import re
from pathlib import Path

import chatur
from chatur.cli import build_parser

REPO = Path(__file__).resolve().parents[1]


def _commands(parser: argparse.ArgumentParser, prefix: str = "chatur") -> list[str]:
    found = []
    for action in parser._actions:  # argparse has no public API for subparsers
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                found.append(f"{prefix} {name}")
                found.extend(_commands(sub, f"{prefix} {name}"))
    return found


def test_every_cli_command_is_documented():
    reference = (REPO / "docs" / "guide" / "commands.md").read_text(encoding="utf-8")
    words = set(re.findall(r"[\w-]+", reference))
    missing = [cmd for cmd in _commands(build_parser()) if not set(cmd.split()[1:]) <= words]
    assert not missing, f"undocumented commands: {missing}"


def test_release_workflow_uses_trusted_publishing():
    workflow = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish" in workflow
    assert "environment: pypi" in workflow and "environment: testpypi" in workflow
    assert "password" not in workflow.lower() and "secrets." not in workflow  # no stored tokens
    assert 'tags: ["v*"]' in workflow


def test_changelog_and_release_notes_cover_current_version():
    version = chatur.__version__
    assert f"## [{version}]" in (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert (REPO / "docs" / "releases" / f"{version}.md").is_file()


def test_readme_links_are_absolute_for_pypi():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    relative = [
        link for link in re.findall(r"\]\(([^)]+)\)", readme) if not link.startswith("http")
    ]
    assert relative == [], f"relative links break on PyPI: {relative}"


def test_guide_internal_links_resolve():
    guide = REPO / "docs" / "guide"
    for page in guide.glob("*.md"):
        for link in re.findall(r"\]\(([^)#]+\.md)\)", page.read_text(encoding="utf-8")):
            if not link.startswith("http"):
                assert (page.parent / link).is_file(), f"{page.name} links to missing {link}"
