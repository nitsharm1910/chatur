"""Shell analysis unit tests (ADR-0017)."""

import base64
import shlex

import pytest

from chatur.shell import analyze, command_base, normalize_path


def subcommands(command: str) -> set[str | None]:
    return {c.subcommand for c in analyze(command).git_calls}


@pytest.mark.parametrize(
    ("token", "base"),
    [
        ("git", "git"),
        ("/usr/bin/git", "git"),
        (r"C:\Program Files\Git\bin\GIT.EXE", "git"),
        ('"git"', "git"),
        ("pwsh.exe", "pwsh"),
        ("cmd.EXE", "cmd"),
    ],
)
def test_command_base(token, base):
    assert command_base(token) == base


def test_simple_command():
    a = analyze("git status")
    assert a.simple and a.parseable
    assert a.argvs == (("git", "status"),)
    assert subcommands("git status") == {"status"}


def test_segments_and_redirects():
    a = analyze("echo hi > out.txt && cat a.txt | grep x; ls")
    assert not a.simple
    assert "out.txt" in a.paths
    assert {argv[0] for argv in a.argvs} == {"echo", "cat", "grep", "ls"}


def test_fd_duplication_is_not_a_path():
    a = analyze("pytest 2>&1")
    assert "1" not in a.paths and "&1" not in a.paths


def test_git_global_options_skipped():
    assert subcommands("git -C /repo -c user.name=x --no-pager --git-dir=.git commit -m y") == {
        "commit"
    }


def test_git_call_args_and_text():
    (call,) = analyze("git reset --hard HEAD~1").git_calls
    assert call.args == ("--hard", "HEAD~1")
    assert call.text() == "reset --hard HEAD~1"


def test_quoted_strings_are_not_commands():
    assert subcommands('echo "git commit -m x"') == set()
    assert subcommands("git log --grep=commit") == {"log"}


def test_encoded_command_decoded():
    payload = base64.b64encode("git push origin main".encode("utf-16-le")).decode()
    a = analyze(f"pwsh -NoProfile -EncodedCommand {payload}")
    assert {c.subcommand for c in a.git_calls} == {"push"}
    assert not a.simple


def test_bad_encoded_command_is_problem():
    a = analyze("powershell -enc !!!notbase64")
    assert "undecodable -EncodedCommand" in a.problems


@pytest.mark.parametrize(
    "command",
    ['echo "unterminated', "$G commit", "$(echo git) push", "git -c alias.ci='!git commit' ci"],
)
def test_problem_cases(command):
    assert not analyze(command).parseable


def test_deep_nesting_is_problem():
    command = "git push"
    for _ in range(7):
        command = f"sh -c {shlex.quote(command)}"
    a = analyze(command)
    assert any("nesting" in p for p in a.problems)
    assert "push" in {c.subcommand for c in a.git_calls}  # heuristic still finds it


def test_empty_command_is_problem():
    assert not analyze("   ").parseable


@pytest.mark.parametrize(
    ("path", "root", "expected"),
    [
        (r".chatur\state.json", None, ".chatur/state.json"),
        ("./src/../.chatur/state.json", None, ".chatur/state.json"),
        ("/repo/.chatur/state.json", "/repo", ".chatur/state.json"),
        (r"C:\Repo\SRC\app.py", r"c:\repo", "SRC/app.py"),
        ("/elsewhere/x.sh", "/repo", "/elsewhere/x.sh"),
        ("/repo", "/repo", "."),
    ],
)
def test_normalize_path(path, root, expected):
    assert normalize_path(path, root) == expected
