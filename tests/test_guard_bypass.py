"""Bypass suite (ADR-0014, ADR-0017, ADR-0018). New bypasses get a failing test here first."""

import base64

import pytest

from chatur.verdict import Decision
from conftest import check, hit_ids, shell_event


def _enc(command: str) -> str:
    return base64.b64encode(command.encode("utf-16-le")).decode()


DENIED = [
    # plain
    "git commit -m x",
    "git push",
    "git push origin main --force",
    "git merge feature",
    "git cherry-pick abc123",
    "git revert HEAD",
    "git am < patch.mbox",
    "git commit-tree HEAD^{tree} -m x",
    "git update-ref refs/heads/main abc123",
    # history rewrite
    "git reset --hard HEAD~1",
    "git rebase -i main",
    "git tag v1.0.0",
    "git branch -D feature",
    "git branch -m old new",
    "git clean -fdx",
    "git stash drop",
    "git checkout -- file.txt",
    "git restore file.txt",
    "git reflog expire --all",
    # global options before the subcommand
    "git -C /repo commit -m x",
    "git -c user.name=x commit -m x",
    "git --git-dir=.git --work-tree=. commit -m x",
    "git --no-pager push",
    "git -P -C . push",
    # git by path / case
    "/usr/bin/git push",
    r'"C:\Program Files\Git\bin\git.exe" commit -m x',
    "GIT.EXE commit -m x",
    "GIT COMMIT -m x",
    # chaining and grouping
    "git status && git commit -m x",
    "git status; git push",
    "git status || git push",
    "echo hi | git commit -F -",
    "(git commit -m x)",
    "{ git commit -m x; }",
    "git status\ngit push",
    "git add . & git commit -m x",
    # nested shells
    'sh -c "git commit -m x"',
    "bash -lc 'git push'",
    "zsh -c 'cd sub && git push'",
    'cmd /c "git commit -m x"',
    "cmd.exe /C git push",
    'powershell -Command "git push"',
    "pwsh -NoProfile -ExecutionPolicy Bypass -c 'git commit -m x'",
    'powershell.exe "git push"',
    f"pwsh -EncodedCommand {_enc('git push origin main')}",
    f"powershell -enc {_enc('git commit -m x')}",
    f"powershell -e {_enc('cd x; git push')}",
    # substitution / eval
    "echo $(git commit -m x)",
    "echo `git push`",
    "cat <(git push)",
    'eval "git commit -m x"',
    'iex "git push"',
    "Invoke-Expression 'git commit -m x'",
    "Start-Process git -ArgumentList 'push'",
    "Start-Process -FilePath git -ArgumentList push,origin,main",
    # wrappers / env
    "& git commit -m x",
    "& 'git' push",
    "sudo git push",
    "sudo -u deploy git push",
    "env GIT_DIR=.git git commit -m x",
    "GIT_AUTHOR_NAME=x git commit -m x",
    "nohup git push &",
    "timeout 10 git push",
    "nice -n 10 git push",
    "xargs git commit -m < msgs.txt",
    "time git push",
    # quoting / escape tricks
    'g""it commit -m x',
    "'git' 'commit' -m x",
    "gi\\t push",
    "git com`mit -m x",
    "g^it com^mit -m x",
    "git p`u`s`h",
    # interpreter one-liners (heuristic scan)
    "python -c \"import os; os.system('git push')\"",
    'python3 -c \'import subprocess; subprocess.run(["git", "commit", "-m", "x"])\'',
    "node -e \"require('child_process').execSync('git push')\"",
    # remote-write tools are covered separately (MCP); shell paths to gate state:
    "rm .chatur/state.json",
]


@pytest.mark.parametrize("command", DENIED)
def test_bypass_denied(command):
    verdict = check(shell_event(command))
    assert verdict.decision is Decision.DENY, f"{command!r} -> {verdict.decision}: {verdict.reason}"


ASK_NOT_DENY = [
    "git status",
    "git log --grep=commit",
    "git log --oneline --format='%h merge %s'",
    'echo "git commit"',
    "git help push",
    "grep -r 'git push' docs/",
    "git show HEAD:src/app.py",
    "git diff HEAD^ HEAD",
]


@pytest.mark.parametrize("command", ASK_NOT_DENY)
def test_no_false_deny(command):
    verdict = check(shell_event(command))
    assert verdict.decision is Decision.ASK, f"{command!r} -> {verdict.decision}: {verdict.reason}"


UNRESOLVABLE = [
    "G=git; $G commit -m x",
    "$(echo git) push",
    "git -c alias.ci='!git commit' ci",
    "git -c core.hooksPath=/dev/null status",
]


@pytest.mark.parametrize("command", UNRESOLVABLE)
def test_unresolvable_goes_to_human(command):
    verdict = check(shell_event(command))
    assert verdict.decision.blocks
    assert "default.unparseable_command" in hit_ids(verdict) or verdict.decision is Decision.DENY
    assert check(shell_event(command, attended=False)).decision is Decision.DENY
