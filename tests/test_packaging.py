"""Packaging invariants (ADR-0011, ADR-0012)."""

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import chatur
from chatur.cli import main

ROOT = Path(__file__).resolve().parents[1]


def _apm_version() -> str:
    text = (ROOT / "apm.yml").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*['\"]?([^'\"\s]+)", text, re.MULTILINE)
    assert match, "apm.yml has no version field"
    return match.group(1)


def test_apm_and_python_versions_match():
    assert _apm_version() == chatur.__version__


def test_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[-.]?(?:a|b|rc|dev)\d*)?", chatur.__version__)


def test_runtime_has_no_dependencies():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["dependencies"] == []
    assert project["requires-python"] == ">=3.11"


def test_cli_version(capsys):
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    assert chatur.__version__ in capsys.readouterr().out


def test_cli_no_args_prints_help(capsys):
    assert main([]) == 0
    assert "usage: chatur" in capsys.readouterr().out


def test_module_entrypoint():
    result = subprocess.run(
        [sys.executable, "-m", "chatur", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert chatur.__version__ in result.stdout
