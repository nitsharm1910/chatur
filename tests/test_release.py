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


_PLAIN_VALUE = re.compile(r"^\s*(?:-\s+)?[\w.-]+:[ \t]+(?P<value>[^\"'|>\[{&*!#%@`\s$-].*)$")


def _unquoted_colon_problems(path: Path) -> list[str]:
    """Plain YAML scalars containing ': ' (a second mapping) on `key: value` lines."""
    problems = []
    in_block = False
    block_indent = 0
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        indent = len(line) - len(line.lstrip())
        if in_block:
            if line.strip() and indent <= block_indent:
                in_block = False
            else:
                continue  # inside a `run: |` style block scalar
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.search(r":[ \t]+[|>][+-]?\d*[ \t]*$", line):
            in_block, block_indent = True, indent
            continue
        match = _PLAIN_VALUE.match(line)
        if match and re.search(r": |:$", match.group("value").split(" #")[0]):
            problems.append(f"{path.name}:{number}: {line.strip()[:80]}")
    return problems


def test_yaml_files_have_no_unquoted_colon_values():
    # Regression (2026-11-05): `description: Chatur backstop: policy ...` made GitHub reject
    # action.yml ("Mapping values are not allowed in this context"). The runtime is stdlib-only,
    # so there is no YAML parser here; this lints that exact mistake.
    files = [
        REPO / "action.yml",
        REPO / ".pre-commit-hooks.yaml",
        REPO / "apm.yml",
        *sorted((REPO / ".github" / "workflows").glob("*.yml")),
    ]
    problems = [p for path in files for p in _unquoted_colon_problems(path)]
    assert not problems, "quote these values (they contain ': '):\n" + "\n".join(problems)


def test_yaml_lint_catches_the_reported_mistake(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("name: x\ndescription: Chatur backstop: policy validity\n", encoding="utf-8")
    assert _unquoted_colon_problems(bad) == [
        "bad.yml:2: description: Chatur backstop: policy validity"
    ]
    good = tmp_path / "good.yml"
    good.write_text(
        'description: "Chatur backstop: policy validity"\n'
        "steps:\n  - run: |\n      echo a: b\n  - name: Check tag: matches\n",
        encoding="utf-8",
    )
    assert _unquoted_colon_problems(good) == [
        "good.yml:5: - name: Check tag: matches"
    ]  # block scalar skipped, real mistake still found
